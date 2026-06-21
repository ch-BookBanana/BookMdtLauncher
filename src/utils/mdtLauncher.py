import os
import json
from PyQt5.QtCore import QProcess, QProcessEnvironment, pyqtSignal

from .mdtScanner import mdtScanner
from .javaScanner import javaScanner


class mdtLauncher(QProcess):
    game_launched = pyqtSignal()       # 已开始尝试启动
    game_started = pyqtSignal()        # 进程已成功开始运行
    game_finished = pyqtSignal(int)    # 进程结束，传出退出码
    game_log = pyqtSignal(dict)        # 进程输出日志，dict: {"type":"info"/"error", "text":...}
    game_error = pyqtSignal(dict)      # 启动前或运行时的致命错误，dict: {"type":"error", "text":...}
    log = pyqtSignal(dict)             # 预留的通用日志信号（保持兼容）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.envs = QProcessEnvironment.systemEnvironment()
        self.going = 0   # 0: 空闲, 1: 校验中/准备启动, 2: 进程运行中
        self.data = {}   # 本次启动的关键路径信息

    def _launch(self, mdt_name, java_path=None, args=None, data_path=None):
        """
        校验参数并启动 Mindustry 服务端（异步）。
        返回 True 表示启动指令已发出，False 表示启动前校验失败。
        进程的实际启动、运行、结束都通过信号通知。
        """
        self.game_launched.emit()

        # ---------- 并发保护 ----------
        if self.going:
            self.game_error.emit({"type": "error", "text": "gameRunning"})
            return False
        self.going = 1

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
            self.game_error.emit({"type": "error", "text": "mdtNotFound"})
            self.going = 0
            return False

        self.data["mdtName"] = mdt_name
        self.data["mdtPath"] = os.path.abspath(
            os.path.join("BML", ".Mindustrys", mdt_name)
        )
        self.data["mdtJar"] = os.path.join(self.data["mdtPath"], "mdt.jar")

        # ---------- 2. 确定数据目录 ----------
        if data_path is None:
            self.data["mdtData"] = os.path.join(self.data["mdtPath"], "data")
        else:
            try:
                self.data["mdtData"] = os.path.abspath(data_path)
            except Exception:
                self.game_error.emit({"type": "error", "text": "mdtDataError"})
                self.going = 0
                return False

        # ---------- 3. 确定 Java 路径 ----------
        if java_path is not None:
            if not javaScanner.isJava(java_path):
                self.game_error.emit({"type": "error", "text": "javaError"})
                self.going = 0
                return False
            self.data["javaPath"] = java_path
        else:
            bml_config = os.path.join(self.data["mdtPath"], "BML.json")
            try:
                with open(bml_config, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    java = cfg.get("javaFile")
                    if not java or not javaScanner.isJava(java):
                        raise ValueError("Invalid java path")
                    self.data["javaPath"] = java
            except Exception:
                self.game_error.emit({"type": "error", "text": "javaError"})
                self.going = 0
                return False

        self.data["args"] = args if args else []

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
        self.game_finished.emit(exitCode)
        self.going = 0
        self._disconnect_signals()

    def _on_error(self, error):
        err_map = {
            QProcess.FailedToStart: "processFailedToStart",
            QProcess.Crashed:        "processCrashed",
            QProcess.Timedout:       "processTimedout",
            QProcess.WriteError:     "processWriteError",
            QProcess.ReadError:      "processReadError",
            QProcess.UnknownError:   "processUnknownError"
        }
        msg = err_map.get(error, "processUnknownError")
        self.game_error.emit({"type": "error", "text": msg})
        self.going = 0
        self._disconnect_signals()

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