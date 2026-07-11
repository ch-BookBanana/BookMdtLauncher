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

init = {
    "version": "26-T0605",
    "BuildCode": "10000.0"
}


from PyQt5.Qt import *
import sys, os, json, copy, winreg, logging, glob, locale, hashlib
from datetime import datetime
import ctypes
import ctypes.wintypes
from src.utils.path_utils import getPath
from src.utils.mdtScanner import mdtScanner
from src.utils.mdtLauncher import mdtLauncher
from src.utils.QThTimer import QThTimer


def change_color(path, color: QColor):
    """白底png改色"""
    pix = QPixmap(getPath(path))
    colored = QPixmap(pix.size())
    colored.fill(Qt.transparent)
    painter = QPainter(colored)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), color)
    painter.end()
    return QIcon(colored)

def pngSha(path):
    """计算png的sha256"""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(65536)  # 64KB
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()
def t(text, *args):
    try:
        for i, arg in enumerate(reversed(args), start=1):
            text = text.replace(f"${i}", str(arg))
    except Exception:
        pass
    return text


class Leftw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(None)
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.left.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.left.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width

    # def showEvent(self, event):
    #     self.parent.parent.left.setFixedWidth(self.width_)
    #     super().showEvent(event)

       
class Mainw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.parent.parent.main.addWidget(self)

class Rightw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.right.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.right.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width

    # def showEvent(self,event):
    #     super().showEvent(event)
    #     self.parent.parent.left.setFixedWidth(self.width_)

class Main():
    def __init__(self,app):
        self.app = app
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
            "checkTime": 2000,
            "theme": 0,
            "maxLogNum": 50,
            "closeByTray": True,
            "defaultGame": None,
            "githubToken": [],
            "javaPath": []
        }
        self.settings = copy.deepcopy(self.defsettings)
        app.aboutToQuit.connect(self.saveSettings)

        def deep_merge_settings(default, file_settings):
            for key, value in file_settings.items():
                if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                    deep_merge_settings(default[key], value)
                elif key in default:
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

        self.langer = self.Langer(self, self)
        self.logger._cleanup_old_logs()

        self.saveSettings()

        self.launcher = mdtLauncher()

        self.tray = self.Tray(self, self)
        self.window = self.Window(self, self)

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
            if eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(message.__int__())

                #
                if msg.message == 0x0084:
                    if not self.isMaximized():
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
                    self.move_mousepos_ = event.globalPos()
                    super().mousePressEvent(event)

                def mouseMoveEvent(self, event):
                    if self.move_pressed:
                        if self.root.window.isMaximized():
                            self.root.window.showNormal()
                        self.move_mousepos = event.globalPos()
                        self.move_moving = True
                        screensize = QScreen.availableGeometry(QApplication.primaryScreen())
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
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignRight)

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
                    self.layout.addSpacing(5)

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

                    self.start = self.Start(self,self.root,"wid.pages.start",getPath("src/assets/buttons/start.png"))
                    self.download = self.Download(self,self.root,"wid.pages.download",getPath("src/assets/buttons/download.png"))
                    self.game = self.Game(self,self.root,"wid.pages.game",getPath("src/assets/buttons/game.png"))
                    self.setting = self.Setting(self,self.root,"wid.pages.setting",getPath("src/assets/buttons/setting.png"))

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

            
                class Page():
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.text = text
                        self.logo = logo
                        self.init_wid()
                        self.id = len(self.parent.pages)
                        self.parent.pages.append(self)
                        self.btn = self.root.window.left.pagebtns.add_btn(self.text,self.logo)
                        self.parent.btns.append(self)
                        self.btn.clicked.connect(self.changePage)

                    def changePage(self):
                        self.parent.left.setCurrentWidget(self.left)
                        self.parent.main.setCurrentWidget(self.main)
                        self.parent.right.setCurrentWidget(self.right)
                        self.parent.left.setFixedWidth(self.left.width_)
                        self.parent.right.setFixedWidth(self.right.width_)

                    def click(self):
                        self.btn.click()

                    def init_wid(self):
                        cls_left = self.Left if hasattr(self, 'Left') else Leftw
                        self.left = cls_left(self, self.root)

                        cls_main = self.Main if hasattr(self, 'Main') else Mainw
                        self.main = cls_main(self, self.root)

                        cls_right = self.Right if hasattr(self, 'Right') else Rightw
                        self.right = cls_right(self, self.root)

                class Start(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        root.signals.register("start_gameChanged")
                        super().__init__(parent, root, text, logo)
                        QThTimer.taskP(2000, self.left.changeTimer, [self.left.sets])
                        QThTimer.task(self.left.changeTimer, [self.left.sets], None ,0)

                    def changeGame(self, game=None):
                        if game not in mdtScanner.getMdts():
                            if len(mdtScanner.getMdts()) == 0:
                                self.root.settings["defaultGame"] = None
                            else:
                                self.root.settings["defaultGame"] = game
                            self.root.signals.emit("start_gameChanged", game)
                            

                    class Left(Leftw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent, root)
                            self.resize_(250)
                            self.init_wid()
                            self.game = {
                                "icon": None,
                                "name": None,
                                "vers": None
                            }

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0,0,0,0)
                            self.layout.setSpacing(0)
                            self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

                            self.layout.addSpacing(40)
                            self.icon = QLabel(self)
                            self.icon.setFixedSize(120,120)
                            self.icon.setScaledContents(True)
                            self.icon.setProperty("wid", "png")
                            self.layout.addWidget(self.icon, 0, Qt.AlignHCenter)
                            self.layout.addSpacing(20)

                            self.gameTxt = QLabel()
                            self.gameTxt.setProperty("wid","title")
                            self.gameTxt.setStyleSheet("font-size:20px")
                            self.layout.addWidget(self.gameTxt, 0, Qt.AlignHCenter)
                            self.gameTxt.setText("游戏名")

                            self.versTxt = QLabel()
                            self.versTxt.setProperty("wid","title")
                            self.versTxt.setStyleSheet("font-size:12px")
                            self.layout.addWidget(self.versTxt, 0, Qt.AlignHCenter)
                            self.versTxt.setText("版本")

                            self.layout.addSpacing(30)
                            self.main = QStackedWidget()
                            self.layout.addWidget(self.main,1)

                        def sets(self,icon=(False,None),gameTxt=(False,None),versTxt=(False,None)):
                            if icon[0]:
                                self.icon.setPixmap(QPixmap(icon[1]))
                            if gameTxt[0]:
                                self.gameTxt.setText(QFontMetrics(self.gameTxt.font()).elidedText(gameTxt[1], Qt.ElideRight, 150))
                            if versTxt[0]:
                                self.versTxt.setText(QFontMetrics(self.versTxt.font()).elidedText(versTxt[1], Qt.ElideRight, 130))

                        def changeTimer(self,event):
                            i = [(False,None),(False,None),(False,None)]
                            if len(mdtScanner.getMdts()) == 0:
                                self.root.settings["defaultGame"] = None
                            elif self.root.settings["defaultGame"] is None:
                                self.root.settings["defaultGame"] = mdtScanner.getMdts()[0]
                            if self.game["name"] != self.root.settings["defaultGame"]:
                                if self.root.settings["defaultGame"] is None:
                                    i[1] = (True,self.root.langer.get("wid.pages.start.left.noGame"))
                                    i[2] = (True,self.root.langer.get("wid.pages.start.left.DGame"))
                                    self.game["name"] = self.game["vers"] = None
                                else:
                                    game = self.root.settings["defaultGame"]
                                    self.game["name"] = game
                                    vers = mdtScanner.getMdtMsg(game)
                                    self.game["vers"] = f"v{vers['number']}.{vers['build']}{vers['modifier']}"
                                    i[1] = (True,game)
                                    i[2] = (True,self.game["vers"])
                            if self.game["name"] is not None:
                                vers = f"v{mdtScanner.getMdtMsg(self.game['name'])['number']}.{mdtScanner.getMdtMsg(self.game['name'])['build']}{mdtScanner.getMdtMsg(self.game['name'])['modifier']}"
                                if self.game["vers"] != vers:
                                    self.game["vers"] = vers
                                    i[2] = (True,vers)
                            if self.game["name"] is not None and mdtScanner.getMdtMsg(self.game["name"])["icon"]:
                                png = pngSha(mdtScanner.getMdtMsg(self.game["name"])["icon"])
                            else:
                                png = None
                            if self.game["icon"] != png:
                                self.game["icon"] = png
                                i[0] = (True,QPixmap(mdtScanner.getMdtMsg(self.game["name"])["icon"]) if self.game["name"] is not None else QPixmap())
                            if i[0][0] or i[1][0] or i[2][0]:
                                event.lambdas[0].emit(i[0],i[1],i[2])
                            
                                    



                    class Main(Mainw):
                        def __init__(self,parent=None,root=None):
                            super().__init__(parent,root)
                            self.init_wid()

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setContentsMargins(0,0,0,0)
                            self.layout.setSpacing(0)
                            self.backg = self.Backg(self,self)
                            self.layout.addWidget(self.backg)

                            self.lay2 = QHBoxLayout(self.backg)
                            self.lay2.setContentsMargins(0,0,0,0)
                            self.lay2.setSpacing(0)
                            self.stack = QStackedWidget()
                            self.stack.setStyleSheet("background:transparent;")
                            self.lay2.addWidget(self.stack)

                            self.start = self.Start(self,self.root)

                        class _Main(QWidget):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent)
                                self.parent = parent
                                self.root = root
                                self.index = self.parent.stack.addWidget(self)

                        class Start(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.init_ui()
                                self.init_wid()

                            def init_ui(self):
                                self.setAttribute(Qt.WA_StyledBackground, False)

                            def init_wid(self):
                                self.layout = QGridLayout(self)
                                self.layout.setContentsMargins(30,30,30,30)
                                self.layout.setSpacing(5)

                                self.layout.setColumnStretch(0,1)
                                self.layout.setColumnStretch(1,0)
                                self.layout.setColumnStretch(2,0)
                                self.layout.setRowStretch(0,1)
                                self.layout.setRowStretch(1,0)
                                self.layout.setRowStretch(2,0)

                                self.start = self.Btn(self,self.root,"255,184, 0")
                                self.start.setFixedSize(180,50)
                                self.layout.addWidget(self.start,1,1,1,2)
                                QTimer.singleShot(10, lambda: print(self.start.x(),self.start.y(),self.start.width(),self.start.height()))
                                
                                self.settings = self.Btn(self,self.root,"110,65,151")
                                self.settings.setFixedSize(50,50)
                                self.layout.addWidget(self.settings,2,2,1,1)

                            class Btn(QPushButton):
                                def __init__(self,parent=None,root=None,color="0,0,0"):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.color = color
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.setStyleSheet(f"""
                                        QPushButton{{
                                            background-color:rgba({self.color},0.4);
                                            color:white;
                                            border-radius:10px;
                                            font-size:20px;

                                        }}
                                        QPushButton:hover{{
                                            background-color:rgba({self.color},1);
                                        }}
                                    """)




                        class Backg(QWidget):
                            def __init__(self,parent=None,root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.png = 0
                                self.pixs = [None,None]
                                self.init_wid()
                                self.setPixmap(QPixmap(getPath("src/assets/backg/1.png")))

                            def init_wid(self):
                                self.pngs = [QLabel(self),QLabel(self)]
                                

                                self.shadow = QWidget(self)
                                self.shadow.setAttribute(Qt.WA_StyledBackground, True)
                                self.shadow.setProperty("wid", "shadow")

                                self.pngs[1].hide()
                                self.resizeEvent(None)
                                
                            def setPixmap(self,pix=None):
                                self.pixs[1-self.png] = pix
                                self.pngs[1-self.png].hide()
                                pix = self.pixs[1-self.png].scaled(
                                    self.size(),
                                    Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation
                                ) if self.pixs[1-self.png] is not None else QPixmap()
                                self.pngs[1-self.png].setPixmap(pix)
                                self.pngs[1-self.png].stackUnder(self.shadow)
                                self.pngs[1-self.png].show()
                                self.png = 1-self.png
                                

                            def resizeEvent(self,event):
                                for i,n in enumerate(self.pngs,start=0):
                                    n.setFixedSize(self.size())
                                    pix = self.pixs[i].scaled(
                                            self.size(),
                                            Qt.KeepAspectRatioByExpanding,
                                            Qt.SmoothTransformation
                                    ) if self.pixs[i] is not None else QPixmap()
                                    n.setPixmap(pix)
                                self.shadow.setGeometry(0,0,200,self.height())
                                super().resizeEvent(event)


                class Download(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                class Game(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                class Setting(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                    class Left(Leftw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent, root)
                            self.resize_(120)
                            self.init_wid()


                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)

                            self.scroll = QScrollArea(self)
                            self.scroll.setWidgetResizable(True)
                            self.scroll.setFrameShape(QFrame.NoFrame)
                            self.layout.addWidget(self.scroll)

                            self.main = QWidget()
                            self.scroll_layout = QVBoxLayout(self.main)
                            self.scroll_layout.setContentsMargins(0, 0, 0, 0)
                            self.scroll_layout.setSpacing(0)
                            self.scroll_layout.setAlignment(Qt.AlignTop)
                            self.scroll.setWidget(self.main)
                            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

                            self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                            
                            self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                            self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                            self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                            self.bthGroup = QButtonGroup(self)

                        def add_btn(self, text=None, icon=None):
                            btn = self.Btns(text, icon, self, self.root)
                            self.scroll_layout.addWidget(btn)
                            self.bthGroup.addButton(btn)
                            self.barShow()
                            return btn

                        def barShow(self):
                            self.scroll_slider.setVisible(self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum())

                        def resizeEvent(self,event):
                            self.scroll_slider.setGeometry(self.scroll.width()-5,0,5,self.scroll.height())
                            self.barShow()
                            super().resizeEvent(event)

                        def showEvent(self,event):
                            super().showEvent(event)
                            self.barShow()


                        class Btns(QPushButton):
                            def __init__(self, text=None, icon=None, parent=None, root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.text_ = text
                                self.icon_ = icon
                                self.init_ui()
                                self.init_wid()

                            def init_ui(self):
                                self.setFixedSize(120, 30)
                                self.setAttribute(Qt.WA_StyledBackground, False)
                                self.setProperty("wid", "lbtn")
                                self.setCheckable(True)

                            def init_wid(self):
                                self.layout = QHBoxLayout(self)
                                self.layout.setContentsMargins(0, 0, 0, 0)
                                self.layout.setSpacing(5)

                                self.icon = QLabel()
                                self.icon.setAttribute(Qt.WA_StyledBackground, False)
                                self.icon.setFixedSize(30, 30)
                                self.icon.setScaledContents(False)
                                self.layout.addWidget(self.icon)
                                self.icon.setAlignment(Qt.AlignCenter)

                                self.text = QLabel()
                                self.text.setAttribute(Qt.WA_StyledBackground, False)
                                self.text.setFixedSize(90, 30)
                                self.text.setProperty("wid", "lbtn")
                                self.langing()
                                self.layout.addWidget(self.text)

                            def langing(self):
                                if self.text_ is not None:
                                    self.text.setText(self.root.langer.get(self.text_))
                                    self.setToolTip(self.root.langer.get(self.text_))

                            def lighting(self, light: bool):
                                if self.icon_ is not None:
                                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                                    logo = change_color(self.icon_, color)
                                    pixmap = logo.pixmap(30,30)

                                    if not pixmap.isNull():
                                        smooth_pixmap = pixmap.scaled(
                                            22, 22,
                                            Qt.KeepAspectRatio,
                                            Qt.FastTransformation
                                        )
                                        self.icon.setPixmap(smooth_pixmap)
                                    else:
                                        self.root.logger.warning(f"Failed to load pixmap for {self.icon_}")


                            def setText(self, _text):
                                self.text_ = _text
                                self.langing()

                            def setIcon(self, _icon):
                                self.icon_ = _icon
                                self.lighting(self.root.settings["theme"])
                    
                    class Main(Mainw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent, root)
                            self.init_wid()
                            self.btns_[0].click()

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)
                            self.layout.setAlignment(Qt.AlignLeft)

                            self.line = QWidget()
                            self.line.setProperty("wid", "line")
                            self.line.setAttribute(Qt.WA_StyledBackground,True)
                            self.line.setFixedWidth(1)
                            self.layout.addWidget(self.line,0)

                            self.pages = QStackedWidget()
                            self.layout.addWidget(self.pages,1)

                            self.pages_ = []
                            self.btns_ = []


                            self.launcher = self.add_page("wid.pages.setting.launcher","src/assets/icons/units.png",self.Launcher)

                            

                        def add_page(self,text=None,icon=None,page=None):
                            if page is None: page = self.Page
                            btn = self.parent.left.add_btn(text,icon)
                            page_ = page(self,self.root,text,icon)
                            self.pages_.append(page_)
                            self.btns_.append(btn)
                            self.pages.addWidget(page_)
                            page_.btn = btn
                            btn.clicked.connect(lambda: self.pages.setCurrentWidget(page_))
                            return page_

                        class Page(QWidget):
                            def __init__(self,parent=None,root=None,text=None,icon=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.text=text
                                self.icon=icon

                                self._init_wid()

                            def _init_wid(self):
                                self.layout = QVBoxLayout(self)
                                self.layout.setContentsMargins(0, 0, 0, 0)
                                self.layout.setSpacing(0)
                                self.layout.setAlignment(Qt.AlignHCenter)

                                self.scroll = QScrollArea(self)
                                self.scroll.setStyleSheet("max-width: 600px;")
                                self.scroll.setWidgetResizable(True)
                                self.scroll.setFrameShape(QFrame.NoFrame)
                                self.layout.addWidget(self.scroll)

                                self.main = QWidget()
                                
                                self.scroll_layout = QVBoxLayout(self.main)
                                self.scroll_layout.setContentsMargins(30,0,30,0)
                                self.scroll_layout.setSpacing(0)
                                self.scroll_layout.setAlignment(Qt.AlignTop)
                                self.scroll.setWidget(self.main)
                                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

                                self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                                
                                self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                                self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                                self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                                self._title = QLabel()
                                self._title.setProperty("wid", "title")
                                self._title.setFixedHeight(38)
                                self._title.setStyleSheet("font-size: 28px;")
                                self._title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                                self.scroll_layout.addWidget(self._title)
                                self.langing()

                            def langing(self):
                                self._title.setText(self.root.langer.get(self.text))
                            
                            class Bool(QWidget):
                                push = pyqtSignal(bool)
                                def __init__(self,parent=None,root=None,text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.text_ = text
                                    self.intro_ = ""
                                    self.tips_ = ""
                                    self.btnpix = [QPixmap()]*2
                                    self.introable = False
                                    self.tipsable = False
                                    self.init_wid()
                                    self.parent.scroll_layout.addWidget(self)
                                
                                def init_wid(self):
                                    self.setFixedHeight(40)
                                    self.layout = QHBoxLayout(self)
                                    self.layout.setAlignment(Qt.AlignVCenter)
                                    self.layout.setContentsMargins(0, 0, 0, 0)
                                    self.layout.setSpacing(5)

                                    self.btn = QPushButton()
                                    self.btn.setProperty("wid","check")
                                    self.btn.setFixedSize(20,20)
                                    self.btn.setCheckable(True)
                                    self.layout.addWidget(self.btn,0)

                                    self.text = QLabel()
                                    self.text.setProperty("wid","text")
                                    self.text.setStyleSheet("font-size: 17px;")
                                    self.text.setAlignment(Qt.AlignVCenter)
                                    self.layout.addWidget(self.text,0)
                                    self.text.setFixedHeight(30)

                                    self.layout.addStretch(1)

                                    self.intro = QLabel()
                                    self.layout.addWidget(self.intro)
                                    self.intro.hide()
                                    self.intro.setFixedSize(20,20)

                                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    intr = self.intro.sizePolicy()
                                    intr.setRetainSizeWhenHidden(True)
                                    self.intro.setSizePolicy(intr)

                                    self.tips = QLabel()
                                    self.layout.addWidget(self.tips)
                                    self.tips.hide()
                                    self.tips.setFixedSize(20,20)

                                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    tip = self.tips.sizePolicy()
                                    tip.setRetainSizeWhenHidden(True)
                                    self.tips.setSizePolicy(intr)

                                    self.langing()
                                    self.lighting(self.root.settings["theme"])
                                    self.btn.toggled.connect(self.btnEvent)
                                    self.btn.setIcon(QIcon(self.btnpix[0]))

                                def btnEvent(self,booll):
                                    self.push.emit(booll)
                                    self.btn.setIcon(QIcon(self.btnpix[1 if booll else 0]))

                                def setToolBar(self,wid,shown=None,text=None):
                                    if wid == "intro":
                                        if shown is not None:
                                            self.introable = shown
                                            self.intro.setVisible(shown)
                                        if text is not None: self.intro_ = text
                                    if wid == "tips":
                                        if shown is not None:
                                            self.tipsable = shown
                                            self.tips.setVisible(shown)
                                        if text is not None: self.tips_ = text
                                        self.lighting(self.root.settings["theme"])
                                        self.langing()

                                def langing(self):
                                    self.text.setText(self.root.langer.get(self.text_))
                                    self.intro.setToolTip(self.root.langer.get(self.intro_))
                                    self.tips.setToolTip(self.root.langer.get(self.tips_))

                                def lighting(self,light):
                                    self.btnpix =[change_color(getPath("src/assets/actions/btn_on.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(35,35)),change_color(getPath("src/assets/actions/btn_off.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(35,35))]
                                    if self.introable:
                                        self.intro.setPixmap(change_color(getPath("src/assets/actions/intro.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
                                    if self.tipsable:
                                        self.tips.setPixmap(change_color(getPath("src/assets/actions/tips.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))

                            class Line(QWidget):
                                def __init__(self,parent=None,root=None,text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.init_wid()
                                    self.parent.scroll_layout.addWidget(self)
                                
                                def init_wid(self):
                                    self.setFixedHeight(1)
                                    self.layout = QHBoxLayout(self)
                                    self.layout.setContentsMargins(10, 0, 10, 0)
                                    self.line = QWidget()
                                    self.line.setProperty("wid","line")

                            class Title(QWidget):
                                def __init__(self,parent=None,root=None,text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.text_ = text
                                    self.init_wid()
                                    self.parent.scroll_layout.addSpacing(30)
                                    self.parent.scroll_layout.addWidget(self)
                                
                                def init_wid(self):
                                    self.setFixedHeight(40)
                                    self.layout = QHBoxLayout(self)
                                    self.layout.setContentsMargins(0, 0, 0, 0)
                                    self.layout.setSpacing(15)

                                    self.l1 = QWidget()
                                    self.l1.setProperty("wid","line")
                                    self.l1.setFixedHeight(1)
                                    self.layout.addWidget(self.l1,1)

                                    self.text = QLabel()
                                    self.text.setProperty("wid","text")
                                    self.text.setStyleSheet("font-size: 22px;")
                                    self.langing()
                                    self.layout.addWidget(self.text,0)
                                    
                                    self.l2 = QWidget()
                                    self.l2.setProperty("wid","line")
                                    self.l2.setFixedHeight(1)
                                    self.layout.addWidget(self.l2,1)

                                def langing(self):
                                    self.text.setText(self.root.langer.get(self.text_))

                            class Slider(QWidget):
                                push = pyqtSignal(int)
                                def __init__(self,parent=None,root=None,text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.text_ = text
                                    self.intro_ = ""
                                    self.tips_ = ""
                                    self.val = lambda i: str(i)
                                    self.introable = False
                                    self.tipsable = False
                                    self.init_wid()
                                    self.parent.scroll_layout.addWidget(self)

                                def init_wid(self):
                                    class Slid(QSlider):
                                        def _get_handle_rect(self):
                                            opt = QStyleOptionSlider()
                                            self.initStyleOption(opt)
                                            return self.style().subControlRect(
                                                QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
                                            )

                                        def _pos_to_value(self, pos):
                                            handle_rect = self._get_handle_rect()
                                            
                                            if self.orientation() == Qt.Horizontal:
                                                span = self.width() - handle_rect.width()
                                                if span <= 0: return self.minimum()
                                                pos_in_span = pos.x() - handle_rect.width() / 2.0
                                                pos_in_span = max(0.0, min(span, pos_in_span))
                                                ratio = pos_in_span / span
                                            else:
                                                span = self.height() - handle_rect.height()
                                                if span <= 0: return self.minimum()
                                                pos_in_span = (self.height() - pos.y()) - handle_rect.height() / 2.0
                                                pos_in_span = max(0.0, min(span, pos_in_span))
                                                ratio = pos_in_span / span
                                            return self.minimum() + round(ratio * (self.maximum() - self.minimum()))

                                        def mousePressEvent(self, event):
                                            if event.button() == Qt.LeftButton:
                                                handle_rect = self._get_handle_rect()
                                                self.setValue(self._pos_to_value(event.pos()))
                                                self.sliderPressed.emit()
                                                self.sliderMoved.emit(self.value())
                                                event.accept()
                                            else: super().mousePressEvent(event)

                                        def mouseMoveEvent(self, event):
                                            if event.buttons() & Qt.LeftButton:
                                                handle_rect = self._get_handle_rect()
                                                self.setValue(self._pos_to_value(event.pos()))
                                                self.sliderMoved.emit(self.value())
                                                event.accept()
                                                return
                                            super().mouseMoveEvent(event)

                                    self.setFixedHeight(40)
                                    self.layout = QHBoxLayout(self)
                                    self.layout.setContentsMargins(0, 0, 0, 0)
                                    self.layout.setSpacing(5)
                                    self.scroll = Slid(Qt.Horizontal)
                                    self.scroll.setProperty("wid","mdt")
                                    self.scroll.setFixedHeight(30)
                                    self.layout.addWidget(self.scroll)
                                    self.scroll.valueChanged.connect(self.pushEvent)

                                    self.intro = QLabel()
                                    self.layout.addWidget(self.intro)
                                    self.intro.hide()
                                    self.intro.setFixedSize(20,20)

                                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    intr = self.intro.sizePolicy()
                                    intr.setRetainSizeWhenHidden(True)
                                    self.intro.setSizePolicy(intr)

                                    self.tips = QLabel()
                                    self.layout.addWidget(self.tips)
                                    self.tips.hide()
                                    self.tips.setFixedSize(20,20)

                                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    tip = self.tips.sizePolicy()
                                    tip.setRetainSizeWhenHidden(True)
                                    self.tips.setSizePolicy(intr)
                                    
                                    self.lay2 = QHBoxLayout(self.scroll)
                                    self.lay2.setContentsMargins(5, 0, 5, 0)
                                    self.lay2.setSpacing(0)
                                    self.lay2.setAlignment(Qt.AlignVCenter)

                                    self.text = QLabel()
                                    self.text.setProperty("wid","text")
                                    self.text.setStyleSheet("font-size: 17px;")
                                    self.text.setAlignment(Qt.AlignVCenter)
                                    self.text.setFixedHeight(30)
                                    self.lay2.addWidget(self.text)
                                    self.text.setAttribute(Qt.WA_TranslucentBackground)

                                    self.lay2.addStretch(1)

                                    self.value = QLabel()
                                    self.value.setProperty("wid","text")
                                    self.value.setStyleSheet("font-size: 17px;")
                                    self.value.setAlignment(Qt.AlignVCenter)
                                    self.value.setFixedHeight(30)
                                    self.lay2.addWidget(self.value)
                                    self.value.setAttribute(Qt.WA_TranslucentBackground)

                                    self.langing()

                                def lighting(self,light):
                                    if self.introable:
                                        self.intro.setPixmap(change_color(getPath("src/assets/actions/intro.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
                                    if self.tipsable:
                                        self.tips.setPixmap(change_color(getPath("src/assets/actions/tips.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))

                                def langing(self):
                                    self.text.setText(self.root.langer.get(self.text_))
                                    self.intro.setToolTip(self.root.langer.get(self.intro_))
                                    self.tips.setToolTip(self.root.langer.get(self.tips_))
                                    self.value.setText(self.val(self.scroll.value()))

                                def pushEvent(self, i):
                                    self.push.emit(i)
                                    self.value.setText(self.val(i))

                                def setToolBar(self,wid,shown=None,text=None):
                                    if wid == "intro":
                                        if shown is not None:
                                            self.introable = shown
                                            self.intro.setVisible(shown)
                                        if text is not None: self.intro_ = text
                                    if wid == "tips":
                                        if shown is not None:
                                            self.tipsable = shown
                                            self.tips.setVisible(shown)
                                        if text is not None: self.tips_ = text
                                        self.lighting(self.root.settings["theme"])
                                        self.langing()

                            class DropBtnCombo(QComboBox):
                                """只在点击下拉箭头时弹出下拉框"""
                                def mousePressEvent(self, event):
                                    opt = QStyleOptionComboBox()
                                    self.initStyleOption(opt)
                                    drop_rect = self.style().subControlRect(
                                        QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self
                                    )
                                    if drop_rect.contains(event.pos()):
                                        self.showPopup()
                                    else:
                                        super().mousePressEvent(event)

                            class Combo(QWidget):
                                push = pyqtSignal(str)

                                class _QComboBox(QComboBox):
                                    popupAboutToShow = pyqtSignal()
                                    def showPopup(self):
                                        self.popupAboutToShow.emit()
                                        super().showPopup()

                                def __init__(self,parent=None,root=None,text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.text_ = text
                                    self.intro_ = ""
                                    self.tips_ = ""
                                    self.introable = False
                                    self.tipsable = False
                                    self.init_wid()
                                    self.parent.scroll_layout.addWidget(self)
                                
                                def init_wid(self):
                                    self.setFixedHeight(40)
                                    self.layout = QHBoxLayout(self)
                                    self.layout.setAlignment(Qt.AlignVCenter)
                                    self.layout.setContentsMargins(0, 0, 0, 0)
                                    self.layout.setSpacing(5)

                                    self.layout.addSpacing(28)

                                    self.text = QLabel()
                                    self.text.setProperty("wid","text")
                                    self.text.setStyleSheet("font-size: 17px;")
                                    self.text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                                    self.layout.addWidget(self.text,0)
                                    self.text.setFixedHeight(30)

                                    self.layout.addStretch(1)

                                    self.combo = self._QComboBox()
                                    self.combo.setFixedHeight(25)
                                    self.combo.setFixedWidth(150)
                                    self.layout.addWidget(self.combo,0)

                                    self.intro = QLabel()
                                    self.layout.addWidget(self.intro)
                                    self.intro.hide()
                                    self.intro.setFixedSize(20,20)

                                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    intr = self.intro.sizePolicy()
                                    intr.setRetainSizeWhenHidden(True)
                                    self.intro.setSizePolicy(intr)

                                    self.tips = QLabel()
                                    self.layout.addWidget(self.tips)
                                    self.tips.hide()
                                    self.tips.setFixedSize(20,20)

                                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                                    tip = self.tips.sizePolicy()
                                    tip.setRetainSizeWhenHidden(True)
                                    self.tips.setSizePolicy(intr)

                                    self.langing()

                                def setToolBar(self,wid,shown=None,text=None):
                                    if wid == "intro":
                                        if shown is not None:
                                            self.introable = shown
                                            self.intro.setVisible(shown)
                                        if text is not None: self.intro_ = text
                                    if wid == "tips":
                                        if shown is not None:
                                            self.tipsable = shown
                                            self.tips.setVisible(shown)
                                        if text is not None: self.tips_ = text
                                        self.lighting(self.root.settings["theme"])
                                        self.langing()

                                def langing(self):
                                    self.text.setText(self.root.langer.get(self.text_))
                                    self.intro.setToolTip(self.root.langer.get(self.intro_))
                                    self.tips.setToolTip(self.root.langer.get(self.tips_))


                            def barShow(self):
                                self.scroll_slider.setVisible(self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum())

                            def resizeEvent(self,event):
                                self.scroll_slider.setGeometry(self.scroll.width()-5,0,5,self.scroll.height())
                                self.barShow()
                                super().resizeEvent(event)

                            def showEvent(self,event):
                                super().showEvent(event)
                                self.barShow()

                        class Launcher(Page):
                            def __init__(self, parent=None, root=None, text=None,icon=None):
                                super().__init__(parent,root,text,icon)
                                self.init_wid()

                            def init_wid(self):
                                self._title1 = self.Title(self,self.root,"wid.pages.setting.launcher.preferences")

                                self._t1_theme = self.Bool(self,self.root,"wid.pages.setting.launcher.preferences.theme")
                                self._t1_theme.btn.setChecked(self.root.settings["theme"])
                                self._t1_theme.push.connect(self.root.setTheme)

                                self._t1_lang = self.Combo(self,self.root,"wid.pages.setting.launcher.preferences.lang")
                                def _t1_lang_showEvent(self,combo):
                                    items = self.root.langer.get_langs_info()
                                    combo.clear()
                                    for lang_name, lang_info in items.items():
                                        combo.addItem(f"{lang_info[0]}",lang_name)
                                        combo.setItemData(combo.count()-1,lang_info[1], Qt.ToolTipRole)
                                    combo.setCurrentIndex(combo.findData(self.root.settings["language"]))
                                _t1_lang_showEvent(self,self._t1_lang.combo)
                                self._t1_lang.combo.popupAboutToShow.connect(lambda: _t1_lang_showEvent(self._t1_lang,self._t1_lang.combo))
                                self._t1_lang.combo.activated.connect(lambda: self.root.langer.load(self._t1_lang.combo.currentData()) if self._t1_lang.combo.currentIndex() != -1 else None)

                                self._title2 = self.Title(self,self.root,"wid.pages.setting.launcher.launch")

                                self._title3 = self.Title(self,self.root,"wid.pages.setting.launcher.java")
                                self._t1_theme.setToolBar("intro",shown=True)




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
            if reason == QSystemTrayIcon.Trigger:
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
            loglevel = logging.DEBUG
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
                QTimer.singleShot(0, lambda: (notify_langing(self.root.window), self.root.logger.debug("Langing...")))
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

    class Signals():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root
            self._signals = {}

        def register(self, name):
            """注册一个新的信号"""
            if name not in self._signals:
                self._signals[name] = []

        def connect(self, name, callback):
            """连接一个回调函数到指定信号"""
            if name not in self._signals:
                self.register(name)
            self._signals[name].append(callback)

        def emit(self, name, *args, **kwargs):
            """触发指定信号，调用所有连接的回调函数"""
            if name in self._signals:
                for callback in self._signals[name]:
                    try:
                        callback(*args, **kwargs)
                    except Exception as e:
                        self.root.logger.error(f"Error in signal '{name}' callback: {e}")

        def disconnect(self, name, callback):
            """断开指定信号的回调函数"""
            if name in self._signals and callback in self._signals[name]:
                self._signals[name].remove(callback)

        def cancel(self, name):
            """取消注册指定信号"""
            if name in self._signals:
                del self._signals[name]

        def clear(self, name):
            """清除指定信号的所有回调函数"""
            if name in self._signals:
                self._signals[name] = []

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
            注意：这主要影响任务栏、开始菜单等系统UI。
            如果希望跟随应用窗口主题，应使用 AppsUseLightTheme
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

        try:
            main = Main(app)
            main.window.show()
            sys.exit(app.exec_())
        except Exception as e:
            import traceback, webbrowser
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
            dialog.exec_()

