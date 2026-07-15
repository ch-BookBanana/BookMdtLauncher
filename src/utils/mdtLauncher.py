import os
import json
from PyQt5.QtCore import QProcess, QProcessEnvironment, pyqtSignal

from .path_utils import getPath
from .mdtScanner import mdtScanner
from .javaScanner import javaScanner


class mdtLauncher(QProcess):
    game_launched = pyqtSignal()       # 已开始尝试启动
    game_started = pyqtSignal()        # 进程已成功开始运行
    game_finished = pyqtSignal(int)    # 进程结束，传出退出码
    game_log = pyqtSignal(dict)        # 进程输出日志，dict: {"type":"info"/"error", "text":...}
    log = pyqtSignal(dict)             # 通用日志信号（启动阶段 info/error）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.envs = QProcessEnvironment.systemEnvironment()
        self.going = 0   # 0: 空闲, 1: 校验中/准备启动, 2: 进程运行中
        self.data = {}   # 本次启动的关键路径信息
        self._finished_emitted = False

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
                self._emit_finished(-1)
                return False
            
            if not javaScanner.isJava(java_path):
                self.log.emit({"type": "error", "text": "javaInvalid"})
                self.going = 0
                self._emit_finished(-1)
                return False
                
            self.data["javaPath"] = java_path
            self.log.emit({"type": "info", "text": "Java path validated: " + java_path})
        else:
            # 从配置文件读取 java_path 的情况
            bml_config = os.path.join(self.data["mdtPath"], "BML.json")
            self.log.emit({"type": "info", "text": "Reading Java config from: " + bml_config})
            if not os.path.exists(bml_config):
                self.log.emit({"type": "error", "text": "javaConfigNotFound"})
                self.going = 0
                self._emit_finished(-1)
                return False

            try:
                with open(bml_config, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.log.emit({"type": "info", "text": "BML.json loaded successfully"})

                    java_from_config = config.get("javaPath")

                    if not java_from_config:
                        raise ValueError("missing java path")
                    self.log.emit({"type": "info", "text": "Java path from config: " + str(java_from_config)})
                    java_from_config = os.path.expandvars(str(java_from_config))
                    if not os.path.isabs(java_from_config):
                        java_from_config = os.path.join(self.data["mdtPath"], java_from_config)
                        self.log.emit({"type": "info", "text": "Resolved relative Java path to: " + java_from_config})
            except Exception:
                self.log.emit({"type": "error", "text": "javaConfigInvalid"})
                self.going = 0
                self._emit_finished(-1)
                return False

            if not os.path.exists(java_from_config):
                self.log.emit({"type": "error", "text": "javaNotFound"})
                self.going = 0
                self._emit_finished(-1)
                return False

            if not javaScanner.isJava(java_from_config):
                self.log.emit({"type": "error", "text": "javaInvalid"})
                self.going = 0
                self._emit_finished(-1)
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

    # ================== 异步事件槽 ==================
    def _on_started(self):
        self.going = 2
        self.game_started.emit()

    def _on_finished(self, exitCode, exitStatus):
        self._emit_finished(exitCode)
        self.going = 0

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