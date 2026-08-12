import os
from PyQt5.QtCore import QProcess, QProcessEnvironment, QTimer, pyqtSignal

from .path_utils import getPath
from .mdtScanner import mdtScanner
from .javaScanner import javaScanner


class mdtLauncher(QProcess):
    game_launched = pyqtSignal()       # 已开始尝试启动
    game_started = pyqtSignal()        # 进程已成功开始运行
    game_finished = pyqtSignal(int)    # 进程结束，传出退出码
    game_log = pyqtSignal(dict)        # 进程输出日志，dict: {"type":"info"/"error", "text":...}
    log = pyqtSignal(dict)             # 通用日志信号（启动阶段 info/error）
    java_missing = pyqtSignal()        # Java 缺失/无效（UI 据此切页显示"未检测到Java"）
    java_status = pyqtSignal(str)      # Java 下载流程状态：downloading/extracting/done/error
    java_progress = pyqtSignal(int, int)      # Java 下载进度（已下载字节, 总字节）
    java_extract_progress = pyqtSignal(int, int)  # Java 解压/部署进度
    java_done = pyqtSignal(bool)       # Java 下载流程结束（True 成功 / False 失败）

    def __init__(self, parent=None, settings=None):
        super().__init__()
        self.envs = QProcessEnvironment.systemEnvironment()
        self.going = 0   # 0: 空闲, 1: 校验中/准备启动, 2: 进程运行中
        self.data = {}   # 本次启动的关键路径信息
        self.settings = settings or {}
        self._finished_emitted = False
        self._java_flow = None                 # Java 自动下载流程实例
        self._java_download_attempts = 0       # 自动下载尝试次数（防循环；游戏启动/结束时重置）

    def _launch(self, mdt_name, java_path=None, args=None, data_path=None):
        """
        校验参数并启动 Mindustry 服务端（异步）。
        返回 True 表示启动指令已发出，False 表示启动前校验失败。
        进程的实际启动、运行、结束都通过信号通知。
        """
        # 生命周期开始
        self._finished_emitted = False
        self.game_launched.emit()

        # ---------- 并发保护 ----------
        if self.going:
            self.log.emit({"type": "error", "text": "gameRunning"})
            self._emit_finished(-1)
            return False
        self.going = 1
        self.log.emit({"type": "info", "text": "Launch preparation started for: " + mdt_name})

        # ---------- 初始化 data ----------
        self.data = {
            "mdtName": None,
            "mdtPath": None,
            "mdtJar": None,
            "mdtData": None,
            "javaPath": None,
            "args": None
        }

        # ---------- 1. 检查 mdt 实例 ----------
        if mdt_name not in mdtScanner.getMdts():
            self.log.emit({"type": "error", "text": "mdtNotFound"})
            self.going = 0
            self._emit_finished(-1)
            return False

        self.data["mdtName"] = mdt_name
        self.data["mdtPath"] = os.path.join(getPath("BML/.Mindustrys"), mdt_name)
        self.data["mdtJar"] = os.path.join(self.data["mdtPath"], "mdt.jar")
        self.log.emit({"type": "info", "text": "MDT instance found: " + mdt_name})

        # ---------- 2. 确定数据目录 ----------
        if data_path is None:
            self.data["mdtData"] = os.path.join(self.data["mdtPath"], "data")
            self.log.emit({"type": "info", "text": "Using default data directory: " + self.data["mdtData"]})
        else:
            try:
                self.data["mdtData"] = os.path.abspath(data_path)
                self.log.emit({"type": "info", "text": "Using custom data directory: " + self.data["mdtData"]})
            except Exception:
                self.log.emit({"type": "error", "text": "mdtDataError"})
                self.going = 0
                self._emit_finished(-1)
                return False

        # ---------- 3. 确定 Java 路径 ----------
        if java_path is not None:
            # 显式传入 java_path 的情况
            self.log.emit({"type": "info", "text": "Using explicit Java path: " + java_path})
            if not os.path.exists(java_path):
                self.log.emit({"type": "error", "text": "javaNotFound"})
                self.going = 0
                self._auto_java_download()
                return False
            
            if not javaScanner.isJava(java_path):
                self.log.emit({"type": "error", "text": "javaInvalid"})
                self.going = 0
                self._auto_java_download()
                return False
                
            self.data["javaPath"] = java_path
            self.log.emit({"type": "info", "text": "Java path validated: " + java_path})
        else:
            # 从 mdtScanner 获取 BML 配置（含 javaPath 解析与回退）
            self.log.emit({"type": "info", "text": "Reading BML config via mdtScanner for: " + mdt_name})
            try:
                mdt_data = mdtScanner.getMdtData(mdt_name, self.settings)
                java_from_config = mdt_data.get("javaPath")
                # follow 表示无可用的 Java（mdtScanner 已校验并写回），按缺失处理
                if not java_from_config or java_from_config == "<:|follow|:>":
                    raise ValueError("missing java path")
                self.log.emit({"type": "info", "text": "Java path from BML config: " + str(java_from_config)})
            except Exception:
                self.log.emit({"type": "error", "text": "javaConfigInvalid"})
                self.going = 0
                self._auto_java_download()
                return False

            if not os.path.exists(java_from_config):
                self.log.emit({"type": "error", "text": "javaNotFound"})
                self.going = 0
                self._auto_java_download()
                return False

            if not javaScanner.isJava(java_from_config):
                self.log.emit({"type": "error", "text": "javaInvalid"})
                self.going = 0
                self._auto_java_download()
                return False

            self.data["javaPath"] = java_from_config
            self.log.emit({"type": "info", "text": "Java path validated: " + java_from_config})

        self.data["args"] = args if args else []
        self.log.emit({"type": "info", "text": "Launch args: " + str(self.data["args"])})

        # ---------- 4. 设置进程环境 ----------
        self.envs.insert("MINDUSTRY_DATA_DIR", self.data["mdtData"])
        self.setProcessEnvironment(self.envs)
        self.setProcessChannelMode(QProcess.SeparateChannels)

        # ---------- 5. 连接信号（先断开避免重复） ----------
        self._disconnect_signals()
        self.readyReadStandardOutput.connect(self.on_stdout)
        self.readyReadStandardError.connect(self.read_stderr)
        self.started.connect(self._on_started)
        self.finished.connect(self._on_finished)
        self.errorOccurred.connect(self._on_error)

        # ---------- 6. 启动（异步） ----------
        self.log.emit({"type": "info", "text": "Starting process: " + self.data["javaPath"] + " -jar " + self.data["mdtJar"]})
        self.start(self.data["javaPath"],
                   self.data["args"] + ["-jar", self.data["mdtJar"]])
        return True

    def run(self, mdt_name, java_path=None, args=None, data_path=None):
        """对外接口：启动服务端（异步），不阻塞调用线程。"""
        self._launch(mdt_name, java_path, args, data_path)

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
        flow.error.connect(lambda msg: self.log.emit({"type": "error", "text": "[Java下载]" + str(msg)}))
        flow.start()

    def _on_java_download_finished(self, ok):
        """Java 自动下载流程结束。

        成功 → 显示"Java部署完成"，一秒后刷新 Java 设置并重新启动游戏
        （重新检测 Java，能扫到新装的 JDK）；
        失败 → 结束本次启动（由 main 显示"下载失败"并回主界面）。
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
        self.java_done.emit(ok)
        if not ok:
            # 失败：不发射 game_finished（避免与 error 状态显示抢切页），
            # 由 main 的 java_done 处理显示"下载失败"并 1 秒后回主界面
            self._java_download_attempts = 0   # 下载失败/取消：下次启动可重新尝试自动下载
            return
        # 等待一秒让"Java部署完成"显示后再重新启动游戏
        QTimer.singleShot(1000, self._restart_after_java)

    def _restart_after_java(self):
        """Java 下载完成后：刷新 Java 设置并重新启动游戏。"""
        try:
            javas = javaScanner.getJavas()
            if javas:
                self.settings["javaPaths"] = javas
                chosen = next((j for j in javas if j[1].startswith("17.")), None) or javas[0]
                self.settings["javaPath"] = chosen[0]
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

    def _on_finished(self, exitCode, exitStatus):
        self._emit_finished(exitCode)
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
        """断开所有内部信号连接，防止重复触发和干扰。"""
        for sig in (self.readyReadStandardOutput,
                    self.readyReadStandardError,
                    self.started,
                    self.finished,
                    self.errorOccurred):
            try:
                sig.disconnect()
            except TypeError:
                pass

    def _emit_finished(self, code: int):
        """内部统一发出 finished 信号（只发一次），并做清理。"""
        if not getattr(self, '_finished_emitted', False):
            try:
                self.game_finished.emit(code)
            except Exception:
                pass
            self._finished_emitted = True
        try:
            self._disconnect_signals()
        except Exception:
            pass

    # ================== 日志输出 ==================
    def on_stdout(self):
        while self.canReadLine():
            line = self.readLine().data().decode("utf-8", errors="replace").strip()
            if line:
                self.game_log.emit({"type": "info", "text": line})

    def read_stderr(self):
        while self.canReadLine():
            line = self.readLine().data().decode("utf-8", errors="replace").strip()
            if line:
                self.game_log.emit({"type": "error", "text": line})