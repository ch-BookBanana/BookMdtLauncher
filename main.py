# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 BookBanana
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
"""
版本信息见上方英文，以下为中文摘要：
本程序为自由软件，您可以根据GNU通用公共许可证的条款重新分发和修改它，许可证版本为3或（由您选择）更高版本。
本程序的发布目的是希望它能有用，但不提供任何保证，包括但不限于适销性或特定用途的适用性的隐含保证。有关更多细节，请参阅GNU通用公共许可证。
您应该已经收到GNU通用公共许可证的副本，如果没有，请访问http://www.gnu.org/licenses/。
"""
try:
    init = {
        "version": "26-T0818",
        "BuildCode": "10000.01"
    }

    from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QSize, QByteArray, Signal
    from PySide6.QtGui import (
        QColor, QPixmap, QPainter, QIcon, QFont, QFontMetrics, QPainterPath, QCursor, QAction, QTextOption
    )
    from PySide6.QtWidgets import (
        QWidget, QScrollBar, QApplication, QHBoxLayout, QVBoxLayout, QStackedWidget, QLineEdit, QPushButton, QLabel,
        QFrame, QScrollArea, QButtonGroup,QSystemTrayIcon, QMenu, QDialog, QTextEdit, QProgressBar
    )
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    import sys, os, json, copy, winreg, logging, locale, base64, time, shutil, traceback, webbrowser
    from datetime import datetime
    import ctypes
    import ctypes.wintypes
    from src.utils.path_utils import getPath
    from src.utils.mdtScanner import mdtScanner
    from src.utils.mdtLauncher import mdtLauncher, set_tr_func as mdt_set_tr_func
    from src.utils.QThTimer import QThTimer
    from src.utils.api.githubAPI import GithubAPI
    from src.utils import javaDownload
    from src.utils.QDownloader import QDownloader

    from src.utils.utils import _is_mdt_download, change_color, t
    from src.utils.on_start import startup


    class Main():
        def __init__(self,app):
            self.app = app
        
            # 全局拦截滚动条右键菜单
            class _ScrollBarFilter(QObject):
                def eventFilter(self, obj, event):
                    if event.type() == QEvent.ContextMenu and isinstance(obj, QScrollBar):
                        return True
                    return super().eventFilter(obj, event)
            self._scroll_bar_filter = _ScrollBarFilter()
            self.app.installEventFilter(self._scroll_bar_filter)

            for i in [
                "BML",
                "BML/logs",
                "BML/.Mindustrys"
            ]:
                os.makedirs(getPath(i), exist_ok=True)
            self.signals = self.Signals(self,self)
            self.winreg = self.Winreg(self, self)
            self.logger = self.Logger(self, self)
            self.logger.info("\n------------Book MDT Launcher------------"
                            f"\n-time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
                            f"\n-version: {init['version']}"
                            f"\n-BuildVersion: {init['BuildCode']}"
                            "\n-----------------------------------------")
            self.defsettings = {
                "language": None,
                "theme": 0,
                "maxLogNum": 50,
                "closeByTray": True,
                "defaultGame": None,
                "javaPath": None,
                "github": {
                    "token_enc":None,
                    "token_key":None,
                    "useful": None,
                    "user":{
                        "name":None,
                        "headurl":None
                    },
                    "rate": {
                        "core":   {"remaining": None, "reset": []},
                        "search": {"remaining": None, "reset": []}
                    }
                },
                "javaPaths": [],
                "gameList": {"<:|default|:>": []}
            }
            self.settings = copy.deepcopy(self.defsettings)
            app.aboutToQuit.connect(self.saveSettings)

            def deep_merge_settings(default, file_settings):
                for key, value in file_settings.items():
                    if key not in default:
                        continue
                    if isinstance(default[key], dict) and isinstance(value, dict):
                        deep_merge_settings(default[key], value)
                    else:
                        default[key] = value

            try:
                settings_path = getPath("BML/settings.json")
                if not os.path.exists(settings_path):
                    self.logger.warning("settings file not found, using default settings")
                else:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        self.logger.info("loading settings...")
                        file_settings = json.load(f)
                        deep_merge_settings(self.settings, file_settings)
            except Exception as e:
                self.logger.error("ERR:Fail to load settings, using default setting"
                                "\n--Exception: " + str(e), exc_info=True)
                self.settings = copy.deepcopy(self.defsettings)
                try:
                    with open(settings_path, "r", encoding="utf-8") as f:
                        self.logger.warning("Error setting: \n" + str(e), exc_info=True)
                except:
                    pass

            self.langer = self.Langer(self, self)
            # 工具模块日志 i18n：注入 langer.get 翻译函数（未注入时日志回退为 key 本身）
            javaDownload.set_tr_func(self.langer.get)
            mdt_set_tr_func(self.langer.get)
            self.logger._cleanup_old_logs()

            self.saveSettings()


            self.launcher = mdtLauncher(self, self.settings)
            self.githubAPI = GithubAPI()
            # settings 传 dict；parent 必须 QObject（Main 不是，传 None）；root 存 Main 引用
            self.mdtScanner = mdtScanner(self.settings, parent=None, root=self)
            # checkGame 变更 gameList（newGame/deleteGame/nameChanged）后自动落盘
            self.mdtScanner.on_game_changed.connect(self._on_game_changed)
            # 启动立即同步一次游戏列表，避免等首个 3 秒周期
            QThTimer.task(0, lambda e: self.mdtScanner.checkGame())
            if self.settings["github"]["token_enc"]:
                raw = self._decrypt_settings_token()
                if raw:
                    self.githubAPI.setToken(raw)
                QThTimer.task(
                    0,
                    lambda e: self.githubAPI.checkToken(),
                    result_callback=self._on_startup_rate_check,
                    dedicated=True   # 网络任务走独立线程，避免阻塞 QThTimer 共享线程（卡死所有 taskP）
                )


            self.signals.register("tokenVerified", Signal(bool, str, object))

            self.tray = self.Tray(self, self)
            self.window = self.Window(self, self)

            # 后台预加载所有游戏数据到缓存，加速后续切换
            QThTimer.task(100, lambda event: self.mdtScanner.preload_all())
            # 图标周期检查与 QPixmaps 引用计数缓存已由 mdtScanner 自管理（icon_timer）

            # 退出统一清理：先停下载/后台线程（避免退出挂起与崩溃弹窗）
            app.aboutToQuit.connect(self._cleanup_on_quit)

            # Java 下载流程的 UI 回调/辅助函数由 src/utils/on_start/java.py 挂载（保持 self._java_* 调用点不变）
            from src.utils.on_start.java import attach as _attach_java_ui
            _attach_java_ui(self)

            startup.register(self)

        def _on_game_changed(self, data):
            """mdtScanner 事件回调（主线程）。

            newGame/deleteGame/nameChanged → gameList 变化，落盘；
            iconChanged → 图标文件变化，失效 QPixmaps 缓存（下次引用重新加载）。
            UI 刷新由 start.py 直接订阅 on_game_changed 完成，不经 signals 中转。"""
            etype = data.get("type")
            if etype in ("newGame", "deleteGame", "nameChanged"):
                self.saveSettings()
            elif etype == "iconChanged":
                mdtScanner.invalidate_icon_pixmap(data.get("game"))

        def _cleanup_on_quit(self):
            """应用退出前的统一清理（aboutToQuit 时执行）。

            顺序：隐藏托盘 → 停止下载线程 → 停止 QThTimer 后台线程 → 清理图片缓存。
            QThTimer.shutdown() 在模块内也连接了 aboutToQuit，重复调用是幂等的。
            """
            try:
                self.tray.hide()
            except Exception:
                pass
            # 取消 Java 下载/解压流程（保留 javaDownload.json，下次启动续传）
            try:
                self._java_cancel_all()
            except Exception:
                pass
            try:
                from src.utils.QDownloader import shutdown_all as _qd_shutdown_all
                _qd_shutdown_all()
            except Exception:
                pass
            try:
                QThTimer.shutdown()
            except Exception:
                pass
            # 删除 markdown 图片缓存（mdimg），下次渲染时重新下载
            try:
                import shutil
                mdimg = getPath("BML/.tmp/mdimg")
                if os.path.isdir(mdimg):
                    shutil.rmtree(mdimg, ignore_errors=True)
            except Exception:
                pass

        _OBF_BYTE = 0x5A

        @classmethod
        def _obf_store(cls, s):
            """固定 XOR → base64，settings 存储前混淆"""
            return base64.b64encode(
                bytes(b ^ cls._OBF_BYTE for b in s.encode())
            ).decode()

        @classmethod
        def _deobf_store(cls, s):
            """逆向：base64 解码 → XOR 还原"""
            b = base64.b64decode(s)
            return bytes(byte ^ cls._OBF_BYTE for byte in b).decode()

        def _encrypt_settings_token(self, raw):
            enc, key = GithubAPI._encrypt(raw)
            self.settings["github"]["token_enc"] = Main._obf_store(enc)
            self.settings["github"]["token_key"] = Main._obf_store(key)

        def _decrypt_settings_token(self):
            return GithubAPI._decrypt(
                Main._deobf_store(self.settings["github"]["token_enc"]),
                Main._deobf_store(self.settings["github"]["token_key"])
            )

        def _on_startup_rate_check(self, result):
            ok, error_type, data = result
            if ok:
                rate = self.githubAPI.rate
                s = self.settings["github"]
                s["rate"]["core"] = {"remaining": rate["core"]["remaining"], "reset": rate["core"]["reset"]}
                s["rate"]["search"] = {"remaining": rate["search"]["remaining"], "reset": rate["search"]["reset"]}
                s["useful"] = True
            elif error_type == "auth":
                self.githubAPI.setToken(None)
                s = self.settings["github"]
                s["token_enc"] = None
                s["token_key"] = None
                s["useful"] = None
                s["user"] = {"name": None, "headurl": None}
            self.saveSettings()
            self.signals.emit("tokenVerified", ok, error_type, data)

        def setTheme(self,theme):
            self.settings["theme"] = 1 if theme else 0
            self.apply_theme()

        def saveSettings(self):
            try:
                settings_path = getPath("BML/settings.json")
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, separators=(',', ':'), ensure_ascii=False)
                try:
                    self.logger.info(self.langer.get("log.info.savesettings"))
                except:
                    self.logger.info("Settings saved")
            except Exception as e:
                try:
                    self.logger.error(self.langer.get("log.error.savesettings") + "\n--Exception: " + str(e), exc_info=True)
                except:
                    self.logger.error("Failed to save settings\n--Exception: " + str(e), exc_info=True)

        def apply_theme(self):
            is_light = bool(self.settings["theme"])
            theme_file = "light.qss" if is_light else "dark.qss"

            qss = ""
            with open(getPath(f"src/resources/styles/{theme_file}"), "r", encoding="utf-8") as f:
                qss = f.read()

            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)
                self.logger.debug(f"Loading QtStyleSheet from {theme_file}:\n{qss} ")

            font = QFont()
            font.setFamily("Microsoft Yahei")
            font.setPointSize(8)
            app.setFont(font)

            # 递归调用所有子控件的 lighting 函数（图标换色）
            def notify_lighting(widget, state):
                if hasattr(widget, 'lighting') and callable(widget.lighting):
                    try:
                        widget.lighting(state)
                    except Exception as e:
                        self.logger.error(f"Error calling lighting on {widget}: {e}")
                for child in widget.children():
                    notify_lighting(child, state)

            notify_lighting(self.window, is_light)
            self.logger.info(t(self.langer.get("log.info.changetheme"), "light" if is_light else "dark"))

        class Window(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root



                self.server = QLocalServer(self)
                QLocalServer.removeServer("BookMdtLauncherMI")
                if self.server.listen("BookMdtLauncherMI"):
                    self.server.newConnection.connect(self.showS)



                self.root.logger.debug("init QW.window")
                self.root.window = self
                self.setMinimumSize(QSize(600, 450))

                self.installEventFilter(self)

                self._last_window_state = Qt.WindowNoState

                self.init_ui()
                self.init_wid()

                self.root.apply_theme()

                self.root.logger.info(self.root.langer.get("log.info.windowLoad"))

            def init_ui(self):
                self.setWindowTitle("Book MDT Launcher")
                self.setWindowFlags(Qt.FramelessWindowHint)
                self.setGeometry(50, 50, 700, 500)

            def changeEvent(self, event):
                if event.type() == QEvent.WindowStateChange:
                    if not self.isMinimized():
                        self._last_window_state = self.windowState()
                        # 同步最大化/还原按钮图标。
                        # 不依赖 nativeEvent（PySide6 下 eventType 是 QByteArray，
                        # Windows 消息分支不可靠），Qt 自身的窗口状态变化一定触发这里。
                        try:
                            tbt = self.main.top.tbt_max
                            maximized = self.isMaximized()
                            self.root.logger.debug(f"window state changed, maximized={maximized}")
                            tbt.setLogo(1 if maximized else 0)
                        except Exception:
                            pass
                super().changeEvent(event)

            def restore_from_tray(self):
                self.show()
                if self.isMinimized():
                    # 最小化
                    if self._last_window_state == Qt.WindowMaximized:
                        self.showMaximized()
                    else:
                        self.showNormal()
                else:
                    # 提层
                    self.raise_()
                self.activateWindow()

            def showS(self):
                conn = self.server.nextPendingConnection()
                if conn:
                    conn.readyRead.connect(self._on_read_data)
                    conn.disconnected.connect(conn.deleteLater)

            def _on_read_data(self):
                conn = self.sender()
                data = conn.readAll()
                if data == QByteArray(b"MAINWINSHOW"):
                    self.restore_from_tray()
                conn.disconnectFromServer()
                conn.deleteLater()

            def init_wid(self):
                self.floatingStack = self.FloatingStack(self, self.root)
                self.root.logger.debug("init QW.window.left")
                self.left = self.Left(self, self.root)
                self.root.logger.debug("init QW.window.lline")
                self.lline = self.LLine(self, self.root)

                self.root.logger.debug("init QW.windowL")
                self.layout = QHBoxLayout(self)
                self.layout.setAlignment(Qt.AlignLeft)
                self.layout.setSpacing(0)
                self.layout.setContentsMargins(0, 0, 0, 0)

                self.root.logger.debug("init QW.windowL.stren")
                self.stren = QWidget()
                self.stren.setFixedWidth(41)
                self.layout.addWidget(self.stren, 0)

                self.root.logger.debug("init QW.windowL.main")
                self.main = self.Main(self, self.root)
                self.layout.addWidget(self.main, 1)

                self.left.raise_()
                self.lline.raise_()

                self.floatingStack.raise_()

                self.githubSetting = self.GithubSetting(self, self.root)

            def eventFilter(self, obj, event):
                if obj is self and event.type() == QEvent.Resize:
                    new_width = self.left.width()  # 假设宽度固定，或者从配置读取
                    self.left.setGeometry(0, 0, new_width, self.height())
                    self.lline.init_ui()

                    self.root.logger.debug(f"Window resized via filter: {self.width()}x{self.height()}")

                return super().eventFilter(obj, event)

            def nativeEvent(self, eventType, message):
                """
                拦截 Windows 原生消息
                """
                # 判断是否是 Windows 消息
                # PySide6: eventType 是 QByteArray（b"windows_generic_MSG"）；PyQt5 是 str。
                # 直接比较 str 在 PySide6 下恒为 False，导致整个分支（含最大化检测）失效。
                if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
                    # PySide6: message 已是 int（内存地址）；PyQt5 是 sip.voidptr，int() 两者通用
                    msg = ctypes.wintypes.MSG.from_address(int(message))

                    #
                    if msg.message == 0x0084:
                        if not self.isMaximized() and not self.githubSetting.isVisible():
                            # 获取鼠标在屏幕上的坐标
                            pos = self.mapFromGlobal(QCursor.pos())
                            x, y = pos.x(), pos.y()
                            w, h = self.width(), self.height()

                            border_width = 5
                            result = 1

                            if x < border_width:
                                if y < border_width:
                                    result = 13
                                elif y > h - border_width:
                                    result = 16
                                else:
                                    result = 10
                            elif x > w - border_width:
                                if y < border_width:
                                    result = 14
                                elif y > h - border_width:
                                    result = 17
                                else:
                                    result = 11
                            elif y < border_width:
                                result = 12
                            elif y > h - border_width:
                                result = 15

                            return True, result

                    # 托盘主题切换
                    elif msg.message in (0x001A, 0x0320):
                        QTimer.singleShot(100, self.root.tray.setIcon_)

                    # 最大化检测
                    elif msg.message == 0x0005:
                        if msg.wParam == 2:
                            self.root.logger.debug("window maximized")
                            self.main.top.tbt_max.setLogo(1)
                        elif msg.wParam == 0:
                            self.root.logger.debug("window unmaximized")
                            self.main.top.tbt_max.setLogo(0)

                # 3. 其他消息交给默认处理
                return super().nativeEvent(eventType, message)

            def resizeEvent(self, event):
                super().resizeEvent(event)
                self.githubSetting.setGeometry(0,0,self.width(),self.height())
                self.floatingStack.setGeometry(0,40,self.width(),self.height()-40)
                

            class GithubSetting(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()
                    self.hide()

                def init_ui(self):
                    self.setGeometry(self.geometry())
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.setProperty("wid_", "_window.github")
                    self.setStyleSheet('QWidget[wid_="_window.github"]{background-color: rgba(0,0,0,0.5);}')

                def init_wid(self):
                    self.l = QHBoxLayout(self)
                    self.l.setContentsMargins(0, 0, 0, 0)
                    self.l.setSpacing(0)
                    self.l.setAlignment(Qt.AlignCenter)

                    self.panel = self.Panel(self, self.root)
                    self.l.addWidget(self.panel,0)

                def showEvent(self, event):
                    # 显示时提层，盖过 floatingStack 等覆盖控件
                    super().showEvent(event)
                    self.raise_()

                def _sync_rate_from_api(self):
                    """将 GithubAPI 中的实时 rate 同步到 settings 内存（不写盘）。"""
                    rate = self.root.githubAPI.rate
                    s = self.root.settings["github"]
                    s["rate"]["core"] = {
                        "remaining": rate["core"]["remaining"],
                        "reset": rate["core"]["reset"]
                    }
                    s["rate"]["search"] = {
                        "remaining": rate["search"]["remaining"],
                        "reset": rate["search"]["reset"]
                    }

                def _clear_token_data(self):
                    """清除 settings 中所有 token 相关数据（仅当 token 确认无效时调用）。"""
                    self.root.githubAPI.setToken(None)
                    s = self.root.settings["github"]
                    s["token_enc"] = None
                    s["token_key"] = None
                    s["useful"] = None
                    s["user"] = {"name": None, "headurl": None}

                def _debounce_save_settings(self):
                    """延迟 500ms 写盘，合并高频写入。"""
                    if hasattr(self, '_save_timer'):
                        self._save_timer.stop()
                    else:
                        self._save_timer = QTimer(self)
                        self._save_timer.setSingleShot(True)
                        self._save_timer.timeout.connect(self.root.saveSettings)
                    self._save_timer.start(500)

                class Panel(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.githubAPI = self.root.githubAPI
                        self.init_ui()
                        self.init_wid()
                        self.githubAPI.refreshed.connect(self._on_rate_refreshed)
                        

                    def init_ui(self):
                        self.setFixedSize(520,365)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def _on_rate_refreshed(self):
                        self.parent._sync_rate_from_api()
                        if self.isVisible():
                            self.body.content._update_rate_section()

                    def init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop)

                        self.top = self.Top(self, self.root)
                        self.layout.addWidget(self.top,0)
                        
                        self.line = QWidget(self)
                        self.line.setFixedHeight(1)
                        self.line.setProperty("wid","line")
                        self.layout.addWidget(self.line,0)

                        self.body = self.Body(self, self.root)
                        self.layout.addWidget(self.body,1)


                    class Top(QWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.init_ui()
                            self.init_wid()

                        def init_ui(self):
                            self.setFixedHeight(30)
                            self.setAttribute(Qt.WA_StyledBackground, True)

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setContentsMargins(30, 0, 0, 0)
                            self.layout.setSpacing(0)
                            self.layout.setAlignment(Qt.AlignLeft)

                            self.title = QLabel("GitHub")
                            self.title.setProperty("wid", "title")
                            self.title.setStyleSheet("font-size: 16px;")
                            self.layout.addWidget(self.title,0)

                            self.layout.addStretch(1)

                            self.close = self.Close(self, self.root)
                            self.layout.addWidget(self.close,0)

                            self.close.clicked.connect(self.parent.parent.hide)

                        class Close(QPushButton):
                            def __init__(self, parent=None, root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.init_ui()

                            def init_ui(self):
                                self.setFixedSize(30, 30)
                                self.setProperty("wid", "tbtn")
                            
                            def lighting(self, light: bool):
                                color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                                logo = change_color(getPath("src/assets/tribtns/close.png"),color)
                                icon = QIcon(logo.pixmap(30,30))

                                self.setIcon(icon)

                    class Body(QWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.init_wid()

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)

                            self.scroll = QScrollArea(self)
                            self.scroll.setWidgetResizable(True)
                            self.scroll.setFrameShape(QFrame.NoFrame)
                            self.layout.addWidget(self.scroll)

                            self.content = self.Content(self, self.root)
                            self.scroll.setWidget(self.content)

                        class Content(QWidget):
                            def __init__(self, parent=None, root=None):
                                super().__init__(parent)
                                self.parent = parent
                                self.root = root
                                self._gs = parent.parent.parent
                                self._editing = False
                                self.init_wid()
                                self.langing()

                            def init_wid(self):
                                self.layout = QVBoxLayout(self)
                                self.layout.setContentsMargins(20,20,20,20)
                                self.layout.setSpacing(10)
                                self.layout.setAlignment(Qt.AlignTop)


                                self.l1w = QWidget()
                                self.l1w.setFixedHeight(84)
                                self.layout.addWidget(self.l1w,0)
                                
                                self.l1 =QHBoxLayout(self.l1w)
                                self.l1.setContentsMargins(0, 0, 0, 0)
                                self.l1.setSpacing(0)

                                self.headIcon = QLabel()
                                self.headIcon.setProperty("wid","png")
                                self.headIcon.setFixedSize(84,84)
                                self.headIcon.setStyleSheet("border-radius:42px;")
                                self.l1.addWidget(self.headIcon,0)

                                self.l1_l1w = QWidget()
                                self.l1.addWidget(self.l1_l1w,1)

                                self.l1_l1 = QVBoxLayout(self.l1_l1w)
                                self.l1_l1.setContentsMargins(10, 0, 0, 0)
                                self.l1_l1.setSpacing(5)
                                self.l1_l1.setAlignment(Qt.AlignTop)

                                self.userName = QLabel("User-Name")
                                self.userName.setProperty("wid","text")
                                self.userName.setStyleSheet("font-size: 22px;")
                                self.userName.setAlignment(Qt.AlignLeft)
                                self.userName.setFixedHeight(24)
                                self.l1_l1.addWidget(self.userName,0)

                                self.tokenStatus = QLabel("")
                                self.tokenStatus.setProperty("wid","title")
                                self.tokenStatus.setStyleSheet("font-size: 11px;")
                                self.tokenStatus.setAlignment(Qt.AlignLeft)
                                self.tokenStatus.setFixedHeight(14)
                                self.l1_l1.addWidget(self.tokenStatus,0)

                                self.l1_l1_l1w = QWidget()
                                self.l1_l1.addWidget(self.l1_l1_l1w,1)

                                self.l1_l1_l1 = QHBoxLayout(self.l1_l1_l1w)
                                self.l1_l1_l1.setContentsMargins(0, 0, 0, 0)
                                self.l1_l1_l1.setSpacing(5)

                                self.coreBadge = QLabel()
                                self.coreBadge.setProperty("wid","badge")
                                self.coreBadge.setFixedHeight(20)
                                self.l1_l1_l1.addWidget(self.coreBadge,0)

                                self.searchBadge = QLabel()
                                self.searchBadge.setProperty("wid","badge")
                                self.searchBadge.setFixedHeight(20)
                                self.l1_l1_l1.addWidget(self.searchBadge,0)

                                self.l1_l1_l1.addStretch(1)

                                self.layout.addSpacing(14)

                                self.tokenTips = QWidget()
                                self.tokenTips.setStyleSheet(
                                    "QWidget#tokenTips{"
                                    "background-color: rgba(255, 255, 0, 50);"
                                    "border: 1px solid orange;"
                                    "border-radius: 4px;"
                                    "}"
                                )
                                self.tokenTips.setObjectName("tokenTips")
                                tips_l = QHBoxLayout(self.tokenTips)
                                tips_l.setContentsMargins(6, 5, 6, 5)
                                tips_l.setSpacing(6)

                                self.tokenTipsIcon = QLabel()
                                self.tokenTipsIcon.setFixedSize(18, 18)
                                self.tokenTipsIcon.setScaledContents(True)
                                tips_l.addWidget(self.tokenTipsIcon, 0, Qt.AlignTop)

                                self.tokenTipsText = QLabel()
                                self.tokenTipsText.setProperty("wid", "text")
                                self.tokenTipsText.setStyleSheet("font-size: 10px;")
                                self.tokenTipsText.setWordWrap(True)
                                tips_l.addWidget(self.tokenTipsText, 1)

                                self.layout.addWidget(self.tokenTips, 0)

                                self.layout.addSpacing(8)

                                self.tokenTitle = QLabel()
                                self.tokenTitle.setProperty("wid","text")
                                self.tokenTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                                self.tokenTitle.setFixedHeight(18)
                                self.layout.addWidget(self.tokenTitle,0)

                                self.tokenStack = QStackedWidget()
                                self.tokenStack.setFixedHeight(32)
                                self.layout.addWidget(self.tokenStack,0)

                                self.tokenInputW = QWidget()
                                self.tokenInputL = QHBoxLayout(self.tokenInputW)
                                self.tokenInputL.setContentsMargins(0, 0, 0, 0)
                                self.tokenInputL.setSpacing(5)

                                self.tokenInput = QLineEdit()
                                self.tokenInput.setProperty("wid","input")
                                self.tokenInput.setFixedHeight(28)
                                self.tokenInputL.addWidget(self.tokenInput,1)

                                self.tokenSaveBtn = QPushButton()
                                self.tokenSaveBtn.setProperty("wid","btn")
                                self.tokenSaveBtn.setFixedSize(44,28)
                                self.tokenSaveBtn.clicked.connect(self._save_token)
                                self.tokenInputL.addWidget(self.tokenSaveBtn,0)

                                self.tokenCancelBtn = QPushButton()
                                self.tokenCancelBtn.setProperty("wid","btn")
                                self.tokenCancelBtn.setFixedSize(54,28)
                                self.tokenCancelBtn.clicked.connect(self._cancel_edit)
                                self.tokenCancelBtn.setVisible(False)
                                self.tokenInputL.addWidget(self.tokenCancelBtn,0)

                                self.tokenStack.addWidget(self.tokenInputW)

                                self.tokenDisplayW = QWidget()
                                self.tokenDisplayL = QHBoxLayout(self.tokenDisplayW)
                                self.tokenDisplayL.setContentsMargins(0, 0, 0, 0)
                                self.tokenDisplayL.setSpacing(5)

                                self.tokenMaskedLabel = QLabel()
                                self.tokenMaskedLabel.setProperty("wid","title")
                                self.tokenMaskedLabel.setStyleSheet("font-size: 12px;")
                                self.tokenMaskedLabel.setFixedHeight(28)
                                self.tokenDisplayL.addWidget(self.tokenMaskedLabel,1)

                                self.tokenEditBtn = QPushButton()
                                self.tokenEditBtn.setProperty("wid","btn")
                                self.tokenEditBtn.setFixedSize(60,28)
                                self.tokenEditBtn.clicked.connect(self._start_edit)
                                self.tokenDisplayL.addWidget(self.tokenEditBtn,0)

                                self.tokenClearBtn = QPushButton()
                                self.tokenClearBtn.setProperty("wid","btn")
                                self.tokenClearBtn.setFixedSize(60,28)
                                self.tokenClearBtn.clicked.connect(self._clear_token)
                                self.tokenDisplayL.addWidget(self.tokenClearBtn,0)

                                self.tokenStack.addWidget(self.tokenDisplayW)

                                self.tokenMsg = QLabel()
                                self.tokenMsg.setProperty("wid","title")
                                self.tokenMsg.setStyleSheet("font-size: 10px;")
                                self.tokenMsg.setFixedHeight(14)
                                self.layout.addWidget(self.tokenMsg,0)

                                self.tokenTestBtnW = QWidget()
                                self.tokenTestBtnL = QHBoxLayout(self.tokenTestBtnW)
                                self.tokenTestBtnL.setContentsMargins(0, 0, 0, 0)
                                self.tokenTestBtnL.setSpacing(5)

                                self.tokenTestBtn = QPushButton()
                                self.tokenTestBtn.setProperty("wid","btn")
                                self.tokenTestBtn.setFixedSize(90,26)
                                self.tokenTestBtn.clicked.connect(self._test_token)
                                self.tokenTestBtnL.addWidget(self.tokenTestBtn,0)

                                self.tokenLatencyBtn = QPushButton()
                                self.tokenLatencyBtn.setProperty("wid","btn")
                                self.tokenLatencyBtn.setFixedSize(90,26)
                                self.tokenLatencyBtn.clicked.connect(self._test_latency)
                                self.tokenTestBtnL.addWidget(self.tokenLatencyBtn,0)

                                self.tokenTestBtnL.addStretch(1)
                                self.layout.addWidget(self.tokenTestBtnW,0)

                                self.layout.addSpacing(8)

                                self.rateTitle = QLabel()
                                self.rateTitle.setProperty("wid","text")
                                self.rateTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                                self.rateTitle.setFixedHeight(18)
                                self.layout.addWidget(self.rateTitle,0)

                                self.rateCoreW = QWidget()
                                self.rateCoreL = QHBoxLayout(self.rateCoreW)
                                self.rateCoreL.setContentsMargins(0, 0, 0, 0)
                                self.rateCoreL.setSpacing(10)

                                self.rateCoreLabel = QLabel()
                                self.rateCoreLabel.setProperty("wid","text")
                                self.rateCoreLabel.setStyleSheet("font-size: 11px;")
                                self.rateCoreLabel.setFixedHeight(16)
                                self.rateCoreL.addWidget(self.rateCoreLabel,0)

                                self.rateCoreValue = QLabel()
                                self.rateCoreValue.setProperty("wid","title")
                                self.rateCoreValue.setStyleSheet("font-size: 11px;")
                                self.rateCoreValue.setFixedHeight(16)
                                self.rateCoreL.addWidget(self.rateCoreValue,1)

                                self.layout.addWidget(self.rateCoreW,0)

                                self.rateSearchW = QWidget()
                                self.rateSearchL = QHBoxLayout(self.rateSearchW)
                                self.rateSearchL.setContentsMargins(0, 0, 0, 0)
                                self.rateSearchL.setSpacing(10)

                                self.rateSearchLabel = QLabel()
                                self.rateSearchLabel.setProperty("wid","text")
                                self.rateSearchLabel.setStyleSheet("font-size: 11px;")
                                self.rateSearchLabel.setFixedHeight(16)
                                self.rateSearchL.addWidget(self.rateSearchLabel,0)

                                self.rateSearchValue = QLabel()
                                self.rateSearchValue.setProperty("wid","title")
                                self.rateSearchValue.setStyleSheet("font-size: 11px;")
                                self.rateSearchValue.setFixedHeight(16)
                                self.rateSearchL.addWidget(self.rateSearchValue,1)

                                self.layout.addWidget(self.rateSearchW,0)

                                self.layout.addStretch(1)

                            def langing(self):
                                self.tokenTipsIcon.setPixmap(change_color(getPath("src/assets/actions/tips.png"), QColor(255, 165, 0)).pixmap(QSize(18, 18)))
                                self.tokenTipsText.setText(self.root.langer.get("github.settings.tokenTips"))
                                self.tokenTitle.setText(self.root.langer.get("github.settings.tokenTitle"))
                                self.tokenSaveBtn.setText(self.root.langer.get("text.save"))
                                self.tokenCancelBtn.setText(self.root.langer.get("text.cancel"))
                                self.tokenEditBtn.setText(self.root.langer.get("text.edit"))
                                self.tokenClearBtn.setText(self.root.langer.get("text.clear"))
                                self.tokenTestBtn.setText(self.root.langer.get("github.settings.testToken"))
                                self.tokenLatencyBtn.setText(self.root.langer.get("github.settings.testLatency"))
                                self.rateTitle.setText(self.root.langer.get("github.settings.rateTitle"))
                                self.rateCoreLabel.setText(self.root.langer.get("github.settings.rateCore"))
                                self.rateSearchLabel.setText(self.root.langer.get("github.settings.rateSearch"))
                                self._refresh_ui()

                            def showEvent(self, event):
                                super().showEvent(event)
                                self._refresh_ui()

                            def _refresh_ui(self):
                                token = self.root.settings["github"]["token_enc"]
                                self._update_user_section()
                                self._update_token_section(token)
                                self._update_rate_section()

                            def _update_user_section(self):
                                user = self.root.settings["github"]["user"]
                                name = user.get("name") if user else None
                                headurl = user.get("headurl") if user else None

                                if name:
                                    self.userName.setText(name)
                                    self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                    if headurl:
                                        self._load_avatar(headurl)
                                    else:
                                        self.headIcon.clear()
                                elif self.root.settings["github"]["token_enc"] and self.root.settings["github"]["useful"] is False:
                                    self.userName.setText(self.root.langer.get("github.settings.notLoggedIn"))
                                    self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.invalid"))
                                    self.headIcon.clear()
                                elif self.root.settings["github"]["token_enc"]:
                                    self.userName.setText(self.root.langer.get("text.loading"))
                                    self.tokenStatus.setText("")
                                    self.headIcon.clear()
                                else:
                                    self.userName.setText(self.root.langer.get("github.settings.notLoggedIn"))
                                    self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.none"))
                                    self.headIcon.clear()

                            def _load_avatar(self, url):
                                def _fetch():
                                    # 复用 githubAPI 的 session：走系统代理 + 合并 CA bundle
                                    # （裸 requests.get 无法访问 avatars.githubusercontent.com）
                                    try:
                                        session = getattr(self.root, "githubAPI", None)
                                        sess = getattr(session, "_session", None)
                                        if sess is not None:
                                            resp = sess.get(url, timeout=10)
                                        else:
                                            import requests as _req
                                            resp = _req.get(url, timeout=10)
                                        if resp.status_code == 200:
                                            return resp.content
                                    except Exception:
                                        pass
                                    return None
                                def _set_round(data):
                                    # 主线程创建 QPixmap（QPixmap 是 GUI 类，禁止在子线程创建）
                                    if not data:
                                        return
                                    pix = QPixmap()
                                    if not pix.loadFromData(data):
                                        return
                                    scaled = pix.scaled(78, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                    round_pix = QPixmap(78, 78)
                                    round_pix.fill(Qt.transparent)
                                    painter = QPainter(round_pix)
                                    painter.setRenderHint(QPainter.Antialiasing)
                                    path = QPainterPath()
                                    path.addEllipse(0, 0, 78, 78)
                                    painter.setClipPath(path)
                                    offset_x = (78 - scaled.width()) // 2
                                    offset_y = (78 - scaled.height()) // 2
                                    painter.drawPixmap(offset_x, offset_y, scaled)
                                    painter.end()
                                    self.headIcon.setPixmap(round_pix)
                                QThTimer.task(0, lambda e,_url=url: _fetch(), result_callback=_set_round, dedicated=True)

                            def _update_token_section(self, token):
                                if self._editing:
                                    return
                                if token:
                                    self.tokenStack.setCurrentIndex(1)
                                    masked = self.root.githubAPI.getMaskedToken()
                                    self.tokenMaskedLabel.setText(masked if masked else "****")
                                    self.tokenMsg.setText("")
                                else:
                                    self.tokenStack.setCurrentIndex(0)
                                    self.tokenInput.clear()
                                    self.tokenMsg.setText("")

                            def _update_rate_section(self):
                                rate = self.root.githubAPI.rate
                                core = rate.get("core", {})
                                search = rate.get("search", {})

                                core_rem = core.get("remaining")
                                search_rem = search.get("remaining")
                                core_reset = core.get("reset", [])
                                search_reset = search.get("reset", [])

                                if core_rem is not None:
                                    self.coreBadge.setText(f"Core: {core_rem}")
                                    self.coreBadge.setVisible(True)
                                    reset_str = ""
                                    if len(core_reset) == 6:
                                        reset_str = f"{core_reset[0]}-{core_reset[1]:02d}-{core_reset[2]:02d} {core_reset[3]:02d}:{core_reset[4]:02d}:{core_reset[5]:02d}"
                                    self.rateCoreValue.setText(
                                        f"{self.root.langer.get('github.settings.rateRemaining')}: {core_rem}   "
                                        f"{self.root.langer.get('github.settings.rateReset')}: {reset_str}"
                                    )
                                else:
                                    self.coreBadge.setVisible(False)
                                    self.rateCoreValue.setText("")

                                if search_rem is not None:
                                    self.searchBadge.setText(f"Search: {search_rem}")
                                    self.searchBadge.setVisible(True)
                                    reset_str = ""
                                    if len(search_reset) == 6:
                                        reset_str = f"{search_reset[0]}-{search_reset[1]:02d}-{search_reset[2]:02d} {search_reset[3]:02d}:{search_reset[4]:02d}:{search_reset[5]:02d}"
                                    self.rateSearchValue.setText(
                                        f"{self.root.langer.get('github.settings.rateRemaining')}: {search_rem}   "
                                        f"{self.root.langer.get('github.settings.rateReset')}: {reset_str}"
                                    )
                                else:
                                    self.searchBadge.setVisible(False)
                                    self.rateSearchValue.setText("")

                            def _start_edit(self):
                                self._editing = True
                                self.tokenStack.setCurrentIndex(0)
                                self.tokenCancelBtn.setVisible(True)
                                self.tokenInput.clear()

                            def _cancel_edit(self):
                                self._editing = False
                                token = self.root.settings["github"]["token_enc"]
                                if token:
                                    self.tokenStack.setCurrentIndex(1)
                                self.tokenInput.clear()

                            def _save_token(self):
                                new_token = self.tokenInput.text().strip()
                                if not new_token:
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                    return

                                self.root.githubAPI.setToken(new_token)
                                self.root._encrypt_settings_token(new_token)
                                new_token = None

                                self.tokenSaveBtn.setEnabled(False)
                                self.tokenMsg.setText(self.root.langer.get("github.settings.tokenChecking"))

                                def _on_checked(result):
                                    ok, error_type, data = result
                                    self.tokenSaveBtn.setEnabled(True)
                                    if ok:
                                        self._gs._sync_rate_from_api()
                                        self.root.settings["github"]["useful"] = True
                                        self.root.saveSettings()
                                        self._editing = False
                                        self._refresh_ui()
                                        self._fetch_user()
                                        # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                                        self.tokenMsg.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                    elif error_type == "auth":
                                        self.root.settings["github"]["useful"] = False
                                        self.tokenMsg.setText(
                                            f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}"
                                        )
                                    elif error_type == "network":
                                        self.tokenMsg.setText(
                                            f"{self.root.langer.get('github.settings.latencyConnError')}: {data}"
                                        )
                                    else:
                                        self.tokenMsg.setText(f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}")

                                QThTimer.task(
                                    0,
                                    lambda e: self.root.githubAPI.checkToken(),
                                    result_callback=_on_checked,
                                    dedicated=True
                                )

                            def _clear_token(self):
                                self._gs._clear_token_data()
                                self.root.saveSettings()
                                self._editing = False
                                self._refresh_ui()

                            def _test_token(self):
                                if not self.root.settings["github"]["token_enc"]:
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                    return
                                self.tokenTestBtn.setEnabled(False)
                                self.tokenMsg.setText(self.root.langer.get("github.settings.tokenChecking"))
                                def _done(result):
                                    self.tokenTestBtn.setEnabled(True)
                                    ok, error_type, data = result
                                    if ok:
                                        self._gs._sync_rate_from_api()
                                        self.root.settings["github"]["useful"] = True
                                        self._refresh_ui()
                                        # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                                        self.tokenMsg.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                    elif error_type == "auth":
                                        # 仅明确的认证失败才清除 token
                                        self._gs._clear_token_data()
                                        self.root.saveSettings()
                                        self._refresh_ui()
                                        self.tokenMsg.setText(
                                            f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}"
                                        )
                                    elif error_type == "network":
                                        # 网络不通，保留 token
                                        self.tokenMsg.setText(
                                            f"{self.root.langer.get('github.settings.latencyConnError')}: {data}"
                                        )
                                    else:
                                        self.tokenMsg.setText(f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}")
                                QThTimer.task(
                                    0,
                                    lambda e: self.root.githubAPI.checkToken(),
                                    result_callback=_done,
                                    dedicated=True
                                )

                            def _test_latency(self):
                                if not self.root.settings["github"]["token_enc"]:
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                    return
                                self.tokenLatencyBtn.setEnabled(False)
                                self.tokenMsg.setText(self.root.langer.get("github.settings.latencyChecking"))
                                def _done(latency):
                                    self.tokenLatencyBtn.setEnabled(True)
                                    if latency > 0:
                                        self.tokenMsg.setText(
                                            self.root.langer.get("github.settings.latencyResult").replace("$1", str(latency))
                                        )
                                    elif latency == -2:
                                        self.tokenMsg.setText(self.root.langer.get("github.settings.latencyTimeout"))
                                    elif latency == -3:
                                        self.tokenMsg.setText(self.root.langer.get("github.settings.latencyConnError"))
                                    elif latency == -4:
                                        self.tokenMsg.setText("SSL 连接错误")
                                    else:
                                        self.tokenMsg.setText(
                                            self.root.langer.get("github.settings.latencyError").replace("$1", str(latency))
                                        )
                                QThTimer.task(
                                    0,
                                    lambda e: self.root.githubAPI.checkConnection(),
                                    result_callback=_done,
                                    dedicated=True
                                )

                            def _fetch_user(self):
                                def _on_user(result):
                                    ok, data = result
                                    if ok:
                                        body = data.get("body", {})
                                        self.root.settings["github"]["user"] = {
                                            "name": body.get("login"),
                                            "headurl": body.get("avatar_url")
                                        }
                                        self.root.saveSettings()
                                        self._refresh_ui()
                                    else:
                                        # 获取用户信息失败，但不影响 token 有效性
                                        self.root.settings["github"]["user"] = {"name": None, "headurl": None}
                                        self._refresh_ui()
                                QThTimer.task(
                                    0,
                                    lambda e: self.root.githubAPI.getUser(),
                                    result_callback=_on_user,
                                    dedicated=True
                                )


            class Left(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.isfold = True
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setGeometry(0, 0, 40, self.parent.height())
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.root.logger.debug("init QW.window.leftL")
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.root.logger.debug("init QW.window.leftL.tline")
                    self.tline = self.TLine(self, self.root)
                    self.root.logger.debug("init QW.window.leftL.logo")
                    self.logo = self.Logo(self, self.root)
                    self.layout.addWidget(self.logo, 0)
                    self.layout.addWidget(self.tline, 0)

                    self.root.logger.debug("init QW.window.leftL.pages")
                    self.pagebtns = self.PageBtns(self, self.root)
                    self.layout.addWidget(self.pagebtns, 1)

                def fold(self, text=None):
                    if text is None:
                        text = not self.isfold
                    width = 40 if text else 180
                    self.setGeometry(0, 0, width, self.height())
                    self.root.window.lline.init_ui()
                    self.root.logger.debug(f"Window left fold: {self.isfold}")
                    self.isfold = text

                class Logo(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root

                        self.move_pressed = False
                        self.move_moving = False
                        self.move_winpos_ = None
                        self.move_mousepos_ = None

                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedSize(180, 40)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        self.root.logger.debug("init QW.window.leftL.logoL")
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(5)
                        self.layout.setAlignment(Qt.AlignLeft)

                        self.logo = QLabel(self)

                        self.logo.setFixedSize(40, 40)
                        self.logo.setScaledContents(True)
                        self.layout.addWidget(self.logo, 0)

                        self.label = QLabel(self)
                        self.label.setText('Book MDT Launcher')
                        self.label.setFixedWidth(140)
                        self.label.setProperty('wid', 'title')
                        self.layout.addWidget(self.label, 1)

                    def lighting(self, light: bool):
                        logo = getPath("src/assets/icons/" + ("dark.png" if light else "light.png"))
                        pix = QPixmap(logo)
                        if pix.isNull():
                            self.root.logger.error(f"Logo image not found: {logo}")
                        self.logo.setPixmap(pix)

                    def mousePressEvent(self, event):
                        self.move_pressed = True
                        self.move_winpos_ = self.root.window.pos()
                        self.move_mousepos_ = event.globalPosition().toPoint()
                        super().mousePressEvent(event)

                    def mouseMoveEvent(self, event):
                        if self.move_pressed:
                            if self.root.window.isMaximized():
                                self.root.window.showNormal()
                            self.move_mousepos = event.globalPosition().toPoint()
                            self.move_moving = True
                            screensize = QApplication.primaryScreen().availableGeometry()
                            movpos = self.move_winpos_ + self.move_mousepos - self.move_mousepos_
                            if movpos.x() < 0:
                                movpos.setX(0)
                            elif movpos.x() > screensize.width() - 40:
                                movpos.setX(screensize.width() - 40)
                            if movpos.y() < 0:
                                movpos.setY(0)
                            elif movpos.y() > screensize.height() - 40:
                                movpos.setY(screensize.height() - 40)
                            self.root.window.move(movpos)
                        super().mouseMoveEvent(event)

                    def mouseReleaseEvent(self, event):
                        if self.move_pressed and self.move_moving:
                            self.root.logger.debug(t("Window moved via filter: ($1,$2)", self.root.window.pos().x(), self.root.window.pos().y()))
                        else:
                            self.parent.fold()
                        self.move_pressed = False
                        self.move_moving = False
                        super().mouseReleaseEvent(event)

                class TLine(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.root = root
                        self.parent = parent

                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(1)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        self.line = QWidget(self)
                        self.line.setAttribute(Qt.WA_StyledBackground, True)
                        self.line.setProperty("wid", "line")

                    def resizeEvent(self, event):
                        """
                        当 TLine 的大小发生变化时（由布局管理器决定），
                        重新计算内部 line 的位置和宽度
                        """
                        super().resizeEvent(event)

                        # 获取当前 TLine 的实际宽度
                        current_width = self.width()

                        # 确保宽度足够减去两边的 5px
                        if current_width > 10:
                            new_width = current_width - 10
                            new_x = 5
                        else:
                            new_width = current_width
                            new_x = 0

                        # 更新内部 line 的几何形状
                        self.line.setGeometry(new_x, 0, new_width, 1)

                class PageBtns(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self._btn = None
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setFixedWidth(180)

                    def init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop)

                        self.btsGroup = QButtonGroup(self)
                        self.btns_ = []

                        self.chooser = QWidget(self)
                        self.chooser.setAttribute(Qt.WA_StyledBackground, True)
                        self.chooser.setStyleSheet("background: #6e4197;")
                        self.chooser.setFixedSize(3, 40)
                        self.chooser.move(-10, 0)

                        self.btsGroup.buttonClicked.connect(self.someone_clicked)

                    def someone_clicked(self, btn):
                        if self._btn is not btn:
                            self.chooser.setGeometry(btn.x(), btn.y(), 3, 40)
                            self.root.logger.debug(t("Page changed to: $1", self.root.langer.get(btn.text_)))
                            self._btn = btn

                    def add_btn(self, text=None, logo=None):
                        btn = self.Btns(logo, text, self, self.root)
                        self.btns_.append(btn)
                        self.layout.addWidget(btn)
                        self.btsGroup.addButton(btn)
                        return btn

                    class Btns(QPushButton):
                        def __init__(self, logo=None, text=None, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.logo_ = logo
                            self.text_ = text
                            self.init_ui()
                            self.init_wid()

                        def init_ui(self):
                            self.setFixedSize(180, 40)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid", "lbtn")
                            self.setCheckable(True)

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setContentsMargins(3, 0, 0, 0)
                            self.layout.setSpacing(5)

                            self.logo = QLabel(self)
                            self.logo.setFixedSize(40, 40)
                            self.logo.setAttribute(Qt.WA_StyledBackground, False)
                            self.logo.setProperty("wid", "lbtn")
                            self.logo.setScaledContents(False)
                            self.layout.addWidget(self.logo)

                            self.text = QLabel(self)
                            self.text.setAttribute(Qt.WA_StyledBackground, False)
                            self.text.setFixedSize(140, 40)
                            self.text.setProperty("wid", "lbtn")
                            self.langing()
                            self.layout.addWidget(self.text)

                        def lighting(self, light: bool):
                            if self.logo_ is not None:
                                color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                                logo = change_color(self.logo_, color)
                                pixmap = logo.pixmap(56,56)

                                if not pixmap.isNull():
                                    smooth_pixmap = pixmap.scaled(
                                        30, 30,
                                        Qt.KeepAspectRatio,
                                        Qt.FastTransformation
                                    )
                                    self.logo.setPixmap(smooth_pixmap)
                                else:
                                    self.root.logger.warning(f"Failed to load pixmap for {self.logo_}")

                        def langing(self):
                            if self.text_ is not None:
                                self.text.setText(self.root.langer.get(self.text_))
                                self.setToolTip(self.root.langer.get(self.text_))

                        def setText(self, _text):
                            self.text_ = _text
                            self.langing()

                        def setLogo(self, _logo):
                            self.logo_ = _logo
                            self.lighting()

            class LLine(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.init_ui()

                def init_ui(self):
                    self.setProperty("wid", "line")
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.setGeometry(self.parent.left.width(), 0, 1, self.parent.height())


            class Main(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    pass

                def init_wid(self):
                    self.root.logger.debug("init QW.windowL.mainL")
                    self.layout = QVBoxLayout(self)
                    self.layout.setAlignment(Qt.AlignTop)
                    self.layout.setSpacing(0)
                    self.layout.setContentsMargins(0, 0, 0, 0)

                    self.root.logger.debug("init QW.windowL.mainL.top")
                    self.top = self.Top(self, self.root)
                    self.layout.addWidget(self.top, 0)

                    self.root.logger.debug("init QW.windowL.mainL.tline")
                    self.tline = self.TLine(self, self.root)
                    self.layout.addWidget(self.tline)

                    self.root.logger.debug("init QW.windowL.mainL.main")
                    self.main = self.Main(self, self.root)
                    self.layout.addWidget(self.main, 1)

                class Top(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(40)

                    def init_wid(self):
                        self.root.logger.debug("init QW.windowL.mainL.topL")
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(7, 0, 5, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignRight)

                        self.github = self.GitHub(self, self.root)
                        self.layout.addWidget(self.github)

                        self.layout.addSpacing(8)

                        self.dlList = self.DlList(self, self.root)
                        self.layout.addWidget(self.dlList)

                        self.layout.addStretch(1)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_mini")
                        self.tbt_mini = self.TriBtn([getPath("src/assets/tribtns/minimize.png")], self, self.root)
                        self.tbt_mini.clicked.connect(lambda: self.root.window.showMinimized())
                        self.layout.addWidget(self.tbt_mini)
                        self.layout.addSpacing(5)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_max")
                        self.tbt_max = self.TriBtn(
                            [
                                getPath("src/assets/tribtns/maximize.png"),
                                getPath("src/assets/tribtns/maximize2.png")
                            ],
                            self, self.root)
                        self.tbt_max.clicked.connect(self.maxmize)
                        self.layout.addWidget(self.tbt_max)
                        self.layout.addSpacing(5)

                        self.root.logger.debug("init QW.windowL.mainL.topL.tbt_close")
                        self.tbt_close = self.TriBtn([getPath("src/assets/tribtns/close.png")], self, self.root)
                        self.tbt_close.clicked.connect(lambda: self.close_())
                        self.tbt_close.setStyleSheet("QPushButton:hover{background: red;}")
                        self.layout.addWidget(self.tbt_close)


                    def maxmize(self):
                        if self.root.window.isMaximized():
                            self.root.window.showNormal()
                        else:
                            self.root.window.showMaximized()

                    def close_(self):
                        if self.root.settings["closeByTray"]:
                            self.root.window.hide()
                        else:
                            self.root.window.close()

                    class GitHub(QPushButton):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self._hover_pending = False
                            self.init_ui()
                            self.clicked.connect(lambda: self.root.window.githubSetting.show())
                            # refreshed 仅更新 tooltip，不触发后台请求
                            self.root.githubAPI.refreshed.connect(self._update_tooltip)

                        def init_ui(self):
                            self.setFixedSize(28, 28)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setStyleSheet("QPushButton {border-radius: 15px;}")

                        def lighting(self, light):
                            self.setIcon(QIcon(change_color(getPath("src/assets/brands/github.png"),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                            self.setIconSize(QSize(28, 28))

                        def _update_tooltip(self):
                            """仅更新 tooltip 文本，不触发网络请求。"""
                            token = self.root.settings["github"]["token_enc"]
                            live_rate = self.root.githubAPI.rate
                            rate = self.root.settings["github"]["rate"]

                            def _fmt_reset(entry):
                                r = entry.get("reset", [])
                                if len(r) == 6:
                                    return f"{r[3]:02d}:{r[4]:02d}:{r[5]:02d}"
                                return "-"

                            def _get(entry, key, fallback_entry=None):
                                v = entry.get(key)
                                if v is not None and v != []:
                                    return v
                                if fallback_entry is not None:
                                    v = fallback_entry.get(key)
                                    if v is not None and v != []:
                                        return v
                                return None

                            core_rem = _get(rate["core"], "remaining", live_rate["core"])
                            search_rem = _get(rate["search"], "remaining", live_rate["search"])
                            core_reset = _fmt_reset(
                                rate["core"] if rate["core"].get("reset") else live_rate["core"]
                            )
                            search_reset = _fmt_reset(
                                rate["search"] if rate["search"].get("reset") else live_rate["search"]
                            )

                            if token is None:
                                key = "github.token.none"
                            elif self.root.settings["github"]["useful"] is False:
                                key = "github.token.error"
                            else:
                                key = "github.token"
                            #   $1=剩余次数 $2=刷新时间 $3=剩余次数 $4=刷新时间
                            self.setToolTip(str(t(
                                self.root.langer.get(key),
                                search_reset, search_rem, core_reset, core_rem
                            )))

                        def _maybe_fetch_rate(self):
                            """hover 时数据缺失才触发一次 checkToken（防抖 2s）。"""
                            if self._hover_pending:
                                return
                            live = self.root.githubAPI.rate
                            core_rem = live["core"].get("remaining")
                            search_rem = live["search"].get("remaining")
                            if core_rem is not None and search_rem is not None:
                                return
                            self._hover_pending = True
                            QThTimer.task(0, lambda e: self.root.githubAPI.checkToken(), dedicated=True)
                            # 2 秒后允许下次 hover 触发
                            QTimer.singleShot(2000, lambda: setattr(self, '_hover_pending', False))

                        def enterEvent(self, event):
                            super().enterEvent(event)
                            self._update_tooltip()
                            if self.root.settings["github"]["token_enc"] is not None:
                                self._maybe_fetch_rate()

                    class DlList(QPushButton):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.init_ui()
                            self.shown = True
                            self.hide()
                            self._active_state = None
                            # taskP 周期驱动：job 在 QThTimer 共享子线程检查任务表，
                            # 仅状态变化时 emit 回主线程刷新 UI——主线程零轮询、跨线程消息最少
                            self._dl_timer = QThTimer.taskP(
                                1000, self._check_state, [lambda v: self._apply_visible(v)]
                            )
                            self.destroyed.connect(self._stop_dl_timer)
                            self.clicked.connect(self._on_click)

                        def _on_click(self):
                            """打开下载列表页（floatingStack 导航页）。"""
                            self.root.window.floatingStack.add_page(self.DlListPage(self, self.root))

                        def _check_state(self, event):
                            """子线程：读取任务表，与本地状态比对，变化才 emit。"""
                            cur = bool(QDownloader.get_active_tasks())
                            if cur != self._active_state:
                                self._active_state = cur
                                event.lambdas[0].emit(cur)

                        def _apply_visible(self, visible):
                            """主线程：仅状态变化时被调用，更新 UI。"""
                            try:
                                self.setVisible(visible and self.shown)
                            except Exception:
                                pass

                        def update_shown(self):
                            """shown 变化（DlListPage 打开/关闭）后立即刷新，不等下一个周期。"""
                            try:
                                self.setVisible(self._active_state and self.shown)
                            except Exception:
                                pass

                        def _stop_dl_timer(self):
                            # 自身销毁时停掉周期任务，避免对已删除对象回调
                            try:
                                timer = getattr(self, "_dl_timer", None)
                                if timer is not None:
                                    timer.destroy()
                                    self._dl_timer = None
                            except Exception:
                                pass

                        def init_ui(self):
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setStyleSheet("QPushButton {border-radius: 15px;}")

                        def lighting(self, light):
                            self.setIcon(QIcon(change_color(getPath("src/assets/actions/dl_list.png"),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                            self.setIconSize(QSize(30,30))

                        class DlListPage(QWidget):
                            def __init__(self, parent=None, root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.parent.shown = False
                                self.parent.update_shown()
                                self.item_map = {}          # task_id -> Item
                                self._closed = False
                                self._timer = None
                                self._last_java_paused = None   # 检测循环上次看到的 Java 暂停状态（变化时记日志）
                                self.init_ui()
                                self.langing()
                                # 初始化时立即扫描一次，随后周期刷新
                                self._timer = QThTimer.taskP(1000, self._snapshot_tasks, result_callback=self._render_items)
                                QThTimer.task(0, self._snapshot_tasks, result_callback=self._render_items)

                            def on_close(self):
                                self._closed = True
                                self.parent.shown = True
                                self.parent.update_shown()
                                try:
                                    if self._timer is not None:
                                        self._timer.destroy()
                                        self._timer = None
                                except Exception:
                                    pass

                            def init_ui(self):
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.setProperty("wid", "color2")
                                self.layout = QVBoxLayout(self)
                                self.layout.setContentsMargins(0, 0, 0, 0)
                                self.layout.setSpacing(0)

                                # 标题栏：标题 + 返回
                                self.top_bar = QWidget()
                                self.top_bar.setFixedHeight(44)
                                self.layout.addWidget(self.top_bar, 0)
                                self.top_layout = QHBoxLayout(self.top_bar)
                                self.top_layout.setContentsMargins(15, 0, 10, 0)
                                self.top_layout.setSpacing(8)
                                self.title_label = QLabel()
                                self.title_label.setProperty("wid", "text")
                                self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
                                self.top_layout.addWidget(self.title_label, 1)

                                self.divider = QWidget()
                                self.divider.setProperty("wid", "line")
                                self.divider.setFixedHeight(1)
                                self.layout.addWidget(self.divider, 0)

                                # 任务列表滚动区
                                self.scroll = QScrollArea()
                                self.scroll.setWidgetResizable(True)
                                self.scroll.setFrameShape(QFrame.NoFrame)
                                self.layout.addWidget(self.scroll, 1)
                                self.list_container = QWidget()
                                self.list_container.setAttribute(Qt.WA_StyledBackground, True)
                                self.list_container.setStyleSheet("background: transparent")
                                self.list_layout = QVBoxLayout(self.list_container)
                                self.list_layout.setContentsMargins(12, 12, 12, 12)
                                self.list_layout.setSpacing(8)
                                self.list_layout.setAlignment(Qt.AlignTop)
                                self.scroll.setWidget(self.list_container)

                                # 空状态提示（始终位于列表末尾，任务卡片插入其前）
                                self.empty_label = QLabel()
                                self.empty_label.setProperty("wid", "title")
                                self.empty_label.setStyleSheet("font-size: 14px;")
                                self.empty_label.setAlignment(Qt.AlignCenter)
                                self.empty_label.setFixedHeight(120)
                                self.list_layout.addWidget(self.empty_label)

                            def langing(self):
                                self.title_label.setText(self.root.langer.get("wid.pages.downloadList.title"))
                                self.empty_label.setText(self.root.langer.get("wid.pages.downloadList.empty"))

                            def _snapshot_tasks(self, event):
                                """子线程：收集运行中/暂停中与可续传任务的快照（不触碰 UI）。"""
                                try:
                                    actives = {}
                                    for task_id, task in QDownloader.get_active_tasks().items():
                                        done, total = 0, 0
                                        try:
                                            done, total = task.get_progress()
                                        except Exception:
                                            pass
                                        actives[task_id] = {
                                            "id": task_id,
                                            "kind": "active",
                                            "dest": task.dest_path or "",
                                            "title": getattr(task, "title", "") or "",
                                            "done": done,
                                            "total": total,
                                            "paused": bool(getattr(task, "_is_paused", False)),
                                            "cancel_allowed": bool(getattr(task, "cancel_allowed", True)),
                                            "pause_allowed": bool(getattr(task, "pause_allowed", True)),
                                            "task": task,
                                        }
                                    pendings = {}
                                    for task_id, info in QDownloader.get_pending_tasks().items():
                                        pendings[task_id] = {
                                            "id": task_id,
                                            "kind": "pending",
                                            "dest": info.get("dest_path") or "",
                                            "title": info.get("title") or "",
                                            "done": info.get("done_bytes") or 0,
                                            "total": info.get("total_size") or 0,
                                            "paused": False,
                                            "task": None,
                                            "state_file": info.get("state_file") or "",
                                        }
                                    return actives, pendings
                                except Exception as e:
                                    return e

                            def _render_items(self, result):
                                if self._closed or isinstance(result, Exception):
                                    return
                                actives, pendings = result
                                # Java 下载状态同步：检测循环轮询读取任务实时状态，驱动 Launch 页 label。
                                # 与 paused_changed 信号互补——信号丢失/时序错乱时，1 秒内轮询自动纠正，
                                # 避免暂停瞬间被 progress 覆盖成"正在下载"后卡住。
                                # 只更新 label 文本不切页，避免打断用户当前页面。
                                try:
                                    for _t in actives.values():
                                        _dest = _t.get("dest") or ""
                                        if _dest.startswith(javaDownload.JAVA_TMP_DIR):
                                            _total = _t.get("total") or 0
                                            _done = _t.get("done") or 0
                                            _pct = min(100, int(_done * 100.0 / _total)) if _total > 0 else 0
                                            _paused = bool(_t.get("paused"))
                                            _bottom = self.root._java_bottom()
                                            if _paused:
                                                _bottom.launch.setStatus("paused", _pct)
                                            else:
                                                _bottom.launch.setStatus("downloading", _pct)
                                            # 检测循环日志：记录读取到的 Java 任务状态（含暂停/恢复切换），
                                            # 用于排查信号竞争导致的"暂停后被覆盖成正在下载"
                                            if _paused != self._last_java_paused:
                                                self.root.logger.info(t(self.root.langer.get("log.dl.java_state"),
                                                                        "paused" if _paused else "downloading",
                                                                        _pct,
                                                                        os.path.basename(_dest) or _dest))
                                                self._last_java_paused = _paused
                                            break
                                except Exception as e:
                                    self.root.logger.warning(t(self.root.langer.get("log.dl.java_sync_error"), repr(e)))
                                all_tasks = dict(actives)
                                all_tasks.update(pendings)
                                # 移除已消失的任务卡片
                                for task_id in list(self.item_map.keys()):
                                    if task_id not in all_tasks:
                                        item = self.item_map.pop(task_id)
                                        self.list_layout.removeWidget(item)
                                        item.deleteLater()
                                # 新增或刷新卡片
                                for task_id, task_info in all_tasks.items():
                                    if task_id not in self.item_map:
                                        item = self.Item(self, self.root)
                                        item.continue_requested.connect(self._continue_task)
                                        item.delete_requested.connect(self._delete_task)
                                        self.item_map[task_id] = item
                                        self.list_layout.insertWidget(self.list_layout.count() - 1, item)
                                    else:
                                        item = self.item_map[task_id]
                                    item.set_data(task_info)
                                self.empty_label.setVisible(not bool(all_tasks))

                            def _continue_task(self, task_id):
                                try:
                                    dl = QDownloader.continue_task(task_id)
                                    if not hasattr(self.root, "_mdt_downloads"):
                                        self.root._mdt_downloads = []
                                    self.root._mdt_downloads.append(dl)
                                    # 用户主动续传：清除 downloading.json 中的暂停状态（恢复下载）
                                    try:
                                        dest = getattr(dl, "dest_path", "") or ""
                                        if dest and _is_mdt_download(dest):
                                            dfile = os.path.join(os.path.dirname(dest), "downloading.json")
                                            if os.path.isfile(dfile):
                                                with open(dfile, "r", encoding="utf-8") as f:
                                                    info = json.load(f)
                                                if info.get("paused"):
                                                    info["paused"] = False
                                                    info["updated_at"] = int(time.time())
                                                    with open(dfile, "w", encoding="utf-8") as f:
                                                        json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                                    except Exception:
                                        pass
                                except Exception as e:
                                    self.root.logger.error(t(self.root.langer.get("log.dl.resume_failed"), task_id, e))

                            def _delete_task(self, state_file):
                                task_dir = os.path.dirname(state_file) if state_file else None
                                if task_dir and os.path.isdir(task_dir):
                                    shutil.rmtree(task_dir, ignore_errors=True)
                                # 若是 mdt 游戏下载：同时删除目标文件夹（含 downloading.json），
                                # 避免残留记录导致下次启动又被续传
                                try:
                                    dest = ""
                                    if state_file and os.path.isfile(state_file):
                                        with open(state_file, "r", encoding="utf-8") as f:
                                            dest = (json.load(f) or {}).get("dest_path", "") or ""
                                    if dest and _is_mdt_download(dest):
                                        mdir = os.path.dirname(dest)
                                        if os.path.isdir(mdir):
                                            shutil.rmtree(mdir, ignore_errors=True)
                                        self.root.logger.info(t(self.root.langer.get("log.dl.mdt_delete_cleaned"),
                                                                os.path.basename(mdir) or mdir))
                                except Exception:
                                    pass
                                # 立即刷新一轮，不必等下一个周期
                                QThTimer.task(0, lambda e: self._snapshot_tasks(e), result_callback=self._render_items)

                            class Item(QWidget):
                                continue_requested = Signal(str)
                                delete_requested = Signal(str)

                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent)
                                    self.parent = parent
                                    self.root = root
                                    self.task_id = ""
                                    self.task = None      # 运行中任务的 QDownloader 实例（pending 为 None）
                                    self.state_file = ""
                                    self.task_info = {}
                                    self.init_ui()

                                def init_ui(self):
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.setProperty("wid", "color2")
                                    self.setStyleSheet("border-radius: 8px;")
                                    layout = QVBoxLayout(self)
                                    layout.setContentsMargins(12, 8, 12, 8)
                                    layout.setSpacing(6)

                                    # 第一行：文件名 + 状态
                                    row1 = QHBoxLayout()
                                    row1.setSpacing(8)
                                    self.title_label = QLabel()
                                    self.title_label.setProperty("wid", "text")
                                    self.title_label.setStyleSheet("font-size: 13px;")
                                    row1.addWidget(self.title_label, 1)
                                    self.status_label = QLabel()
                                    self.status_label.setProperty("wid", "title")
                                    self.status_label.setStyleSheet("font-size: 11px;")
                                    row1.addWidget(self.status_label, 0)
                                    layout.addLayout(row1)

                                    # 第二行：进度条 + 已下载/总大小
                                    row2 = QHBoxLayout()
                                    row2.setSpacing(8)
                                    self.progress_bar = QProgressBar()
                                    self.progress_bar.setProperty("wid", "progress")
                                    self.progress_bar.setRange(0, 100)
                                    self.progress_bar.setTextVisible(False)
                                    self.progress_bar.setFixedHeight(14)
                                    row2.addWidget(self.progress_bar, 1)
                                    self.size_label = QLabel()
                                    self.size_label.setProperty("wid", "title")
                                    self.size_label.setStyleSheet("font-size: 11px;")
                                    self.size_label.setFixedWidth(120)
                                    row2.addWidget(self.size_label, 0)
                                    layout.addLayout(row2)

                                    # 第三行：主操作（暂停/继续/续传）+ 次操作（取消/删除）
                                    row3 = QHBoxLayout()
                                    row3.setSpacing(6)
                                    row3.addStretch(1)
                                    self.btn_primary = QPushButton()
                                    self.btn_primary.setProperty("wid", "btn")
                                    self.btn_primary.setFixedSize(64, 24)
                                    row3.addWidget(self.btn_primary, 0)
                                    self.btn_secondary = QPushButton()
                                    self.btn_secondary.setProperty("wid", "btn")
                                    self.btn_secondary.setFixedSize(64, 24)
                                    row3.addWidget(self.btn_secondary, 0)
                                    layout.addLayout(row3)

                                    self.btn_primary.clicked.connect(self._on_primary_clicked)
                                    self.btn_secondary.clicked.connect(self._on_secondary_clicked)

                                @staticmethod
                                def _fmt_size(size):
                                    size = max(0, int(size or 0))
                                    if size >= 1024 * 1024 * 1024:
                                        return "%.2f GB" % (size / (1024.0 ** 3))
                                    if size >= 1024 * 1024:
                                        return "%.2f MB" % (size / (1024.0 ** 2))
                                    if size >= 1024:
                                        return "%.1f KB" % (size / 1024.0)
                                    return "%d B" % size

                                def set_data(self, task_info):
                                    self.task_info = task_info
                                    self.task_id = task_info.get("id") or ""
                                    task = task_info.get("task")
                                    if task is not self.task:
                                        self._disconnect_task_signals()
                                        self.task = task
                                        self._connect_task_signals()
                                    self.state_file = task_info.get("state_file") or ""

                                    # 名称（超长省略）：优先显示 title，回退文件名
                                    name = task_info.get("title") or os.path.basename(task_info.get("dest") or "") or self.task_id
                                    self.title_label.setText(QFontMetrics(self.title_label.font()).elidedText(name, Qt.ElideRight, 460))

                                    # 进度条与大小文本
                                    done = task_info.get("done") or 0
                                    total = task_info.get("total") or 0
                                    if total > 0:
                                        percent = min(100, int(done * 100.0 / total))
                                        self.progress_bar.setValue(percent)
                                        self.size_label.setText("%s / %s" % (self._fmt_size(done), self._fmt_size(total)))
                                    else:
                                        self.progress_bar.setValue(0)
                                        self.size_label.setText(self._fmt_size(done))

                                    # 状态文本与按钮语义
                                    if task_info.get("kind") == "active":
                                        if task_info.get("paused"):
                                            self.status_label.setText(self.root.langer.get("wid.pages.downloadList.paused"))
                                            self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.resume"))
                                        else:
                                            self.status_label.setText(self.root.langer.get("wid.pages.downloadList.active"))
                                            self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.pause"))
                                        self.btn_secondary.setText(self.root.langer.get("wid.pages.downloadList.cancel"))
                                    else:
                                        self.status_label.setText(self.root.langer.get("wid.pages.downloadList.pending"))
                                        self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.continue"))
                                        self.btn_secondary.setText(self.root.langer.get("wid.pages.downloadList.delete"))
                                    self._update_buttons()

                                def _connect_task_signals(self):
                                    """监听任务允许状态变化，即时刷新按钮。"""
                                    if self.task is not None:
                                        try:
                                            self.task.cancel_allowed_changed.connect(self._on_cancel_allowed_changed)
                                        except Exception:
                                            pass
                                        try:
                                            self.task.pause_allowed_changed.connect(self._on_pause_allowed_changed)
                                        except Exception:
                                            pass

                                def _disconnect_task_signals(self):
                                    if self.task is not None:
                                        try:
                                            self.task.cancel_allowed_changed.disconnect(self._on_cancel_allowed_changed)
                                        except Exception:
                                            pass
                                        try:
                                            self.task.pause_allowed_changed.disconnect(self._on_pause_allowed_changed)
                                        except Exception:
                                            pass

                                def _on_cancel_allowed_changed(self, allowed):
                                    self.task_info["cancel_allowed"] = bool(allowed)
                                    self._update_buttons()

                                def _on_pause_allowed_changed(self, allowed):
                                    self.task_info["pause_allowed"] = bool(allowed)
                                    self._update_buttons()

                                def _update_buttons(self):
                                    """根据任务允许状态显示/隐藏操作按钮。"""
                                    if self.task_info.get("kind") == "active":
                                        self.btn_primary.setVisible(bool(self.task_info.get("pause_allowed", True)))
                                        self.btn_secondary.setVisible(bool(self.task_info.get("cancel_allowed", True)))
                                    else:
                                        self.btn_primary.setVisible(True)
                                        self.btn_secondary.setVisible(True)

                                def _on_primary_clicked(self):
                                    # 运行中：暂停/继续；待续传：请求页面续传
                                    if self.task_info.get("kind") == "active":
                                        if self.task is not None and self.task_info.get("pause_allowed", True):
                                            if self.task_info.get("paused"):
                                                self.task.resume()
                                                self._sync_mdt_paused(False)
                                            else:
                                                self.task.pause()
                                                self._sync_mdt_paused(True)
                                    else:
                                        self.continue_requested.emit(self.task_id)

                                def _sync_mdt_paused(self, paused):
                                    """暂停/恢复时把状态写入 .Mindustrys/<name>/downloading.json（仅 mdt 游戏下载）。

                                    启动时通过 getDownloadingMdts 读取该状态同步暂停。
                                    """
                                    dest = getattr(self.task, "dest_path", "") or ""
                                    if not _is_mdt_download(dest):
                                        return
                                    dfile = os.path.join(os.path.dirname(dest), "downloading.json")
                                    try:
                                        info = {}
                                        if os.path.isfile(dfile):
                                            with open(dfile, "r", encoding="utf-8") as f:
                                                info = json.load(f)
                                        info["paused"] = bool(paused)
                                        info["updated_at"] = int(time.time())
                                        os.makedirs(os.path.dirname(dfile), exist_ok=True)
                                        with open(dfile, "w", encoding="utf-8") as f:
                                            json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                                        _state = self.root.langer.get("log.java.paused_state" if paused else "log.java.resumed_state")
                                        self.root.logger.info(t(self.root.langer.get("log.dl.mdt_paused_state"),
                                                                _state,
                                                                os.path.basename(os.path.dirname(dest)) or ""))
                                    except Exception as e:
                                        self.root.logger.warning(t(self.root.langer.get("log.dl.mdt_paused_error"), repr(e)))

                                def _on_secondary_clicked(self):
                                    # 运行中：取消（子线程执行阻塞式取消，取消后删除 mdt 目标文件夹）；
                                    # 待续传：请求页面删除
                                    if self.task_info.get("kind") == "active":
                                        if self.task is not None and self.task_info.get("cancel_allowed", True):
                                            def _do_cancel(e, t=self.task, dest=self.task_info.get("dest") or ""):
                                                try:
                                                    t.cancel(timeout=8)
                                                finally:
                                                    # mdt 游戏下载：取消后删除目标文件夹（含 downloading.json）
                                                    if dest and _is_mdt_download(dest):
                                                        mdir = os.path.dirname(dest)
                                                        try:
                                                            if os.path.isdir(mdir):
                                                                shutil.rmtree(mdir, ignore_errors=True)
                                                            self.root.logger.info(t(self.root.langer.get("log.dl.mdt_cancel_cleaned"),
                                                                                    os.path.basename(mdir) or mdir))
                                                        except Exception:
                                                            pass
                                            QThTimer.task(0, _do_cancel, dedicated=True)
                                    else:
                                        self.delete_requested.emit(self.state_file)

                    class TriBtn(QPushButton):
                        def __init__(self, logo: list, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.logo_ = logo
                            self.setLogo_ = 0
                            self.init_ui()

                        def init_ui(self):
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid", "tbtn")

                        def setLogo(self, l):
                            self.setLogo_ = l
                            self.lighting(self.root.settings["theme"])

                        def lighting(self, light: bool):
                            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                            logo = change_color(self.logo_[self.setLogo_], color)
                            pixmap = QIcon(logo.pixmap(48,48))

                            self.setIcon(pixmap)

                class TLine(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setProperty("wid", "line")
                        self.setFixedHeight(1)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        pass

                class Main(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.pages = []
                        self.btns = []
                        self.init_wid()
                        self.pages[0].click()

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop)

                        self.left = self.Left_(self,self.root)
                        self.layout.addWidget(self.left,0)
                        self.main = self.Main_(self,self.root)
                        self.layout.addWidget(self.main,1)
                        self.right = self.Right_(self,self.root)
                        self.layout.addWidget(self.right,0)

                        from src.utils.pages.start import Start
                        from src.utils.pages.download import Download
                        from src.utils.pages.game import Game
                        from src.utils.pages.setting import Setting

                        self.start = Start(self,self.root,"wid.pages.start",getPath("src/assets/buttons/start.png"))
                        self.download = Download(self,self.root,"wid.pages.download",getPath("src/assets/buttons/download.png"))
                        self.game = Game(self,self.root,"wid.pages.game",getPath("src/assets/buttons/game.png"))
                        self.setting = Setting(self,self.root,"wid.pages.setting",getPath("src/assets/buttons/setting.png"))

                    class Left_(QStackedWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root


                    class Main_(QStackedWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root

                    class Right_(QStackedWidget):
                        def __init__(self,parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root

            class FloatingStack(QWidget):
                def __init__(self,parent=None,root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.init_wid()
                    self.refresh()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0,0,0,0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.line = QWidget()
                    self.line.setProperty("wid","line")
                    self.line.setFixedHeight(1)
                    self.layout.addWidget(self.line)

                    self.l2w = QWidget()
                    self.layout.addWidget(self.l2w,1)

                    self.l2 = QHBoxLayout(self.l2w)
                    self.l2.setContentsMargins(0,0,0,0)
                    self.l2.setSpacing(0)
                    self.l2.setAlignment(Qt.AlignLeft)

                    self.left = self.Left(self,self.root)
                    self.l2.addWidget(self.left,0)

                    self.line2 = QWidget()
                    self.line2.setProperty("wid","line")
                    self.line2.setFixedWidth(1)
                    self.l2.addWidget(self.line2,0)

                    self.main = self.Main(self,self.root)
                    self.l2.addWidget(self.main,1)

                def refresh(self):
                    # 栈空时隐藏整个浮层，否则显示并提层
                    if self.main.count() <= 0:
                        self.hide()
                    else:
                        self.show()
                        self.raise_()
                    self.left.refresh()

                def add_page(self,wid):
                    # 入栈：添加页面并切换到栈顶
                    self.main.addWidget(wid)
                    self.main.setCurrentWidget(wid)
                    self.refresh()

                def pop_page(self):
                    # 出栈：移除栈顶并销毁
                    if self.main.count() <= 0:
                        return
                    wid = self.main.currentWidget()
                    self.main.removeWidget(wid)
                    on_close = getattr(wid, "on_close", None)
                    if on_close is not None:
                        on_close()
                    wid.deleteLater()
                    if self.main.count() > 0:
                        self.main.setCurrentIndex(self.main.count() - 1)
                    self.refresh()

                def clear(self):
                    while self.main.count() > 0:
                        wid = self.main.widget(0)
                        self.main.removeWidget(wid)
                        on_close = getattr(wid, "on_close", None)
                        if on_close is not None:
                            on_close()
                        wid.deleteLater()
                    self.refresh()

                class Left(QWidget):
                    def __init__(self,parent=None,root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.setFixedWidth(40)
                        self.init_wid()

                    def init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(5,5,5,5)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

                        # 内置退出按钮（左箭头，返回上一页）
                        self.back = self.Back(self,self.root)
                        self.layout.addWidget(self.back,0,Qt.AlignHCenter)

                        # 清空整个栈按钮（叉号）
                        self.btn_close = self.Close(self,self.root)
                        self.layout.addWidget(self.btn_close,0,Qt.AlignHCenter)

                    def refresh(self):
                        # 栈空时禁用两个按钮
                        enabled = self.parent.main.count() > 0
                        self.back.setEnabled(enabled)
                        self.btn_close.setEnabled(enabled)

                    class Back(QPushButton):
                        def __init__(self,parent=None,root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid","tbtn")
                            self.langing()
                            self.lighting(self.root.settings["theme"])
                            self.clicked.connect(self.parent.parent.pop_page)

                        def lighting(self, light: bool):
                            color = QColor(120,120,120) if light else QColor(200,200,200)
                            logo = change_color("src/assets/nav/back.png", color)
                            self.setIcon(QIcon(logo.pixmap(48,48)))

                        def langing(self):
                            self.setToolTip(self.root.langer.get("text.return"))

                    class Close(QPushButton):
                        def __init__(self,parent=None,root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self.setFixedSize(30,30)
                            self.setAttribute(Qt.WA_StyledBackground, False)
                            self.setProperty("wid","tbtn")
                            self.langing()
                            self.lighting(self.root.settings["theme"])
                            self.clicked.connect(self.parent.parent.clear)

                        def lighting(self, light: bool):
                            color = QColor(120,120,120) if light else QColor(200,200,200)
                            logo = change_color("src/assets/tribtns/close.png", color)
                            self.setIcon(QIcon(logo.pixmap(48,48)))

                        def langing(self):
                            self.setToolTip(self.root.langer.get("wid.top.close"))

                class Main(QStackedWidget):
                    def __init__(self,parent=None,root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.init_wid()

                    def init_wid(self):
                        # QStackedWidget 内部自带 QStackedLayout 管理页面，无需（也不能）再设置 layout
                        pass


        class Tray(QSystemTrayIcon):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.theme = None
                self.init_ui()
                self.init_wid()
                self.activated.connect(self.on_tray_activated)
                self.root.logger.info(self.root.langer.get("log.info.trayLoad"))

            def on_tray_activated(self, reason):
                if reason == QSystemTrayIcon.ActivationReason.Trigger:
                    self.root.logger.debug("Tray clicked by L-mouse button")
                    self.root.window.restore_from_tray()

            def init_ui(self):
                self.setToolTip("Book Mdt Launcher")
                self.setIcon_()
                self.show()

            def init_wid(self):
                self.menu = QMenu()

                self.menu_title = QAction("Book Mdt Launcher", self)
                self.menu_title.triggered.connect(lambda: QTimer.singleShot(0, self.root.window.restore_from_tray))
                self.menu.addAction(self.menu_title)

                self.menu.addSeparator()  # 添加分隔线

                self.menu_close = QAction("", self)
                self.menu_close.triggered.connect(QApplication.quit)
                self.menu.addAction(self.menu_close)

                self.langing()
                self.setContextMenu(self.menu)

            def langing(self):
                self.menu_close.setText(self.root.langer.get("tray.menu.close"))

            def setIcon_(self):
                """根据系统主题设置托盘图标"""
                theme = "light" if self.root.winreg.taskbar_theme() == "dark" else "dark"
                if self.theme != theme:
                    self.theme = theme
                    icon_path = getPath(f"src/assets/icons/{theme}.png")

                    # 检查文件是否存在，防止路径错误导致无图标
                    if not os.path.exists(icon_path):
                        self.root.logger.warning(t(self.root.langer.get("log.warning.trayIconPath"), icon_path))

                    icon = QIcon(icon_path)
                    self.setIcon(icon)
                    self.root.logger.info(t(self.root.langer.get("log.info.trayTheme"), "light" if theme == "light" else "dark"))

        class Logger():
            def __init__(self, parent=None, root=None):
                self.parent = parent
                self.root = root
                # 缓存已创建的 logger 实例，避免重复创建
                self._loggers = {}
                # 初始化基础配置
                self._setup_base_logging()

            def _setup_base_logging(self):
                """
                配置根 Logger ("Main") 的 Handler 和格式。
                其他子 Logger 将共享这些 Handler。
                """
                loglevel = logging.INFO
                self.base_logger_name = "Main"

                # 获取或创建主 logger
                main_logger = logging.getLogger(self.base_logger_name)
                main_logger.setLevel(loglevel)

                # 防止重复添加 handler
                if main_logger.handlers:
                    self._loggers[self.base_logger_name] = main_logger
                    return

                # 控制台 handler
                console = logging.StreamHandler()
                console.setLevel(loglevel)

                # 文件 handler 配置
                self.log_dir = getPath("BML/logs")
                os.makedirs(self.log_dir, exist_ok=True)

                now = datetime.now()
                timestamp = now.strftime("%Y%m%d%H%M%S") + f".{now.microsecond // 1000:03d}"
                timestamp_file = os.path.join(self.log_dir, f"{timestamp}.log")
                latest_file = os.path.join(self.log_dir, "latest.log")

                file_handler_timestamp = logging.FileHandler(timestamp_file, encoding="utf-8")
                file_handler_latest = logging.FileHandler(latest_file, mode='w', encoding="utf-8")

                file_handler_timestamp.setLevel(loglevel)
                file_handler_latest.setLevel(loglevel)

                # 设置日志格式：包含 %(name)s 以区分不同模块
                formatter = logging.Formatter('[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s')
                console.setFormatter(formatter)
                file_handler_timestamp.setFormatter(formatter)
                file_handler_latest.setFormatter(formatter)

                # 将 handler 添加到主 logger
                main_logger.addHandler(console)
                main_logger.addHandler(file_handler_timestamp)
                main_logger.addHandler(file_handler_latest)

                self._loggers[self.base_logger_name] = main_logger

            def _get_logger(self, name=None):
                """
                获取指定名称的 logger。
                如果 name 为 None 或 "Main"，返回主 logger。
                否则返回 "Main.{name}" 的子 logger。
                """
                if not name or name == "Main":
                    target_name = self.base_logger_name
                else:
                    # 使用层级命名，例如 "Main.Cmd"，这样它们会共享 Main 的 Handler
                    target_name = f"{self.base_logger_name}.{name}"

                if target_name not in self._loggers:
                    logger = logging.getLogger(target_name)
                    # 子 logger 默认继承父 logger 的级别和 handler，无需额外配置
                    # 但如果需要单独控制级别，可以在此设置：
                    # logger.setLevel(logging.DEBUG)
                    self._loggers[target_name] = logger

                return self._loggers[target_name]

            def _cleanup_old_logs(self):
                max_num = self.root.settings["maxLogNum"]
                if not os.path.exists(self.log_dir):
                    return
                files = [f for f in os.listdir(self.log_dir) if f.endswith('.log') and f != 'latest.log']
                files.sort()
                while len(files) > max_num:
                    oldest = files.pop(0)
                    try:
                        os.remove(os.path.join(self.log_dir, oldest))
                        # 清理日志时使用主 logger 记录
                        self._loggers[self.base_logger_name].info(t(self.root.langer.get("log.info.cleanoldlogs"), oldest))
                    except Exception as e:
                        pass

            # 修改日志方法，增加 name 参数，默认为 None (即 Main)
            def debug(self, msg, name=None):
                self._get_logger(name).debug(msg)

            def info(self, msg, name=None):
                self._get_logger(name).info(msg)

            def warning(self, msg, name=None):
                self._get_logger(name).warning(msg)

            def error(self, msg, name=None, exc_info=False):
                self._get_logger(name).error(msg, exc_info=exc_info)

            def critical(self, msg, name=None):
                self._get_logger(name).critical(msg)

        class Langer():
            def __init__(self, parent=None, root=None):
                self.parent = parent
                self.root = root

                # 确定最终使用的语言
                final_lang = self.root.settings["language"]

                # 1. 检查配置的语言是否可用
                if final_lang not in self.get_langs():
                    if final_lang is not None:
                        self.root.logger.warning(f"Language '{final_lang}' not found, using system display language: " + str(self.root.winreg.display_language()))

                    # 2. 尝试使用系统语言
                    sys_lang = self.root.winreg.display_language()
                    if sys_lang and sys_lang in self.get_langs():
                        final_lang = sys_lang
                    else:
                        # 3.  fallback 到 en-US
                        if sys_lang:
                            self.root.logger.warning(f"System display language '{sys_lang}' not found, using: en-US")
                        else:
                            self.root.logger.warning("System display language detection failed, using: en-US")
                        final_lang = "en-US"

                    # 更新设置中的语言为最终确定的语言
                    self.root.settings["language"] = final_lang
                    self.root.saveSettings()

                self.current_lang = final_lang
                self.default_lang = "en-US"  # 定义默认回退语言

                self.load(self.current_lang)

            def load(self, lang):
                """加载语言文件并自动刷新所有支持多语言的控件"""
                lang_path = getPath(f"src/lang/{lang}.json")
                default_lang_path = getPath(f"src/lang/{self.default_lang}.json")

                try:
                    with open(lang_path, "r", encoding="utf-8") as f:
                        self.langs = json.load(f)
                    self.parent.settings["language"] = lang
                except Exception as e:
                    self.root.logger.error(f"Failed to load language file {lang_path}: {e}")
                    self.langs = {}

                # 预加载默认语言以便快速回退，避免每次get都读取文件
                try:
                    if lang != self.default_lang:
                        with open(default_lang_path, "r", encoding="utf-8") as f:
                            self.default_langs = json.load(f)
                    else:
                        self.default_langs = self.langs
                except Exception as e:
                    self.root.logger.warning(f"Failed to load default language file {default_lang_path}: {e}")
                    self.default_langs = {}

                # 自动加载每个控件里的 langing 模块
                try:
                    self._refresh_all_widgets()
                    self.root.tray.langing()
                except:
                    pass

            def _refresh_all_widgets(self):
                """递归查找所有控件并调用 langing 方法"""
                def notify_langing(widget):
                    # 检查是否有 langing 方法且可调用
                    if hasattr(widget, 'langing') and callable(widget.langing):
                        try:
                            widget.langing()
                        except Exception as e:
                            # 避免因为某个控件翻译失败导致整个程序崩溃
                            self.root.logger.debug(f"Error calling langing on {widget}: {e}")

                    # 递归处理子控件
                    for child in widget.children():
                        notify_langing(child)

                # 从主窗口开始遍历
                if hasattr(self.root, 'window') and self.root.window:
                    QTimer.singleShot(0, lambda: notify_langing(self.root.window))
                self.root.logger.info(self.get("init.load"))

            def get(self, key):
                """
                获取翻译文本，支持三级回退：
                1. 当前语言 (zh-CN)
                2. 默认语言 (en-US)
                3. 原键名
                """
                if key in self.langs:
                    return self.langs[key]
                if key in self.default_langs:
                    return self.default_langs[key]
                return key

            def get_langs(self):
                langs = []
                lang_dir = getPath("src/lang")
                try:
                    if not os.path.exists(lang_dir):
                        return langs
                    for file in os.listdir(lang_dir):
                        if file.endswith(".json"):
                            langs.append(file.replace(".json", ""))
                except Exception as e:
                    self.root.logger.error(f"Failed to list language files: {e}")
                return langs

            def get_langs_info(self):
                """
                获取所有语言文件的名称及 init 信息。
                返回字典：键为语言文件名（不带后缀），值为列表 [init, init.en]
                """
                info = {}
                lang_dir = getPath("src/lang")
                try:
                    if not os.path.exists(lang_dir):
                        return info
                    for file in os.listdir(lang_dir):
                        if file.endswith(".json"):
                            lang_name = file.replace(".json", "")
                            lang_path = os.path.join(lang_dir, file)
                            try:
                                with open(lang_path, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                info[lang_name] = [
                                    data.get("init", lang_name),
                                    data.get("init.en", lang_name)
                                ]
                            except Exception as e:
                                self.root.logger.error(f"Failed to read language file {lang_path}: {e}")
                                info[lang_name] = [lang_name, lang_name]
                except Exception as e:
                    self.root.logger.error(f"Failed to list language files: {e}")
                return info

        class Signals(QObject):
            """
            动态信号管理器 —— 所有信号都是真正的 PySide6 Signal。

            用法:
                signals = Signals()
                signals.register("dataReady", Signal(str, int))
                signals.connect("dataReady", lambda s, i: print(s, i))
                signals.emit("dataReady", "hello", 42)
                signals.disconnect("dataReady", callback)
                signals.cancel("dataReady")  # 完全移除
            """

            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                # name → _SignalHolder 实例
                self._holders = {}

            @staticmethod
            def _make_holder_cls(sig):
                """根据 Signal 签名动态创建一个 QObject 子类，携带一个 signal 属性。"""
                return type('_SigHolder', (QObject,), {'signal': sig})

            def register(self, name, sig=None):
                """
                注册一个信号。
                sig: Signal 实例，如 Signal(), Signal(str), Signal(int, bool)
                返回该 Signal，可直接 connect。
                若同名已存在则返回已有信号。
                """
                if sig is None:
                    sig = Signal()
                if name in self._holders:
                    return self._holders[name].signal
                HolderCls = self._make_holder_cls(sig)
                holder = HolderCls(self)
                self._holders[name] = holder
                return holder.signal

            def connect(self, name, callback):
                """连接到已注册信号。若未注册则自动以无参信号注册。"""
                if name not in self._holders:
                    self.register(name)
                self._holders[name].signal.connect(callback)

            def emit(self, name, *args):
                """触发指定信号。"""
                if name in self._holders:
                    self._holders[name].signal.emit(*args)

            def disconnect(self, name=None, callback=None):
                """
                断开连接。
                - disconnect(name, callback): 断开指定回调
                - disconnect(name): 断开该信号所有连接
                - disconnect(): 断开所有信号所有连接
                """
                if name is None:
                    for h in self._holders.values():
                        try:
                            h.signal.disconnect()
                        except TypeError:
                            pass
                    return
                if name not in self._holders:
                    return
                sig = self._holders[name].signal
                if callback is not None:
                    try:
                        sig.disconnect(callback)
                    except TypeError:
                        pass
                else:
                    try:
                        sig.disconnect()
                    except TypeError:
                        pass

            def cancel(self, name):
                """完全移除指定信号及其所有连接。"""
                if name in self._holders:
                    self._holders[name].signal.disconnect()
                    self._holders[name].deleteLater()
                    del self._holders[name]

            def clear(self, name):
                """清除指定信号的所有回调（不删除信号本身）。"""
                if name in self._holders:
                    try:
                        self._holders[name].signal.disconnect()
                    except TypeError:
                        pass

        class Winreg():
            def __init__(self, parent=None, root=None):
                self.parent = parent
                self.root = root

            def display_language(self):
                try:
                    dll = ctypes.windll.kernel32
                    langId = dll.GetUserDefaultUILanguage()
                    langStr = locale.windows_locale.get(langId)
                    if langStr:
                        return langStr.replace("_", "-")
                except Exception as e:
                    self.root.logger.error(f"Failed to get language, using en-US: {e}")
                return "en-US"

            def taskbar_theme(self):
                """
                获取 Windows 系统外壳主题颜色 (light/dark)
                """
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                    value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
                    return "light" if value == 1 else "dark"
                except Exception as e:
                    self.root.logger.warning(f"Failed to get system theme: {e}")
                    return "light"

    if __name__ == "__main__":
        app = QApplication(sys.argv)
        socket = QLocalSocket()
        socket.connectToServer("BookMdtLauncherMI")

        if socket.waitForConnected(200):
            socket.write(b"MAINWINSHOW")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            sys.exit(0)
        else:
            socket.deleteLater()

            main = Main(app)
            main.window.show()
            code = app.exec()
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(code)

except Exception as e:
    err_msg = traceback.format_exc()

    print(err_msg)

    dialog = QDialog()
    dialog.setWindowTitle("Book MDT Launcher - Error")
    dialog.setMinimumSize(550, 400)
    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)
    layout.setContentsMargins(15, 15, 15, 15)

    info_label = QLabel(
        "启动器貌似出现了一点问题，请带上下面这段错误信息前往 "
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues 提交反馈\n\n"
        "The launcher seems to have encountered a problem. Please take the"
        "following error message and submit feedback at "
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues \n"
    )
    info_label.setWordWrap(True)
    info_label.setStyleSheet("font-size: 13px;")
    layout.addWidget(info_label)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setPlainText(err_msg)
    text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
    layout.addWidget(text_edit, 1)

    btn_layout = QHBoxLayout()
    btn_layout.addStretch()

    skip_btn = QPushButton("跳转 Skip")
    skip_btn.setFixedWidth(120)
    skip_btn.clicked.connect(lambda: webbrowser.open(
        "https://github.com/ch-BookBanana/BookMdtLauncher/issues"
    ))
    btn_layout.addWidget(skip_btn)

    cancel_btn = QPushButton("取消 Cancel")
    cancel_btn.setFixedWidth(120)
    cancel_btn.clicked.connect(dialog.reject)
    btn_layout.addWidget(cancel_btn)

    layout.addLayout(btn_layout)

    dialog.rejected.connect(QApplication.quit)
    dialog.exec()
    # 出错分支同样强制退出，避免残留线程导致挂起/崩溃弹窗
    os._exit(1)