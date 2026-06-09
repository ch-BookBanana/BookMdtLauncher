# src/utils/mdtLauncher.py
import os
import json
from PyQt5.QtCore import QProcess, QProcessEnvironment, pyqtSignal

from .mdtScanner import mdtScanner
from .javaScanner import javaScanner

class mdtLauncher(QProcess):
    """
    游戏副本启动器
    支持用户主动设置 Java 路径和数据目录（覆盖配置文件中的设置）
    若用户设置的数据目录不存在，会自动创建。
    """
    info_ready = pyqtSignal(dict)
    output_ready = pyqtSignal(dict)
    error_ready = pyqtSignal(dict)
    process_started = pyqtSignal(dict)
    process_finished = pyqtSignal(dict)
    process_error = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "idle"               # idle, running
        self._current_game = None

        # 双变量机制
        self.user_settings = {
            "java_path": None,      # 用户指定的 Java 可执行文件路径（绝对路径）
            "data_dir": None,       # 用户指定的数据目录（绝对路径）
        }
        self.runtime_settings = {
            "java_path": None,
            "data_dir": None,
            "jar_path": None,
        }

        # 连接 Qt 信号
        self.readyReadStandardOutput.connect(self._on_stdout)
        self.readyReadStandardError.connect(self._on_stderr)
        self.started.connect(self._on_started)
        self.finished.connect(self._on_finished)
        self.errorOccurred.connect(self._on_process_error)

    # ---------- 用户设置接口 ----------
    def setJavaPath(self, java_path: str):
        """设置用户首选的 Java 路径（绝对路径）"""
        if java_path is None:
            self.user_settings["java_path"] = None
        elif os.path.isfile(java_path):
            self.user_settings["java_path"] = java_path
        else:
            self.process_error.emit({'type': 'process_error', 'content': f'Invalid Java path: {java_path}'})

    def setDataDir(self, data_dir: str):
        """设置用户首选的游戏数据目录（绝对路径），如果目录不存在会在启动时自动创建"""
        if data_dir is None:
            self.user_settings["data_dir"] = None
        else:
            # 不检查是否存在，留给 launch 时创建
            self.user_settings["data_dir"] = os.path.abspath(data_dir)

    # ---------- 静态工具 ----------
    @staticmethod
    def getGames():
        """返回所有有效游戏副本的名称列表（直接复用 mdtScanner）"""
        return mdtScanner.getMdts()

    # ---------- 状态查询 ----------
    def getStatus(self):
        """返回当前状态字典"""
        return {
            "state": self._state,
            "game_name": self._current_game,
            "user_java": self.user_settings.get("java_path"),
            "user_data_dir": self.user_settings.get("data_dir"),
            "runtime_java": self.runtime_settings.get("java_path"),
            "runtime_data_dir": self.runtime_settings.get("data_dir"),
            "runtime_jar": self.runtime_settings.get("jar_path"),
        }

    # ---------- 启动游戏 ----------
    def launch(self, game_name: str) -> bool:
        """
        启动指定名称的游戏副本。
        优先级：
          - Java 路径：user_settings["java_path"] > BML.json 中的 javaFile
          - 数据目录：若 user_settings["data_dir"] 存在，则确保该目录存在（自动创建），使用它；
                     否则使用游戏副本目录（mdt.jar 所在目录）作为数据目录。
        """
        if self._state != "idle":
            self.process_error.emit({'type': 'process_error', 'content': f'Launcher busy (state={self._state})'})
            return False

        # 1. 验证游戏名称有效性
        valid_games = mdtScanner.getMdts()
        if game_name not in valid_games:
            self.process_error.emit({'type': 'process_error', 'content': f'Invalid game name: {game_name}. Available: {valid_games}'})
            return False

        # 2. 构建基本路径（使用绝对路径）
        game_dir = os.path.join(mdtScanner.base_dir, game_name)
        jar_path = os.path.abspath(os.path.join(game_dir, "mdt.jar"))
        json_path = os.path.join(game_dir, "BML.json")

        if not os.path.isfile(jar_path):
            self.process_error.emit({'type': 'process_error', 'content': f'mdt.jar not found: {jar_path}'})
            return False

        # 3. 确定 Java 路径
        java_path = None
        if self.user_settings.get("java_path") and os.path.isfile(self.user_settings["java_path"]):
            java_path = self.user_settings["java_path"]
        else:
            if not os.path.isfile(json_path):
                self.process_error.emit({'type': 'process_error', 'content': f'BML.json not found: {json_path}'})
                return False
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                java_path = config.get("javaFile")
                if not java_path or not isinstance(java_path, str):
                    self.process_error.emit({'type': 'process_error', 'content': 'BML.json missing "javaFile" field or value is null'})
                    return False
                if not os.path.isfile(java_path):
                    self.process_error.emit({'type': 'process_error', 'content': f'Java executable not found: {java_path}'})
                    return False
            except Exception as e:
                self.process_error.emit({'type': 'process_error', 'content': f'Failed to read BML.json: {str(e)}'})
                return False

        # 验证 Java 版本
        version = javaScanner.getJavaVersion(java_path)
        if not version:
            self.process_error.emit({'type': 'process_error', 'content': f'Invalid Java or cannot get version: {java_path}'})
            return False

        # 4. 确定数据目录
        user_data_dir = self.user_settings.get("data_dir")
        if user_data_dir is not None:
            # 用户指定了数据目录
            data_dir = os.path.abspath(user_data_dir)
            # 确保目录存在，自动创建
            try:
                os.makedirs(data_dir, exist_ok=True)
                self.info_ready.emit({'type': 'info', 'content': f'Ensured user data directory exists: {data_dir}'})
            except Exception as e:
                self.process_error.emit({'type': 'process_error', 'content': f'Failed to create user data directory {data_dir}: {str(e)}'})
                return False
        else:
            # 用户未指定，使用默认的游戏副本目录
            data_dir = game_dir
            if not os.path.isdir(data_dir):
                self.process_error.emit({'type': 'process_error', 'content': f'Default data directory does not exist: {data_dir}'})
                return False

        # 5. 记录运行时设置
        self._current_game = game_name
        self.runtime_settings = {
            "java_path": java_path,
            "data_dir": data_dir,
            "jar_path": jar_path,
        }
        self._state = "running"

        self.info_ready.emit({'type': 'info', 'content': f'Launching {game_name} with Java {version}'})
        self.info_ready.emit({'type': 'info', 'content': f'Data directory: {data_dir}'})
        self.info_ready.emit({'type': 'info', 'content': f'JAR path: {jar_path}'})

        # 6. 设置环境变量和工作目录
        env = QProcessEnvironment.systemEnvironment()
        env.insert("MINDUSTRY_DATA_DIR", data_dir)
        self.setProcessEnvironment(env)
        self.setWorkingDirectory(data_dir)   # 工作目录设为数据目录

        # 7. 启动进程（使用绝对路径的 jar）
        args = ["-jar", jar_path]
        self.start(java_path, args)
        if not self.waitForStarted(5000):
            self._state = "idle"
            self.process_error.emit({'type': 'process_error', 'content': 'Process start timeout'})
            return False
        return True

    # ---------- 停止游戏 ----------
    def stop(self):
        if self._state == "running":
            self.info_ready.emit({'type': 'info', 'content': 'Stopping game...'})
            self.terminate()
            if not self.waitForFinished(3000):
                self.kill()
                self.info_ready.emit({'type': 'info', 'content': 'Game process killed'})

    # ---------- 内部信号处理 ----------
    def _on_stdout(self):
        data = self.readAllStandardOutput()
        if data:
            text = bytes(data).decode('utf-8', errors='replace')
            if text:
                self.output_ready.emit({'type': 'output', 'content': text})

    def _on_stderr(self):
        data = self.readAllStandardError()
        if data:
            text = bytes(data).decode('utf-8', errors='replace')
            if text:
                self.error_ready.emit({'type': 'error', 'content': text})

    def _on_started(self):
        self.process_started.emit({'type': 'started', 'content': f'Game {self._current_game} started'})

    def _on_finished(self, exitCode, exitStatus):
        status_str = "Normal" if exitStatus == QProcess.NormalExit else "Crash"
        content = f'Game finished with code {exitCode}, status {status_str}'
        self.process_finished.emit({'type': 'finished', 'content': content})
        # 重置状态
        self._state = "idle"
        self._current_game = None
        self.runtime_settings = {"java_path": None, "data_dir": None, "jar_path": None}

    def _on_process_error(self, error):
        error_map = {
            QProcess.FailedToStart: "Failed to start",
            QProcess.Crashed: "Crashed",
            QProcess.Timedout: "Timeout",
            QProcess.WriteError: "Write error",
            QProcess.ReadError: "Read error",
            QProcess.UnknownError: "Unknown error"
        }
        msg = error_map.get(error, f"Error code {error}")
        self.process_error.emit({'type': 'process_error', 'content': msg})
        if self._state != "idle":
            self._state = "idle"
            self._current_game = None
            self.runtime_settings = {"java_path": None, "data_dir": None, "jar_path": None}