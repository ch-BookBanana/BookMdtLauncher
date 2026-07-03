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
        * `destroy()`：显式销毁当前计时器，断开连接、清理 event、并在没有活动计时器时关闭共享线程。

    - 信号
        * `timeout`：计时器触发时发出（行为等同 QTimer.timeout）。
        * `finished(result)`：当 `task()` 中的后台 job 返回时发出，携带返回值。

    - 类方法（便捷）
        * `QThTimer.singleShot(ms, callback)`：单次延迟在主线程调用 `callback()`。
        * `QThTimer.timer(ms, [callbacks], single_shot=False)`：创建并启动一个计时器，`callbacks` 接收 `timeout`。
        * `QThTimer.task(job, events=None, result_callback=None, interval=0)`：事件模式的后台任务。

`task`（事件模式，推荐）
    - 用法：`QThTimer.task(job, events=None, result_callback=None, interval=0)`。
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

            QThTimer.task(job, events=[on_progress], result_callback=on_done)

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

from PyQt5.Qt import QObject, QTimer, QThread, pyqtSignal, pyqtSlot, Qt

_qthtimer_thread = None
_active_timers = set()


def _get_qthtimer_thread():
    global _qthtimer_thread
    if _qthtimer_thread is None:
        _qthtimer_thread = QThread()
        _qthtimer_thread.setObjectName("QThTimerThread")
        _qthtimer_thread.start()
    return _qthtimer_thread


def _shutdown_qthtimer_thread():
    global _qthtimer_thread
    try:
        if _qthtimer_thread is not None and _qthtimer_thread.isRunning():
            _qthtimer_thread.quit()
            _qthtimer_thread.wait(1000)
    except Exception:
        pass
    _qthtimer_thread = None


class _QThTimerWorker(QObject):
    timeout = pyqtSignal()
    finished = pyqtSignal(object)

    def __init__(self, interval=0, single_shot=False, job=None):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.setInterval(int(interval))
        self.timer.setSingleShot(bool(single_shot))
        self.job = job
        self.timer.timeout.connect(self._on_timeout)

    @pyqtSlot()
    def _on_timeout(self):
        if self.job is None:
            self.timeout.emit()
            return

        try:
            result = self.job()
        except Exception as e:
            result = e
        self.finished.emit(result)

    @pyqtSlot()
    def start(self):
        self.timer.start()

    @pyqtSlot()
    def stop(self):
        self.timer.stop()

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

    def __init__(self, interval=0, parent=None):
        super().__init__(parent)
        self._interval = int(interval)
        self._single_shot = False
        self._job = None
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
        """Stop and cleanup this timer, disconnect signals and free resources."""
        try:
            self.stop()
        except Exception:
            pass

        # 断开与 worker 的连接并删除 worker
        try:
            self._worker.timeout.disconnect(self.timeout)
        except Exception:
            pass
        try:
            self._worker.finished.disconnect(self.finished)
        except Exception:
            pass

        try:
            self._worker.deleteLater()
        except Exception:
            pass

        # 删除 event 对象（如果存在）
        try:
            if hasattr(self, '_event') and self._event is not None:
                self._event.deleteLater()
        except Exception:
            pass

        # 从活动集合中移除并尝试关闭线程（若无活动计时器）
        try:
            if self in _active_timers:
                _active_timers.discard(self)
        except Exception:
            pass

        # 断开父对象连接
        try:
            if getattr(self, '_parent_obj', None) is not None:
                self._parent_obj.destroyed.disconnect(self.destroy)
        except Exception:
            pass

        # 清理引用
        self._worker = None
        self._event = None

        if not _active_timers:
            _shutdown_qthtimer_thread()

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
    def task(cls, job, events=None, result_callback=None, interval=0):
        """
        在子线程执行 `job(event)`（事件模式）。

        参数：
          - job(event): 在子线程执行，必须接受一个 `event` 参数。
                 可在 `job` 内使用 `event.lambdas[i].emit(value)` 发出事件信号。
          - events: 可选，指定事件回调，支持格式：
                * 单个回调：`callback`
                * 回调列表：`[callback1, callback2]`
            仅支持回调列表或单个回调，不支持元组或名称对。
          - result_callback：可选，job 返回值的回调（在主线程中调用）。
          - interval：延迟毫秒（0 表示立即）。

        返回：已启动的 `QThTimer` 实例。
        """
        # 归一化 events 为回调列表
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

        # 动态创建 Event 类，包含 lambda0, lambda1 ... 信号
        cls_dict = {}
        for index in range(len(callbacks)):
            cls_dict[f'lambda{index}'] = pyqtSignal(object)

        EventClass = type('QThEvent', (QObject,), cls_dict)
        event = EventClass()
        event.lambdas = [getattr(event, f'lambda{index}') for index in range(len(callbacks))]

        # 把 event 移到共享子线程
        event.moveToThread(_get_qthtimer_thread())

        # 连接回调（在主线程运行）
        for index, cb in enumerate(callbacks):
            if cb is not None:
                try:
                    event.lambdas[index].connect(cb, Qt.QueuedConnection)
                except Exception:
                    pass

        # 包装 job 使其接收 event
        def _wrapped_job():
            try:
                return job(event)
            except Exception as e:
                return e

        timer = cls(interval)
        timer._event = event
        timer.setJob(_wrapped_job)
        if result_callback is not None:
            timer.finished.connect(result_callback)
        timer.setSingleShot(True)
        timer.start()
        return timer


def shutdown():
    """销毁所有活动计时器并关闭共享子线程。"""
    # 复制集合以避免在迭代时修改
    for t in list(_active_timers):
        try:
            t.destroy()
        except Exception:
            pass
    _shutdown_qthtimer_thread()
