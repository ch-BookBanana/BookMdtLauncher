import os
import logging
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Signal

from .mdtManager import mdtManager
from .javaManager import javaManager
from .mdtLocker import mdtLocker

_log = logging.getLogger("Main.MdtLauncher")

# i18n：日志文本来自语言文件（main.py 初始化 langer 后注入翻译函数）。
# 未注入时回退为 key 本身，日志仍可读、不影响运行。
_tr_func = None


def set_tr_func(fn):
    """注入语言翻译函数（langer.get），供本模块日志 i18n。"""
    global _tr_func
    _tr_func = fn


def _tr(key, *args):
    """取翻译文本并替换 $1/$2 占位符；未注入翻译函数时原样返回 key。"""
    text = _tr_func(key) if _tr_func is not None else key
    try:
        for i, arg in enumerate(reversed(args), start=1):
            text = text.replace("$%d" % i, str(arg))
    except Exception:
        pass
    return text


class mdtLauncher(QProcess):
    game_launched = Signal()       # 已开始尝试启动
    game_started = Signal()        # 进程已成功开始运行
    lifecycle_finished = Signal(int)  # 生命周期结束（启动失败/进程退出/错误），传出退出码
    game_finished = Signal(int)    # 游戏进程真正结束（仅 QProcess.finished 触发），传出退出码
    game_log = Signal(dict)        # 进程输出日志，dict: {"type":"info"/"error", "text":...}
    log = Signal(dict)             # 通用日志信号（启动阶段 info/error）
    java_missing = Signal()        # Java 缺失/无效（UI 据此切页显示"未检测到Java"）
    java_status = Signal(str)      # Java 下载流程状态：downloading/extracting/done/error
    java_progress = Signal(int, int)      # Java 下载进度（已下载字节, 总字节）
    java_extract_progress = Signal(int, int)  # Java 解压/部署进度
    java_done = Signal(bool)       # Java 下载流程结束（True 成功 / False 失败）
    java_cancelled = Signal()      # Java 下载被用户取消（UI 显示"已取消"而非"失败"）
    java_paused = Signal(bool, int)   # Java 下载暂停状态（是否暂停, 当前百分比）

    def __init__(self, parent=None, settings=None):
        super().__init__()
        self.root = parent  # Main 实例（mdtManager 等工具经此访问）
        self.envs = QProcessEnvironment.systemEnvironment()
        self.going = 0   # 0: 空闲, 1: 校验中/准备启动, 2: 进程运行中
        self.data = {}   # 本次启动的关键路径信息
        self.settings = settings or {}
        self._finished_emitted = False
        self._java_flow = None                 # Java 自动下载流程实例
        self._java_download_attempts = 0       # 自动下载尝试次数（防循环；游戏启动/结束时重置）
        self._java_cancelled = False           # 当前 Java 下载是否被用户取消（决定显示"已取消"还是"失败"）
        self._java_rescan_done = False         # 本次启动是否已用掉"没 Java 就先重扫一遍"的补救机会
        self._locker = mdtLocker()             # 实例锁：运行期间禁止实例与本体改名/删除（数据目录不限）

    def _launch(self, mdt_name, java_path=None, args=None, data_path=None):
        """
        校验参数并启动 Mindustry 服务端（异步）。
        返回 True 表示启动指令已发出，False 表示启动前校验失败。
        进程的实际启动、运行、结束都通过信号通知。
        """
        # ---------- 启动前校验：失败直接返回 ----------
        # 必须排在 game_launched 之前：把界面切到「启动中」页的正是这个信号，
        # 先切页再退出会留下一个没人负责收回的界面（卡在"就绪"，且 going 停在 1）。
        if self.going:
            self.log.emit({"type": "error", "text": "gameRunning"})
            self._emit_finished(-1)
            return False
        if mdt_name not in self.root.mdtManager.getMdts():
            self.log.emit({"type": "error", "text": "mdtNotFound"})
            self._emit_finished(-1)
            return False

        # ---------- 生命周期开始 ----------
        # game_launched 必须早于任何日志：Start 页挂在它上面清空上一次的控制台
        self._finished_emitted = False
        self.game_launched.emit()
        self.going = 1
        self.log.emit({"type": "info", "text": "Launch preparation started for: " + mdt_name})

        # ---------- 初始化 data ----------
        self.data = {
            "mdtName": None,
            "mdtPath": None,
            "mdtJar": None,
            "mdtDataRoot": None,
            "mdtData": None,
            "javaPath": None,
            "args": None
        }

        self.data["mdtName"] = mdt_name
        self.data["mdtPath"] = os.path.join(mdtManager.base_dir, mdt_name)
        self.data["mdtJar"] = os.path.join(self.data["mdtPath"], "mdt.jar")
        self.log.emit({"type": "info", "text": "MDT instance found: " + mdt_name})

        # ---------- 2. 确定数据目录 ----------
        # 数据根作为游戏进程的 %APPDATA%，游戏实际数据目录固定为其下的 Mindustry/
        if data_path is None:
            data_root = mdtManager.getDataRoot(mdt_name)
            self.log.emit({"type": "info", "text": "Using default data directory: " + data_root})
        else:
            try:
                data_root = os.path.abspath(data_path)
                self.log.emit({"type": "info", "text": "Using custom data directory: " + data_root})
            except Exception:
                self.log.emit({"type": "error", "text": "mdtDataError"})
                self.going = 0
                self._emit_finished(-1)
                return False
        self.data["mdtDataRoot"] = data_root
        self.data["mdtData"] = os.path.join(data_root, mdtManager.DATA_DIR_NAME)
        self._prepare_data_dir()

        # ---------- 3. 确定 Java 路径 ----------
        # 解析与校验的口径收在 _resolve_java 里，界面上的"提前拦"用的是同一套
        java_from_config, problem = self._resolve_java(mdt_name, java_path)
        if problem:
            self._java_unavailable(problem)
            return False
        self.data["javaPath"] = java_from_config
        self.log.emit({"type": "info", "text": "Java path validated: " + java_from_config})

        self.data["args"] = args if args else []
        self.log.emit({"type": "info", "text": "Launch args: " + str(self.data["args"])})

        # ---------- 4. 设置进程环境 ----------
        # APPDATA 指向数据根：游戏（含不支持 MINDUSTRY_DATA_DIR 的旧版本）会在其下使用 Mindustry/，
        # 与实际数据目录 <数据根>/Mindustry 一致
        self.envs.insert("MINDUSTRY_DATA_DIR", self.data["mdtData"])
        self.envs.insert("APPDATA", self.data["mdtDataRoot"])
        self.setProcessEnvironment(self.envs)
        self.setProcessChannelMode(QProcess.SeparateChannels)
        self.setWorkingDirectory(self.data["mdtDataRoot"])

        # ---------- 5. 连接信号（先断开避免重复） ----------
        self._disconnect_signals()
        self.readyReadStandardOutput.connect(self.on_stdout)
        self.readyReadStandardError.connect(self.read_stderr)
        self.started.connect(self._on_started)
        self.finished.connect(self._on_finished)
        self.errorOccurred.connect(self._on_error)

        # ---------- 6. 锁定实例 ----------
        # 锁住实例目录本身与其中不在数据根里的全部内容：运行期间实例目录、mdt.jar 等
        # 都改不了名也删不掉（用户手动改名或启动器自身的重命名都会被系统拒绝）；
        # 数据根整棵子树不持句柄也不下钻：游戏要随时写存档/设置，里面的文件任人改。
        locked, failed = self._locker.lock(self.data["mdtPath"],
                                           exclude=[self.data["mdtDataRoot"]])
        self.log.emit({"type": "info", "text": "Locked instance, data untouched (%d objects, %d failed): " % (locked, failed) + self.data["mdtPath"]})

        # ---------- 7. 启动（异步） ----------
        self.log.emit({"type": "info", "text": "Starting process: " + self.data["javaPath"] + " -jar " + self.data["mdtJar"]})
        self.start(self.data["javaPath"],
                   self.data["args"] + ["-jar", self.data["mdtJar"]])

    def run(self, mdt_name, java_path=None, args=None, data_path=None):
        """对外接口：启动服务端（异步），不阻塞调用线程。"""
        # 新的一次启动：重新给一次"没有 Java 就先重扫候选表"的补救机会
        # （重试走 _launch 而不是 run，正是为了不把这面旗子又立回去）
        self._java_rescan_done = False
        self._launch(mdt_name, java_path, args, data_path)

    def kill_game(self, blocking=False):
        """杀掉由本启动器拉起的游戏进程。

        blocking=False：给界面上的「强制关闭」按钮用。只发 kill，进程退出照常走
                        finished 信号，解锁与页面回退由既有的生命周期逻辑收尾。
        blocking=True ：给启动器退出用。先断开全部信号再强杀——退出时 UI 正在销毁，
                        finished / errorOccurred 里的回调打回去会碰到已经释放的窗口。
                        强杀后同步等进程真正退出——退出流程不会再回到事件循环，不能
                        指望异步的 finished 来收尾，实例锁也在这里自己放掉。

        返回 True 表示确实结束了一个在跑的进程。
        """
        try:
            if self.state() == QProcess.NotRunning:
                if blocking:
                    self._locker.unlock()
                return False
            _log.info("killing game process: pid=%s (blocking=%s)" % (self.processId(), blocking))
            if not blocking:
                self.kill()
                return True
            self._disconnect_signals()
            self.kill()
            if not self.waitForFinished(3000):
                _log.warning("game process still alive after 3s: pid=%s" % self.processId())
            self.going = 0
            self._locker.unlock()
            return True
        except Exception as e:
            _log.warning("kill game process failed: %r" % (e,))
            return False

    # ================== 数据目录 ==================
    def _prepare_data_dir(self):
        """准备游戏数据目录（<数据根>/Mindustry）：不存在则创建。

        不做旧布局（数据直接位于数据根下）的自动迁移：数据目录布局切换由使用者手动完成。
        """
        target = self.data["mdtData"]
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            self.log.emit({"type": "error", "text": "Prepare data directory failed: " + str(e)})

    # ================== Java 缺失的补救 ==================
    @staticmethod
    def _java_problem(java_path):
        """检查具体 Java 路径：可用返回 None，否则返回日志用的错误文本 key。"""
        if not os.path.exists(java_path):
            return "javaNotFound"
        if not javaManager.isJava(java_path):
            return "javaInvalid"
        return None

    def _resolve_java(self, mdt_name, java_path=None):
        """解析本次启动要用的 Java，返回 (路径, 错误 key)：错误 key 非空即不可用。

        显式传入的路径直接用；否则按实例配置解析——getMdtData 会把 FOLLOW 与
        自动匹配都落成具体路径，还是 FOLLOW 就说明一个 Java 也没解析出来。
        解析与校验的口径只此一份：启动流程用它，界面上的"提前拦"也用它。
        """
        if java_path is not None:
            # 显式传入 java_path 的情况
            java_path = javaManager.resolve(java_path)
            self.log.emit({"type": "info", "text": "Using explicit Java path: " + java_path})
            return java_path, self._java_problem(java_path)
        # 从 mdtManager 获取 BML 配置（含 javaPath 解析与回退）
        self.log.emit({"type": "info", "text": "Reading BML config via mdtManager for: " + mdt_name})
        try:
            mdt_data = self.root.mdtManager.getMdtData(mdt_name, self.settings)
            java_from_config = mdt_data.get("javaPath")
            # follow 表示无可用的 Java（mdtManager 已校验并写回），按缺失处理
            if not java_from_config or java_from_config == mdtManager.FOLLOW:
                raise ValueError("missing java path")
            self.log.emit({"type": "info", "text": "Java path from BML config: " + str(java_from_config)})
        except Exception:
            return None, "javaConfigInvalid"
        java_from_config = javaManager.resolve(java_from_config)
        return java_from_config, self._java_problem(java_from_config)

    def _java_unavailable(self, problem, mdt_name=None):
        """没有可用 Java 时的统一善后：先重扫一遍候选表，再决定要不要下载。

        候选表（settings["javaPaths"]）只在启动器启动时算过一次，用户中途装好
        JDK 后它还是旧的，照着它走会把"有 Java"误判成"没有 Java"，所以先重扫。
        重扫每次启动只做一次（_java_rescan_done）：重试后仍解析不出可用 Java
        就直接自动下载，不会在"重扫 → 重试 → 重扫"之间来回打转。
        重走启动必须延后到事件循环：此刻外层 _launch 还没返回，
        直接递归会被外层的 going 归零和 return False 覆盖掉。
        mdt_name：重试要启动的实例。启动流程里 self.data 已经填好，走"提前拦"
        过来时还没有，所以要显式传。
        """
        self.going = 0
        if not self._java_rescan_done:
            self._java_rescan_done = True
            try:
                javas = javaManager.getJavas()
            except Exception:
                javas = []
            if javas:
                self.settings["javaPaths"] = javas
                _log.info(_tr("log.info.javaRescanFound"))
                target = mdt_name or self.data.get("mdtName")
                if target:
                    QTimer.singleShot(0, lambda: self._launch(target))
                    return
            _log.info(_tr("log.info.javaRescanEmpty"))
        self.log.emit({"type": "error", "text": problem})
        self._auto_java_download()

    # ================== Java 自动下载 ==================
    def _auto_java_download(self):
        """Java 缺失/无效：切页显示"未检测到Java"并自动下载。

        首次缺失 → 发射 java_missing（UI 切到 Launch 页显示状态），
        创建 JavaDownloadFlow 自动下载，下载完成后自动重新启动游戏；
        已自动下载过一次仍缺失 → 发射 java_missing 并结束本次启动（防循环）。
        """
        if self._java_flow is not None:
            # 已有下载流程在运行（重复点击忽略，避免二次触发）
            return
        if self._java_download_attempts >= 1:
            # 已尝试过一次仍缺失，放弃并结束本次启动（game_finished 让 UI 回 Start 页）
            self.java_missing.emit()
            self._emit_finished(-1)
            return
        self._java_download_attempts += 1
        _log.info(_tr("log.info.javaAutoDlStart", self._java_download_attempts))
        self.java_missing.emit()
        try:
            from src.utils import javaDownload
        except ImportError:
            from . import javaDownload
        flow = javaDownload.JavaDownloadFlow(resume=False)
        self._java_flow = flow
        flow.status_changed.connect(self.java_status)
        flow.progress.connect(self.java_progress)
        flow.extract_progress.connect(self.java_extract_progress)
        flow.finished.connect(self._on_java_download_finished)
        flow.cancelled.connect(self._on_java_flow_cancelled)
        flow.paused_changed.connect(self.java_paused)
        flow.error.connect(lambda msg: self.log.emit({"type": "error", "text": _tr("log.error.javaDlErrorPrefix", str(msg))}))
        flow.start()

    def _on_java_flow_cancelled(self):
        """Java 下载被用户取消（下载列表页/退出时）：记录标记，结束时显示"已取消"。"""
        _log.info(_tr("log.info.javaAutoDlCancelled"))
        self._java_cancelled = True

    def _on_java_download_finished(self, ok):
        """Java 自动下载流程结束。

        成功 → 显示"Java部署完成"，一秒后刷新 Java 设置并重新启动游戏
        （重新检测 Java，能扫到新装的 JDK）；
        失败 → 结束本次启动（由 main 显示"下载失败"并回主界面）；
        被用户取消 → 由 main 显示"已取消"并回主界面（不误报"下载失败"）。
        """
        flow = self._java_flow
        self._java_flow = None
        if flow is not None:
            try:
                flow.shutdown()   # 确保下载/解压线程完全退出后再销毁对象
            except Exception:
                pass
            try:
                flow.deleteLater()
            except Exception:
                pass
        if not ok:
            # 失败/取消：不发射 lifecycle_finished（避免与状态显示抢切页），
            # 下次启动可重新尝试自动下载
            self._java_download_attempts = 0
            cancelled = self._java_cancelled
            self._java_cancelled = False
            _log.info(_tr("log.info.javaAutoDlFinished", ok, cancelled))
            if cancelled:
                self.java_cancelled.emit()   # main 显示"Java下载已取消"
            else:
                self.java_done.emit(False)   # main 显示"下载失败"
            return
        _log.info(_tr("log.info.javaAutoDlSuccess"))
        self.java_done.emit(ok)
        # 新装的 JDK 已经落在盘上：让 javaManager 子线程重扫一遍候选表
        # （扫完广播 changed，设置页/游戏管理页的 Java 选项跟着刷新；
        #  下面 _restart_after_java 拿到的就是这份新缓存）
        javaManager.scan()
        # 等待一秒让"Java部署完成"显示后再重新启动游戏
        QTimer.singleShot(1000, self._restart_after_java)

    def _restart_after_java(self):
        """Java 下载完成后：刷新 Java 设置并重新启动游戏。"""
        _log.info(_tr("log.info.javaAutoDlRestart"))
        try:
            # force：这里必须无视缓存重扫，否则可能拿到下载前那份旧候选表，
            # 新装的 JDK 就被跳过了（此处在子线程刚扫过之后，通常直接命中）
            javas = javaManager.getJavas(force=True)
            if javas:
                self.settings["javaPaths"] = javas
                # 与实例解析共用一套挑选口径（优先 17，其次最高版本）
                chosen = mdtManager.pickJava(javas)
                if chosen:
                    self.settings["javaPath"] = chosen
        except Exception:
            pass
        mdt_name = self.data.get("mdtName") or self.settings.get("defaultGame")
        if mdt_name:
            self.run(mdt_name)

    # ================== 异步事件槽 ==================
    def _on_started(self):
        self.going = 2
        self._java_download_attempts = 0   # 游戏成功启动：本次尝试结束，下次启动重新允许自动下载
        self.game_started.emit()

    def _on_finished(self, exitCode):
        # Qt6: QProcess.finished(int exitCode)，仅一个参数（Qt5 的 ExitStatus 已移除）
        # 退出码要落进日志：非 0 时 Windows 的异常码按有符号 int 读是负数
        # （0xC0000005 访问违例 = -1073741819），只看十进制认不出是什么，所以补一个十六进制。
        text = "process exit with %d" % exitCode
        if exitCode != 0:
            text += " (0x%08X)" % (exitCode & 0xFFFFFFFF)
        self.log.emit({"type": "info" if exitCode == 0 else "error", "text": text})
        self._emit_finished(exitCode)
        # 游戏进程真正结束：单独发出 game_finished（区别于生命周期结束）
        try:
            self.game_finished.emit(exitCode)
        except Exception:
            pass
        self.going = 0
        self._java_download_attempts = 0   # 游戏进程结束：生命周期结束，下次启动重新允许自动下载

    def _on_error(self, error):
        err_map = {
            QProcess.FailedToStart:  "processFailedToStart",
            QProcess.Crashed:        "processCrashed",
            QProcess.Timedout:       "processTimedout",
            QProcess.WriteError:     "processWriteError",
            QProcess.ReadError:      "processReadError",
            QProcess.UnknownError:   "processUnknownError"
        }
        msg = err_map.get(error, "processUnknownError")
        self.log.emit({"type": "error", "text": msg})
        self.going = 0
        self._emit_finished(-2)

    def _disconnect_signals(self):
        """断开启动时建立的信号连接，防止重复触发和干扰。

        逐个指定槽断开，不用无参 disconnect()：无参形式相当于从 None 接收者上
        断开，信号本就无连接时 libpyside 会打警告
        （Failed to disconnect (None) from signal ...），而警告不走异常，
        try/except 拦不住。
        """
        pairs = ((self.readyReadStandardOutput, self.on_stdout),
                 (self.readyReadStandardError, self.read_stderr),
                 (self.started, self._on_started),
                 (self.finished, self._on_finished),
                 (self.errorOccurred, self._on_error))
        for sig, slot in pairs:
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _emit_finished(self, code: int):
        """内部统一发出 lifecycle_finished 信号（只发一次），并做清理。"""
        # 先解锁：信号一发 UI 就回主界面，不能让残留的锁挡住随后的删除/更新操作
        try:
            self._locker.unlock()
        except Exception:
            pass
        if not getattr(self, '_finished_emitted', False):
            try:
                self.lifecycle_finished.emit(code)
            except Exception:
                pass
            self._finished_emitted = True
        try:
            self._disconnect_signals()
        except Exception:
            pass

    # ================== 日志输出 ==================
    # 子进程是 Windows 上的 JVM，System.out 按系统 ANSI 代码页写字节（简中下是 GBK），
    # 而日志文件是 UTF-8。固定按 UTF-8 解码会把整条中文行变成 �——游戏日志里的
    # 「UDP session 1 游戏回程 845890 包」就是这么丢的。改成灵活解码：按候选表逐个试，
    # ASCII 行与编码无关、哪条都能解，只有非 ASCII 行才区分得出来，第一个解得通的胜出，
    # 全解不了才 replace 兜底。mbcs 就是 Windows 的 ANSI 代码页本身，
    # 比 locale.getpreferredencoding() 稳——后者会被 Python 的 UTF-8 模式改成 utf-8。
    # 注意：某串字节同时是两种编码的合法序列时无从分辨，只能认先命中的那条。
    _ENCODINGS = ("utf-8", "mbcs", "gbk")

    def _decode(self, raw: bytes) -> str:
        """灵活解码一段子进程输出；候选编码全试完仍失败才按 UTF-8 替换，永不抛异常。"""
        for enc in self._ENCODINGS:
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    def on_stdout(self):
        while self.canReadLine():
            line = self._decode(self.readLine().data()).strip()
            if line:
                self.game_log.emit({"type": "info", "text": line})

    def read_stderr(self):
        while self.canReadLine():
            line = self._decode(self.readLine().data()).strip()
            if line:
                self.game_log.emit({"type": "error", "text": line})