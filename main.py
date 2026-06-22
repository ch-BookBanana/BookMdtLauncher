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
import sys, os, json, copy, winreg, logging, glob, locale
from datetime import datetime
import ctypes
import ctypes.wintypes
from PyQt5.Qt import *
from src.utils.path_utils import getPath
from src.utils.mdtScanner import mdtScanner
from src.utils.mdtLauncher import mdtLauncher


def change_color(path, color: QColor):
    """白底png改色"""
    pix = QPixmap(path)
    colored = QPixmap(pix.size())
    colored.fill(Qt.transparent)
    painter = QPainter(colored)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), color)
    painter.end()
    return QIcon(colored)


def t(text, *args):
    for i, arg in enumerate(args, start=1):
        text = text.replace(f"${i}", str(arg))
    return text


class _Runnable(QRunnable):
    def __init__(self, task, callback):
        super().__init__()
        self.task = task
        self.callback = callback
        self.signal = _Signal()

    def run(self):
        try:
            result = self.task()
            self.signal.done.emit(result, self.callback)
        except:
            pass

class _Signal(QObject):
    done = pyqtSignal(object, object)

pool = QThreadPool()
_signal_bridge = _Signal()
_signal_bridge.done.connect(lambda result, callback: callback(result))

def runAsync(task, callback):
    runnable = _Runnable(task, callback)
    runnable.signal.done.connect(
        lambda res, cb, s=runnable: (cb(res), pool.releaseThread())
    )
    pool.start(runnable)


class Leftw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(None)
        self.parent = parent
        self.root = root
        self.resize_(0)
        self.parent.parent.left.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.left.setFixedWidth(self.width())
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)

            
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
        self.resize_(0)
        self.parent.parent.right.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.right.setFixedWidth(self.width())
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)

class Main():
    def __init__(self):
        for i in [
            "BML",
            "BML/logs",
            "BML/.Mindustrys"
        ]:
            os.makedirs(getPath(i), exist_ok=True)
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
            "githubToken": None
        }
        self.settings = copy.deepcopy(self.defsettings)

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

        with open(getPath("src/resources/styles/app.qss"), "r", encoding="utf-8") as f:
            self.qss = f.read()
        QApplication.instance().setStyleSheet(self.qss)
        self.logger.debug("load QtStyleSheet: \n" + self.qss)

        self.tray = self.Tray(self, self)
        self.window = self.Window(self, self)

    def getQSS(self):
        return self.qss

    def saveSettings(self):
        try:
            settings_path = getPath("BML/settings.json")
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, separators=(',', ':'), ensure_ascii=False)
            self.logger.info(self.langer.get("log.info.savesettings"))
        except Exception as e:
            try:
                self.logger.error(self.langer.get("log.error.savesettings") + "\n--Exception: " + str(e), exc_info=True)
            except:
                self.logger.error("Failed to save settings\n--Exception: " + str(e), exc_info=True)

    def apply_theme(self):
        is_light = bool(self.settings["theme"])
        theme_str = "light" if is_light else "dark"

        # 设置主窗口主题属性并刷新样式
        self.window.setProperty("theme", theme_str)
        self.window.style().unpolish(self.window)
        self.window.style().polish(self.window)

        # 刷新整个应用样式
        app = QApplication.instance()
        if app:
            app.style().unpolish(app)
            app.style().polish(app)

        font = QFont()
        font.setFamily("Microsoft Yahei")
        font.setPointSize(8)
        app.setFont(font)

        # 递归查找并调用所有子控件的 lighting 函数
        def notify_lighting(widget, state):
            if hasattr(widget, 'lighting') and callable(widget.lighting):
                try:
                    widget.lighting(state)
                except Exception as e:
                    self.logger.error(f"Error calling lighting on {widget}: {e}")
            try:
                widget.setProperty('theme', theme_str)
            except:
                pass
            for child in widget.children():
                notify_lighting(child, state)

        notify_lighting(self.window, is_light)
        self.logger.info(t(self.langer.get("log.info.changetheme"), theme_str))
        self_ = self
        if hasattr(self, 'tray') and hasattr(self.tray, 'menu'):
            self.tray.menu.setProperty('theme', theme_str)
            self.tray.menu.style().unpolish(self.tray.menu)
            self.tray.menu.style().polish(self.tray.menu)

    class Window(QWidget):
        def __init__(self, parent=None, root=None):
            super().__init__()
            self.parent = parent
            self.root = root
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
                self.lline.setGeometry(new_width - 1, 0, 1, self.height())

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
                self.init_wid()

            def init_ui(self):
                self.setProperty("wid", "line")
                self.setFixedWidth(1)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setGeometry(self.parent.left.width(), 0, 1, self.parent.height())

            def init_wid(self):
                pass

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
                    self.setFixedHeight(34)

                def init_wid(self):
                    self.root.logger.debug("init QW.windowL.mainL.topL")
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignRight)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_mini")
                    self.tbt_mini = self.TriBtn([getPath("src/assets/tribtns/minimize.png")], self, self.root)
                    self.tbt_mini.clicked.connect(lambda: self.root.window.showMinimized())
                    self.layout.addWidget(self.tbt_mini)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_max")
                    self.tbt_max = self.TriBtn(
                        [
                            getPath("src/assets/tribtns/maximize.png"),
                            getPath("src/assets/tribtns/maximize2.png")
                        ],
                        self, self.root)
                    self.tbt_max.clicked.connect(self.maxmize)
                    self.layout.addWidget(self.tbt_max)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_close")
                    self.tbt_close = self.TriBtn([getPath("src/assets/tribtns/close.png")], self, self.root)
                    self.tbt_close.clicked.connect(lambda: self.close_())
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

                class TriBtn(QPushButton):
                    def __init__(self, logo: list, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.logo_ = logo
                        self.setLogo_ = 0
                        self.init_ui()

                    def init_ui(self):
                        self.setFixedSize(30, 30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid", "tbtn")

                    def setLogo(self, l):
                        self.setLogo_ = l
                        self.lighting(self.root.settings["theme"])

                    def lighting(self, light: bool):
                        color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                        logo = change_color(self.logo_[self.setLogo_], color)
                        pixmap = QIcon(logo.pixmap(40, 40))

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

                    self.start = self.Start(self,self.root,self.root.langer.get("wid.pages.start"),getPath("src/assets/buttons/start.png"))
                    self.download = self.Download(self,self.root,self.root.langer.get("wid.pages.download"),getPath("src/assets/buttons/download.png"))
                    self.game = self.Game(self,self.root,self.root.langer.get("wid.pages.game"),getPath("src/assets/buttons/game.png"))
                    self.setting = self.Setting(self,self.root,self.root.langer.get("wid.pages.setting"),getPath("src/assets/buttons/setting.png"))

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
                    
                    def click(self):
                        self.btn.click()

                    def init_wid(self):
                        cls_left = self.Left if hasattr(self, 'Left') else Leftw
                        self.left = cls_left(self, self.root)

                        cls_main = self.Main if hasattr(self, 'Main') else Mainw
                        self.main = cls_main(self, self.root)

                        cls_right = self.Right if hasattr(self, 'Right') else Rightw
                        self.right = cls_right(self, self.root)

                        self.parent.pages.append(self)



                class Start(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        self.launcher = mdtLauncher()
                        super().__init__(parent, root, text, logo)
                        self.launcher.game_launched.connect(self.on_launch)
                        self.launcher.game_started.connect(self.on_start)
                        self.launcher.game_finished.connect(self.on_finish)
                    def on_launch(self):
                        self.main.game.down.setCurrentIndex(2)
                        self.main.right.right.changeTo(2)

                    def on_start(self):
                        self.main.game.down.setCurrentIndex(3)
                        self.main.right.right.changeTo(3)

                    def on_finish(self, exitCode):
                        self.main.game.down.setCurrentIndex(0)
                        self.main.right.right.changeTo(0)
                        self.root.logger.info(f"Game finished with code {exitCode}")
                    
                        

                    class Main(Mainw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent=parent, root=root)
                            self.init_ui()
                            self.init_wid()

                        def init_ui(self):
                            self.setAttribute(Qt.WA_StyledBackground, True)

                        def init_wid(self):
                            self.layout = QHBoxLayout(self)
                            self.layout.setSpacing(0)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setAlignment(Qt.AlignLeft)

                            self.game = self.Game(self,self.root)
                            self.layout.addWidget(self.game,0)

                            self.right = self.Right(self,self.root)
                            self.layout.addWidget(self.right,1)

                        class Game(QWidget):
                            def __init__(self, parent=None, root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.game_ = None
                                self._notFound = False
                                self._current_display = None
                                self._cached_pixmap = None
                                self._cached_img_bytes = None
                                self._pending_update = False
                                self.init_ui()
                                self.init_wid()

                            def init_ui(self):
                                self.setFixedWidth(200)
                                self.setAttribute(Qt.WA_StyledBackground, True)

                            def init_wid(self):
                                self.layout = QVBoxLayout(self)
                                self.layout.setSpacing(0)
                                self.layout.setContentsMargins(0, 0, 0, 0)
                                self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

                                self.layout.addSpacing(50)

                                self.picture = QLabel()
                                self.picture.setProperty("wid","png")
                                self.picture.setAttribute(Qt.WA_StyledBackground, True)
                                self.picture.setFixedSize(100,100)
                                self.picture.setScaledContents(True)
                                self.layout.addWidget(self.picture,0,Qt.AlignHCenter)

                                self.layout.addSpacing(10)

                                self.name = QLabel()
                                self.name.setProperty("wid","title")
                                self.name.setStyleSheet("font-size: 16px;")
                                self.layout.addWidget(self.name,0,Qt.AlignHCenter)

                                self.layout.addSpacing(5)

                                self.vers = QLabel()
                                self.vers.setProperty("wid","title")
                                self.vers.setStyleSheet("font-size: 12px;")
                                self.layout.addWidget(self.vers,0,Qt.AlignHCenter)

                                self.layout.addSpacing(30)

                                self.down = self.Down(self,self.root)
                                self.layout.addWidget(self.down,1)

                                self.timer = QTimer(self)
                                self.timer.timeout.connect(self.timerEvent)
                                self.timer.start(5000)

                            def langing(self):
                                if self._notFound:
                                    self._show_not_found()

                            def _show_not_found(self):
                                self.picture.setPixmap(QPixmap())
                                self._notFound = True
                                self._cached_pixmap = None
                                self._cached_img_bytes = None
                                self.name.setText(self.root.langer.get("wid.pages.start.gameNotfound"))
                                self.vers.setText(self.root.langer.get("wid.pages.start.gameNotfound2"))

                            def timerEvent(self):
                                default = self.root.settings["defaultGame"]
                                runAsync(
                                    lambda: self._prepare_display_data(default),
                                    lambda data: self._apply_display_data(data)
                                )

                            def _prepare_display_data(self, default):
                                mdts = mdtScanner.getMdts()
                                if not mdts:
                                    return {"type": "notfound"}

                                target = default if default in mdts else mdts[0]

                                icon_path = None
                                base = getPath(f"BML/.Mindustrys/{target}/icon")
                                for ext in (".png", ".jpg", ".jpeg"):
                                    path = base + ext
                                    if os.path.exists(path):
                                        icon_path = path
                                        break
                                if not icon_path:
                                    icon_path = getPath("src/assets/icons/mdt/mdt.png")

                                with open(icon_path, "rb") as f:
                                    img_bytes = f.read()

                                mdtmsg = mdtScanner.getMdtMsg(target)
                                version_str = f"V{mdtmsg['number']}|{mdtmsg['build']}-{mdtmsg['modifier']}"

                                return {
                                    "type": "game",
                                    "name": target,
                                    "img_bytes": img_bytes,
                                    "version": version_str
                                }

                            def _apply_display_data(self, data):
                                if data["type"] == "notfound":
                                    if not self._notFound:
                                        self._show_not_found()
                                        self.root.settings["defaultGame"] = None
                                        self.game_ = None
                                        self.root.saveSettings()
                                        self._current_display = None
                                    return

                                if (self._current_display == data["name"] 
                                        and not self._notFound
                                        and self._cached_img_bytes == data["img_bytes"]):
                                    return

                                self._pending_data = data
                                if not self._pending_update:
                                    self._pending_update = True
                                    QTimer.singleShot(0, self._delayed_update)

                            def _delayed_update(self):
                                self._pending_update = False
                                data = self._pending_data

                                self._notFound = False
                                self._current_display = data["name"]

                                if self._cached_img_bytes != data["img_bytes"]:
                                    pix = QPixmap()
                                    pix.loadFromData(data["img_bytes"])
                                    self._cached_pixmap = pix
                                    self._cached_img_bytes = data["img_bytes"]

                                self.picture.setPixmap(self._cached_pixmap)
                                self.name.setText(data["name"])
                                self.vers.setText(data["version"])

                                if self.root.settings["defaultGame"] != data["name"]:
                                    self.root.settings["defaultGame"] = data["name"]
                                    self.game_ = data["name"]
                                    self.root.saveSettings()

                            class Down(QStackedWidget):
                                def __init__(self,parent=None,root=None):
                                    super().__init__(parent)
                                    self.parent = parent
                                    self.root = root

                                    self.m = self.M(self,self.root)#0-选择游戏
                                    self.addWidget(self.m)

                                    self.mod = self.Mod(self,self.root)#1-模组返回
                                    self.addWidget(self.mod)

                                    self.start = self.Start(self,self.root)#2-游戏数据
                                    self.addWidget(self.start)

                                    self.start2 = self.Start2(self,self.root)#3-取消游戏
                                    self.addWidget(self.start2)

                                    self.setCurrentIndex(0)

                                class M(QWidget):
                                    def __init__(self,parent=None,root=None):
                                        super().__init__()
                                        self.parent = parent
                                        self.root = root
                                        self.init_wid()

                                    def init_wid(self):
                                        self.layout = QVBoxLayout(self)
                                        self.layout.setSpacing(10)
                                        self.layout.setContentsMargins(20,20,20,20)
                                        self.layout.setAlignment(Qt.AlignBottom)

                                        self.game = self.btn(self,self.root,"wid.pages.start.gamebtn")
                                        self.game.setFixedHeight(50)
                                        self.layout.addWidget(self.game)
                                        

                                    class btn(QPushButton):
                                        def __init__(self, parent=None, root=None, text=None):
                                            super().__init__(parent)
                                            self.parent = parent
                                            self.root = root
                                            self.text = text
                                            self.init_ui()
                                            self.langing()

                                        def init_ui(self):
                                            self.setStyleSheet("""
                                                QPushButton{
                                                    background-color: transparent;
                                                    color: rgb(200, 200, 200);
                                                    border: 2px solid rgb(200, 200, 200);
                                                    border-radius: 10px;
                                                }
                                                QPushButton[theme="dark"]{
                                                    background-color: transparent;
                                                    color: rgb(20, 20, 20);
                                                    border: 2px solid rgb(20, 20, 20);
                                                    border-radius: 10px;
                                                }
                                            """)

                                        def langing(self):
                                            self.setText(self.root.langer.get(self.text))

                                            

                                class Mod(QWidget):
                                    def __init__(self,parent=None,root=None):
                                        super().__init__(parent)
                                        self.parent = parent
                                        self.root = root


                                class Start(QWidget):
                                    def __init__(self,parent=None,root=None):
                                        super().__init__(parent)
                                        self.parent = parent
                                        self.root = root

                                class Start2(QWidget):
                                    def __init__(self,parent=None,root=None):
                                        super().__init__(parent)
                                        self.parent = parent
                                        self.root = root

                        class Right(QLabel):
                            def __init__(self,parent=None,root=None):
                                super().__init__()
                                self.parent = parent 
                                self.root = root
                                self.init_wid()


                            def init_wid(self):
                                self.layout = QHBoxLayout(self)
                                self.layout.setSpacing(0)
                                self.layout.setContentsMargins(50,50,50,50)

                                self.layout.addWidget(QWidget(),1)
                                
                                self.lay2 = QWidget()
                                self.lay2.setFixedWidth(185)
                                self.lay2_ = QVBoxLayout(self.lay2)
                                self.layout.addWidget(self.lay2,0)

                                self.lay2_.setSpacing(5)
                                self.lay2_.setContentsMargins(0,0,0,0)

                                self.lay2_.addStretch(1)

                                self.startbtn = self.btn(self,self.root,"#f7c334","wid.pages.start.startbtn")
                                self.startbtn.setFixedSize(185,40)
                                self.startbtn.clicked.connect(lambda: self.parent.parent.launcher.run(self.root.settings["defaultGame"]))
                                self.lay2_.addWidget(self.startbtn,0)

                                self.lay3 = QWidget()
                                self.lay3.setFixedHeight(40)
                                self.lay3_ = QHBoxLayout(self.lay3)
                                self.lay3_.setContentsMargins(0,0,0,0)
                                self.lay3_.setSpacing(5)
                                self.lay2_.addWidget(self.lay3)

                                self.modbtn = self.btn(self,self.root,"#5587c9", "wid.pages.start.modbtn")
                                self.modbtn.setFixedSize(140,40)
                                self.lay3_.addWidget(self.modbtn,0)

                                self.setbtn = self.btn(self,self.root,"#5587c9", "")
                                self.setbtn.setFixedSize(40,40)
                                self.setbtn.setIcon(QIcon(getPath("src/assets/buttons/setting.png")))
                                self.setbtn.setIconSize(QSize(40,40))
                                self.lay3_.addWidget(self.setbtn,0)

                                self.layout2 = QHBoxLayout(self)
                                self.right = self.Right(self,self.root)
                                self.layout2.addWidget(self.right,1) 

                            class Right(QStackedWidget):
                                def __init__(self, parent,root):
                                    super().__init__()
                                    self.setParent(parent)
                                    self.parent = parent
                                    self.root = root
                                    
                                    self.init_ui()
                                    self.init_wid()
                                    self.hide()

                                def init_ui(self):
                                    self.setAttribute(Qt.WA_TranslucentBackground,True)
                                    self.setProperty("wid","widget")

                                def init_wid(self):
                                    self.mod = self.Mod(self,self.root)
                                    self.addWidget(self.mod)

                                    self.world = self.World(self,self.root)
                                    self.addWidget(self.world)

                                    self.start = self.Start(self,self.root)
                                    self.addWidget(self.start)

                                def changeTo(self, index):
                                    if index > 3:
                                        index = 3
                                    if index == 0:
                                        self.hide()
                                    elif 1<=index<=3:
                                        self.show()
                                        self.setCurrentIndex(index + 1)

                                class Mod(QWidget):
                                    def __init__(self, parent,root):
                                        super().__init__()
                                        self.parent = parent
                                        self.root = root

                                        self.init_ui()

                                    def init_ui(self):
                                        self.setAttribute(Qt.WA_StyledBackground,True)

                                class World(QWidget):
                                    def __init__(self, parent,root):
                                        super().__init__()
                                        self.parent = parent
                                        self.root = root
                                        
                                        self.init_ui()

                                    def init_ui(self):
                                        self.setAttribute(Qt.WA_StyledBackground,True)

                                class Start(QWidget):
                                    def __init__(self, parent,root):
                                        super().__init__()
                                        self.parent = parent
                                        self.root = root
                                        
                                        self.init_ui()

                                    def init_ui(self):
                                        self.setAttribute(Qt.WA_StyledBackground,True)

                                    def init_wid(self):
                                        self.layout = QHBoxLayout(self)
                                        self.layout.setContentMargins(0,0,0,0)
                                        self.layout.setSpacing(0)

                                        self.txt = self.TXT(self,self.root)
                                        self.layout.addWidget(self.txt,1)

                                    class TXT(QPlainTextEdit):
                                        def __init__(self,parent=None,root=None):
                                            super().__init__()
                                            self.parent = parent
                                            self.root= root
                                            self.setReadOnly(True)
                                            self.setProperty("wid", "log")
                                            self.logs = []
                                            self.setMaximnmBlockCount(1000)
                                            self.parent.parent.parent.parent.launcher.game_log.connect(self.appendLog)

                                        def appendLog(self,log):
                                            if log["type"] == "info":
                                                col = QColor("white") if self.root.settings["theme"] == "dark" else QColor("black")
                                            else :
                                                col = QColor("red")
                                            self.logs.append([log["type"],log["text"]])
                                            self.setTextColor(col)
                                            self.appendPlainText(log["text"])
                                            if len(self.logs) > 1000:
                                                self.logs.pop(0)
                                            



                            class btn(QPushButton):
                                def __init__(self, parent=None, root=None, color=None, text=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.init_ui()
                                    if color is not None:
                                        self.setColor(color)
                                    if text is not None:
                                        self.text = text
                                        self.langing()

                                def init_ui(self):
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.setStyleSheet("""
                                        QPushButton{
                                            background-color: #00000000;
                                            color: white;
                                            border-radius: 10px;
                                            font-size: 12px;
                                        }
                                    """)

                                def setColor(self,color_):
                                    self.setStyleSheet(f"""
                                        QPushButton{{
                                            background-color: {color_};
                                            color: white;
                                            border-radius: 10px;
                                            font-size: 18px
                                        }}
                                        QPushButton:hover{{
                                            border: 2px solid #88888844;
                                        }}
                                        QPushButton:pressed{{
                                            border: 3px solid #88888888;
                                        }}
                                    """)

                                def langing(self):
                                    self.setText(self.root.langer.get(self.text))

                                    

                    class Right(Rightw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent=parent, root=root)
                            self.resize_(0)

                class Download(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                class Game(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                class Setting(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)





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
            self.root.logger.info(self.get("init.load"))

        def load(self, lang):
            """加载语言文件并自动刷新所有支持多语言的控件"""
            lang_path = getPath(f"src/lang/{lang}.json")
            default_lang_path = getPath(f"src/lang/{self.default_lang}.json")

            try:
                with open(lang_path, "r", encoding="utf-8") as f:
                    self.langs = json.load(f)
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
                QTimer.singleShot(0, lambda: (notify_langing(self.root.window),self.root.logger.debug)("Langing..."))

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
                for file in os.listdir(lang_dir_abs):
                    if file.endswith(".json"):
                        langs.append(file.replace(".json", ""))
            except Exception as e:
                self.root.logger.error(f"Failed to list language files: {e}")
            return langs

    class Winreg():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root

        def display_language(self):
            try:
                dll = ctypes.windll.kerne32
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
    main = Main()
    main.window.show()
    sys.exit(app.exec_())