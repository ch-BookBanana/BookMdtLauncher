"""
QThTimer 使用文档（简洁版，中文）

简介
    QThTimer 是一个 QTimer 风格的事件管理器，计时器逻辑在模块内共享的单个子线程中运行，
    通过信号槽把事件回传到主线程，从而避免为每个计时器创建独立线程。

设计原则
    - 兼容 QTimer 的基本用法（`start` / `stop` / `setInterval` / `singleShot` 等）。
    - 默认的 `task` 为事件驱动模式：后台任务通过 `event.lambdas[i].emit(value)` 将中间数据或事件回传。
    - 模块内部维护单一子线程（避免线程爆炸），并提供显式销毁与全局 shutdown。

主要 API
    - 实例方法
        * `start()` / `stop()`：启动或停止计时器（在子线程中运行）。
        * `setInterval(ms)`：设置触发间隔（毫秒）。
        * `setSingleShot(bool)`：是否仅触发一次。
        * `destroy()`：显式销毁当前计时器，断开连接并清理 event。

    - 信号
        * `timeout`：计时器触发时发出（行为等同 QTimer.timeout）。
        * `finished(result)`：当 `task()` 中的后台 job 返回时发出，携带返回值。

    - 类方法（便捷）
        * `QThTimer.singleShot(ms, callback)`：单次延迟在主线程调用 `callback()`。
        * `QThTimer.timer(ms, [callbacks], single_shot=False)`：创建并启动一个计时器，`callbacks` 接收 `timeout`。
        * `QThTimer.task(interval, job, events=None, result_callback=None, dedicated=False)`：事件模式的后台任务。

`task`（事件模式，推荐）
    - 用法：`QThTimer.task(interval, job, events=None, result_callback=None, dedicated=False)`。
    - 约定：`job` 必须接受一个 `event` 参数；在子线程内部可调用 `event.lambdas[i].emit(value)`。
    - `events` 参数用于指定回调列表，支持两种形式：
            1. 列表：`[cb1, cb2, ...]`，每个元素对应一个 `event.lambdas[i]` 信号。
            2. 单个可调用对象：`events=cb`，等效于 `[cb]`。
    - `result_callback`：可选，`job` 返回值的回调（在主线程执行）。
    - 访问方式：始终使用 `event.lambdas[i].emit(value)`，不支持元组或命名事件。
示例
    - 周期回调（主线程）
            a = QThTimer.timer(1000, [lambda: func_a(), lambda: func_b()])

    - 单次延迟
            QThTimer.singleShot(500, lambda: print('延迟500ms'))

    - 后台任务带事件回传
            def job(event):
                    event.lambdas[0].emit(0.75)
                    return 'done'

            def on_progress(v):
                    print('progress', v)

            def on_done(res):
                    print('result', res)

            QThTimer.task(0, job, events=[on_progress], result_callback=on_done)

父对象（parent）支持
    - 在构造 `QThTimer(interval, parent=someQObject)` 时，`QThTimer` 会监听 `parent.destroyed`，
        父对象销毁时自动调用 `destroy()`。也可手动调用 `destroy()`。

销毁与进程退出
    - 每个 `QThTimer` 实例会在内部注册到 `_active_timers`，调用 `destroy()` 会移除注册并清理。
    - 提供模块级 `shutdown()`：销毁所有活动计时器并停止共享子线程。建议在程序退出时调用。

注意事项
    - `event.lambdas[i].emit(...)` 会通过 `Qt.QueuedConnection` 在主线程触发回调，确保线程安全。
    - `task` 的 `job` 运行在共享子线程中，请避免在 job 中进行 GUI 操作；GUI 更新应通过信号回到主线程处理。
"""

import inspect
import traceback

from PyQt5.Qt import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, Qt

_qthtimer_thread = None
_active_timers = set()
_dedicated_threads = set()
_zombie_threads = []      # 未能及时停止的线程：保留引用，交给进程退出兜底
_shutting_down = False    # 全局退出标志（shutdown 时置位）


def _get_qthtimer_thread():
    global _qthtimer_thread
    if _qthtimer_thread is None:
        _qthtimer_thread = QThread()
        _qthtimer_thread.setObjectName("QThTimerThread")
        _qthtimer_thread.start()
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(shutdown)
        except Exception:
            pass
    return _qthtimer_thread


def _shutdown_qthtimer_thread(timeout=10000):
    """安全停止共享子线程。

    注意：绝不调用 QThread.terminate()——它会在线程仍持有 Python 对象时
    强制终止，导致解释器状态损坏，从而弹出 “Python 已停止运行” 崩溃框。
    若超时仍未退出（如 job 卡在网络请求），保留引用交给进程退出兜底。
    """
    global _qthtimer_thread
    thread = _qthtimer_thread
    _qthtimer_thread = None
    if thread is None or not thread.isRunning():
        return
    thread.quit()
    if not thread.wait(timeout):
        _zombie_threads.append(thread)


def _get_callback_arg_count(callback):
    if callback is None:
        return 0
    try:
        signature = inspect.signature(callback)
        count = 0
        for param in signature.parameters.values():
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                count += 1
            elif param.kind == inspect.Parameter.VAR_POSITIONAL:
                return None
        return count
    except Exception:
        return 1


def _make_signal_for_callback(callback):
    arg_count = _get_callback_arg_count(callback)
    if arg_count is None:
        return pyqtSignal(object)
    if arg_count <= 0:
        return pyqtSignal()
    return pyqtSignal(*([object] * arg_count))


class _QThTimerWorker(QObject):
    timeout = pyqtSignal()
    finished = pyqtSignal(object)
    requestCleanup = pyqtSignal()                    # ★ 信号：外部（任意线程）请求清理

    def __init__(self, interval=0, single_shot=False, job=None):
        super().__init__()
        self._destroyed = False
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval))
        self.timer.setSingleShot(bool(single_shot))
        self.job = job
        self.timer.timeout.connect(self._on_timeout)
        # ★ 用信号槽连接清理逻辑，不做 invokeMethod
        self.requestCleanup.connect(self._do_cleanup, Qt.QueuedConnection)

    @pyqtSlot()
    def _on_timeout(self):
        if self._destroyed:
            return
        if self.job is None:
            self.timeout.emit()
            return

        try:
            result = self.job()
        except Exception as e:
            result = e

        if self._destroyed:
            return

        self.finished.emit(result)

    @pyqtSlot()
    def start(self):
        self.timer.start()

    @pyqtSlot()
    def stop(self):
        try:
            self.timer.stop()
        except RuntimeError:
            pass  # 忽略跨线程警告

    @pyqtSlot()
    def _do_cleanup(self):
        """在 worker 所在线程中安全停止定时器（通过信号槽触发，线程安全）。"""
        self._destroyed = True
        try:
            self.timer.stop()
        except Exception:
            pass
        
    @pyqtSlot(int)
    def setInterval(self, interval):
        self.timer.setInterval(int(interval))

    @pyqtSlot(bool)
    def setSingleShot(self, single_shot):
        self.timer.setSingleShot(bool(single_shot))

    @pyqtSlot(object)
    def setJob(self, job):
        self.job = job


class QThTimer(QObject):
    timeout = pyqtSignal()
    finished = pyqtSignal(object)
    _request_start = pyqtSignal()
    _request_stop = pyqtSignal()
    _request_interval = pyqtSignal(int)
    _request_single_shot = pyqtSignal(bool)
    _request_job = pyqtSignal(object)

    def __init__(self, interval=0, parent=None, dedicated=False):
        super().__init__(parent)
        self._interval = int(interval)
        self._single_shot = False
        self._job = None
        self._dedicated = dedicated
        if dedicated:
            self._thread = QThread()
            self._thread.setObjectName("QThTimerDedicated")
            self._thread.start()
            _dedicated_threads.add(self._thread)
        else:
            self._thread = _get_qthtimer_thread()
        self._worker = _QThTimerWorker(self._interval, self._single_shot, self._job)
        self._worker.moveToThread(self._thread)
        # 注册实例，便于全局管理与销毁
        _active_timers.add(self)
        self._event = None
        self._parent_obj = None
        # 如果传入 parent，则在 parent 销毁时自动销毁本实例
        if parent is not None:
            try:
                parent.destroyed.connect(self.destroy, Qt.QueuedConnection)
                self._parent_obj = parent
            except Exception:
                self._parent_obj = None

        self._worker.timeout.connect(self.timeout, Qt.QueuedConnection)
        self._worker.finished.connect(self.finished, Qt.QueuedConnection)

        self._request_start.connect(self._worker.start)
        self._request_stop.connect(self._worker.stop)
        self._request_interval.connect(self._worker.setInterval)
        self._request_single_shot.connect(self._worker.setSingleShot)
        self._request_job.connect(self._worker.setJob)

    def setInterval(self, interval):
        self._interval = int(interval)
        self._request_interval.emit(self._interval)

    def interval(self):
        return self._interval

    def setSingleShot(self, single_shot):
        self._single_shot = bool(single_shot)
        self._request_single_shot.emit(self._single_shot)

    def isSingleShot(self):
        return self._single_shot

    def setJob(self, job):
        self._job = job
        self._request_job.emit(job)

    def start(self):
        self._request_start.emit()

    def stop(self):
        self._request_stop.emit()

    def destroy(self):
        """异步安全销毁计时器。"""
        if getattr(self, '_destroyed', False):
            return
        self._destroyed = True

        if self._event is not None:
            ev = self._event
            self._event = None
            try:
                ev.deleteLater()
            except Exception:
                pass

        worker = self._worker
        self._worker = None
        if worker is not None:
            worker._destroyed = True
            if not _shutting_down:
                # 正常运行期：请求工作线程停止计时器并延迟销毁
                try:
                    worker.requestCleanup.emit()
                except Exception:
                    pass
                try:
                    worker.deleteLater()
                except Exception:
                    pass
            # 退出阶段：线程即将整体停止，跳过跨线程清理，避免 deferred-delete 崩溃

        # 专用线程：退出并等待（绝不 terminate，超时保留引用兜底）
        if self._dedicated and self._thread is not None:
            thr = self._thread
            self._thread = None
            _dedicated_threads.discard(thr)
            try:
                thr.quit()
                if not thr.wait(3000):
                    _zombie_threads.append(thr)
            except Exception:
                pass

        try:
            if getattr(self, '_parent_obj', None) is not None:
                self._parent_obj.destroyed.disconnect(self.destroy)
        except Exception:
            pass

        try:
            _active_timers.discard(self)
        except Exception:
            pass

    @classmethod
    def once(cls, interval, callbacks=None):
        timer = cls(interval)
        timer.setSingleShot(True)
        if callbacks:
            for fn in callbacks:
                timer.timeout.connect(fn)
        timer.start()
        return timer

    @classmethod
    def singleShot(cls, interval, callback):
        timer = cls(interval)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.start()
        return timer

    @classmethod
    def every(cls, interval, callbacks=None):
        return cls.timer(interval, callbacks=callbacks, single_shot=False)

    @classmethod
    def timer(cls, interval, callbacks=None, single_shot=False):
        timer = cls(interval)
        timer.setSingleShot(single_shot)
        if callbacks:
            for fn in callbacks:
                timer.timeout.connect(fn)
        timer.start()
        return timer

    @classmethod
    def task(cls, interval, job, events=None, result_callback=None, dedicated=False):
        """
        在子线程执行 `job(event)`（事件模式）。

        参数：
          - interval：延迟毫秒（0 表示立即）。
          - job(event): 在子线程执行，必须接受一个 `event` 参数。
                 可在 `job` 内使用 `event.lambdas[i].emit(value)` 发出事件信号。
          - events: 可选，指定事件回调，支持格式：
                * 单个回调：`callback`
                * 回调列表：`[callback1, callback2]`
            仅支持回调列表或单个回调，不支持元组或名称对。
          - result_callback：可选，job 返回值的回调（在主线程中调用）。
          - dedicated：True 时使用独立线程（适合 >1s 长任务），避免阻塞共享线程队列。

        返回：已启动的 `QThTimer` 实例。
        """
        callbacks = []
        if events is None:
            callbacks = []
        elif callable(events):
            callbacks = [events]
        elif isinstance(events, list):
            for item in events:
                if item is None or callable(item):
                    callbacks.append(item)
                else:
                    raise TypeError('events list items must be callable or None')
        else:
            raise TypeError('events must be callable or a list of callables')

        cls_dict = {}
        for index, cb in enumerate(callbacks):
            cls_dict[f'lambda{index}'] = _make_signal_for_callback(cb)

        EventClass = type('QThEvent', (QObject,), cls_dict)
        event = EventClass()
        event.lambdas = [getattr(event, f'lambda{index}') for index in range(len(callbacks))]

        event.moveToThread(_get_qthtimer_thread())

        for index, cb in enumerate(callbacks):
            if cb is not None:
                try:
                    event.lambdas[index].connect(cb, Qt.QueuedConnection)
                except Exception:
                    pass

        def _wrapped_job():
            try:
                return job(event)
            except Exception:
                # job 异常不再静默吞掉：打印完整堆栈便于定位（仍返回异常对象，
                # 兼容 result_callback 收到的可能是异常的容错逻辑）
                traceback.print_exc()
                import sys
                sys.stdout.flush()
                e = sys.exc_info()[1]
                return e

        timer = cls(interval, dedicated=dedicated)
        timer._event = event
        timer.setJob(_wrapped_job)
        if result_callback is not None:
            timer.finished.connect(result_callback)
        timer.setSingleShot(True)
        timer.start()
        return timer


    @classmethod
    def taskP(cls, interval, job, events=None, result_callback=None, dedicated=False):
        """
        周期性后台任务，每隔 `interval` 毫秒在子线程执行一次 `job(event)`。

        参数：
          - job(event): 每次触发都在子线程执行，必须接受 event 参数。
                可在 job 内使用 event.lambdas[i].emit(value) 回传数据。
          - interval: 周期（毫秒）。
          - events: 可选，接收 job 中 emit 的回调（主线程执行）。
          - result_callback: 可选，每次 job 返回值的回调（主线程执行）。
          - dedicated：True 时使用独立线程（适合 >1s 长任务），避免阻塞共享线程队列。

        返回：已启动的 QThTimer 实例。
        用法：返回值的 destroy() 可停止该周期性任务。
        """
        callbacks = []
        if events is None:
            callbacks = []
        elif callable(events):
            callbacks = [events]
        elif isinstance(events, list):
            for item in events:
                if item is None or callable(item):
                    callbacks.append(item)
                else:
                    raise TypeError('events list items must be callable or None')
        else:
            raise TypeError('events must be callable or a list of callables')

        cls_dict = {}
        for index, cb in enumerate(callbacks):
            cls_dict[f'lambda{index}'] = _make_signal_for_callback(cb)
        EventClass = type('QThEvent', (QObject,), cls_dict)
        event = EventClass()
        event.lambdas = [getattr(event, f'lambda{index}') for index in range(len(callbacks))]
        event.moveToThread(_get_qthtimer_thread())

        for index, cb in enumerate(callbacks):
            if cb is not None:
                try:
                    event.lambdas[index].connect(cb, Qt.QueuedConnection)
                except Exception:
                    pass

        def _wrapped_job():
            try:
                result = job(event)
                return result
            except Exception:
                # job 异常不再静默吞掉：打印完整堆栈便于定位（仍返回异常对象，
                # 兼容 result_callback 收到的可能是异常的容错逻辑）
                traceback.print_exc()
                import sys
                sys.stdout.flush()
                e = sys.exc_info()[1]
                return e

        timer = cls(interval, dedicated=dedicated)
        timer._event = event
        timer.setJob(_wrapped_job)
        timer.setSingleShot(False)
        if result_callback is not None:
            timer.finished.connect(result_callback)
        timer.start()
        return timer


def shutdown():
    """销毁所有活动计时器并关闭共享/专用子线程（退出时调用）。

    全程不调用 terminate()，避免线程被强杀导致解释器崩溃；
    无法及时停止的线程保留引用，由进程退出（os._exit 兜底）统一处理。
    """
    global _shutting_down
    _shutting_down = True
    for t in list(_active_timers):
        try:
            t.destroy()
        except Exception:
            pass
    for thr in list(_dedicated_threads):
        try:
            thr.quit()
            if not thr.wait(3000):
                _zombie_threads.append(thr)
        except Exception:
            pass
    _dedicated_threads.clear()
    _shutdown_qthtimer_thread()
