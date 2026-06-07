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
import sys, os, json, copy, winreg, logging
from datetime import datetime
import ctypes, ctypes.wintypes


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

class Main():
    def __init__(self):
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
            "maxLogNum": 50
        }
        self.settings = copy.deepcopy(self.defsettings)

        def deep_merge_settings(default, file_settings):
            for key, value in file_settings.items():
                if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                    deep_merge_settings(default[key], value)
                elif key in default:
                    default[key] = value

        try:
            if not os.path.exists("BML/settings.json"):
                self.logger.warning("settings file not found, using default settings")
            else:
                with open("BML/settings.json", "r") as f:
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

        with open("src/resources/styles/app.qss", "r", encoding="utf-8") as f:
            self.qss = f.read()
        QApplication.instance().setStyleSheet(self.qss)
        self.logger.debug("load QtStyleSheet: \n" + self.qss)

        self.tray = self.Tray(self, self)
        self.window = self.Window(self,self)
  
    def getQSS(self):
        return self.qss
    
    def saveSettings(self):
        try:
            with open("BML/settings.json", "w") as f:
                json.dump(self.settings, f, separators=(',', ':'), ensure_ascii=False)
            self.logger.info(self.langer.get("log.info.savesettings"))
        except Exception as e:
            self.logger.error(self.langer.get("log.error.savesettings") + "\n--Exception: " + str(e), exc_info=True)

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
            
    class Window(QWidget):
        def __init__(self,parent=None,root=None):
            super().__init__()
            self.parent = parent
            self.root = root
            self.root.logger.debug("init QW.window")
            self.root.window = self
            self.setMinimumSize(QSize(500, 370))

            self.installEventFilter(self)

            self.init_ui()
            self.init_wid()

            self.root.apply_theme()

            self.root.logger.info(self.root.langer.get("log.info.windowLoad"))

        def init_ui(self):
            self.setWindowTitle("Book MDT Launcher")
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setGeometry(50, 50, 700, 500)

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
            self.stren.setFixedWidth(31)
            self.layout.addWidget(self.stren,0)

            self.root.logger.debug("init QW.windowL.main")
            self.main = self.Main(self, self.root)
            self.layout.addWidget(self.main, 1)

            self.left.raise_()
            self.lline.raise_()

        def eventFilter(self, obj, event):
            if obj is self and event.type() == QEvent.Resize:
                new_width = self.left.width() # 假设宽度固定，或者从配置读取
                self.left.setGeometry(0, 0, new_width, self.height())
                self.lline.setGeometry(new_width, 0, 1, self.height())
                
                self.root.logger.debug(f"Window resized via filter: {self.width()}x{self.height()}")
            
            return super().eventFilter(obj, event)

        def nativeEvent(self, eventType, message):
            """
            拦截 Windows 原生消息
            """
            #判断是否是 Windows 消息
            if eventType == "windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                
                #
                if msg.message == 0x0084:
                    # 获取鼠标在屏幕上的坐标
                    pos = self.mapFromGlobal(QCursor.pos())
                    x, y = pos.x(), pos.y()
                    w, h = self.width(), self.height()
                    
                    border_width = 5
                    result = 1 
                    
                    if x < border_width:
                        if y < border_width: result = 13
                        elif y > h - border_width: result = 16
                        else: result = 10
                    elif x > w - border_width:
                        if y < border_width: result = 14
                        elif y > h - border_width: result = 17
                        else: result = 11
                    elif y < border_width:
                        result = 12
                    elif y > h - border_width:
                        result = 15
                    
                    return True, result

                # 托盘主题切换
                elif msg.message in (0x001A, 0x0320):
                    QTimer.singleShot(100, self.root.tray.setIcon_)
            
            # 3. 其他消息交给默认处理
            return super().nativeEvent(eventType, message)
            

        class Left(QWidget):
            def __init__(self,parent=None,root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.isfold = True
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                self.setGeometry(0, 0, 30, self.parent.height())
                self.setAttribute(Qt.WA_StyledBackground, True)

            def init_wid(self):
                self.root.logger.debug("init QW.window.leftL")
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0,0,0,0)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignTop)
                
                self.root.logger.debug("init QW.window.leftL.tline")
                self.tline = self.TLine(self,self.root)
                self.root.logger.debug("init QW.window.leftL.logo")
                self.logo = self.Logo(self,self.root)
                self.layout.addWidget(self.logo,0)
                self.layout.addWidget(self.tline,0)

                self.root.logger.debug("init QW.window.leftL.pages")
                self.pagebtns = self.PageBtns(self,self.root)
                self.layout.addWidget(self.pagebtns,1)

            def fold(self,text=None):
                if text is None:text = not self.isfold
                width = 30 if text else 150
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
                    self.setFixedSize(150,30)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.root.logger.debug("init QW.window.leftL.logoL")
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(5)
                    self.layout.setAlignment(Qt.AlignLeft)

                    self.logo = QLabel(self)
                    
                    self.logo.setFixedSize(30, 30)
                    self.logo.setScaledContents(True)
                    self.layout.addWidget(self.logo, 0)

                    self.label = QLabel(self)
                    self.label.setText('Book MDT Launcher')
                    self.label.setFixedWidth(120)
                    self.label.setProperty('wid', 'title')
                    self.layout.addWidget(self.label, 1)


                def lighting(self,light:bool):
                    logo = "src/assets/icons/" + ("dark.png" if light else "light.png")
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
                        self.move_mousepos = event.globalPos()
                        self.move_moving = True
                        screensize = QScreen.availableGeometry(QApplication.primaryScreen())
                        movpos = self.move_winpos_ + self.move_mousepos - self.move_mousepos_
                        if movpos.x() < 0:
                            movpos.setX(0)
                        elif movpos.x() > screensize.width() - 30:
                            movpos.setX(screensize.width() - 30)
                        if movpos.y() < 0:
                            movpos.setY(0)
                        elif movpos.y() > screensize.height() - 30:
                            movpos.setY(screensize.height() - 30)
                        self.root.window.move(movpos)
                    super().mouseMoveEvent(event)

                def mouseReleaseEvent(self, event):
                    if self.move_pressed and self.move_moving:
                        self.root.logger.debug(t("Window moved via filter: ($1,$2)",self.root.window.pos().x(),self.root.window.pos().y()))
                    else:
                        self.parent.fold()
                    self.move_pressed = False
                    self.move_moving = False
                    super().mouseReleaseEvent(event)

            class TLine(QWidget):
                def __init__(self,parent=None,root=None):
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
                    self.line.setProperty("wid","line")

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
                def __init__(self,parent=None,root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setAttribute(Qt.WA_StyledBackground, False)
                    self.setFixedWidth(150)

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
                    self.chooser.setFixedSize(3, 30)
                    self.chooser.move(-10,0)

                    self.btsGroup.buttonClicked.connect(self.someone_clicked)

                    a = self.add_btn("test","src/assets/buttons/home.png")
                    b = self.add_btn("test","src/assets/buttons/home.png")


                def someone_clicked(self,btn):
                    self.chooser.setGeometry(btn.x(), btn.y(), 3, 30)
                    
                def add_btn(self,Stext,Slogo):
                    btn = self.Btns(Slogo,Stext,self,self.root)
                    self.btns_.append(btn)
                    self.layout.addWidget(btn)
                    self.btsGroup.addButton(btn)
                    return btn

                class Btns(QPushButton):
                    def __init__(self,logo,text,parent=None,root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.logo_ = logo
                        self.text_ = text
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedSize(150, 30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid", "lbtn")
                        self.setCheckable(True)

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(3, 0, 0, 0)
                        self.layout.setSpacing(3)

                        self.logo = QLabel(self)
                        self.logo.setFixedSize(24,30)
                        self.logo.setAttribute(Qt.WA_StyledBackground, False)
                        self.logo.setProperty("wid", "lbtn")
                        self.logo.setScaledContents(False)
                        self.layout.addWidget(self.logo)

                        self.text = QLabel(self)
                        self.text.setAttribute(Qt.WA_StyledBackground, False)
                        self.text.setFixedSize(120,30)
                        self.langing()
                        self.layout.addWidget(self.text)

                    def lighting(self,light:bool):
                        color = QColor(75,75,75) if light else QColor(200,200,200)
                        logo = change_color(self.logo_,color)
                        pixmap = logo.pixmap(40, 40) 
                        
                        if not pixmap.isNull():
                            smooth_pixmap = pixmap.scaled(
                                24,24, 
                                Qt.KeepAspectRatio, 
                                Qt.FastTransformation
                            )
                            self.logo.setPixmap(smooth_pixmap)
                        else:
                            self.root.logger.warning(f"Failed to load pixmap for {self.logo_}")

                    def langing(self):
                        self.text.setText(self.root.langer.get(self.text_))



        class LLine(QWidget):
            def __init__(self,parent=None,root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                self.setProperty("wid", "line")
                self.setFixedWidth(1)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setGeometry(self.parent.left.width()+1, 0, 1, self.parent.height())

            def init_wid(self):
                pass
        
        class Main(QWidget):
            def __init__(self,parent=None,root=None):
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
                self.layout.addWidget(self.top,0)

                self.root.logger.debug("init QW.windowL.mainL.tline")
                self.tline = self.TLine(self, self.root)
                self.layout.addWidget(self.tline)


            class Top(QWidget):
                def __init__(self,parent=None,root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setFixedHeight(30)

                def init_wid(self):
                    pass

            class TLine(QWidget):
                def __init__(self,parent=None,root=None):
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
    
    class Tray(QSystemTrayIcon):
        def __init__(self, parent=None, root=None):
            super().__init__()
            self.parent = parent
            self.root = root
            self.theme = None
            self.init_ui()
            self.init_wid()
            self.root.logger.info(self.root.langer.get("log.info.trayLoad"))

        def init_ui(self):
            self.setToolTip("Book Mdt Launcher")
            self.setIcon_()
            self.show()
        def init_wid(self):
            pass

        def setIcon_(self):
            """根据系统主题设置托盘图标"""
            theme = "light" if self.root.winreg.taskbar_theme() == "dark" else "dark"
            if self.theme != theme:
                self.theme = theme
                icon_path = f"src/assets/icons/{theme}.png"
                
                # 检查文件是否存在，防止路径错误导致无图标
                if not os.path.exists(icon_path):
                    self.root.logger.warning(t(self.root.langer.get("log.warning.trayIconPath"),icon_path))
                
                icon = QIcon(icon_path)
                self.setIcon(icon)
                self.root.logger.info(t(self.root.langer.get("log.info.trayTheme"),"light" if theme == "light" else "dark"))

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
            self.log_dir = "BML/logs"
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
            if self.root.settings["language"] not in self.get_langs():
                if self.root.settings["language"] is not None:
                    self.root.logger.warning(f"Language '{self.root.settings['language']}' not found, using system display language:"+ self.root.winreg.display_language())
                else:
                    self.root.logger.info("using system display language:"+ self.root.winreg.display_language())
                if self.root.winreg.display_language() in self.get_langs():
                    self.root.settings["language"] = self.root.winreg.display_language()
                else:
                    self.root.logger.warning("system display language not found, using: en-US")
                    self.root.settings["language"] = "en-US"
            self.load(self.root.settings["language"])
            self.root.logger.info(self.get("init.load"))

        def load(self,lang):
            with open(f"src/lang/{lang}.json", "r", encoding="utf-8") as f:
                self.langs = json.load(f)

        def get(self, key):
            return self.langs[key]

        def get_langs(self):
            langs = []
            for file in os.listdir("src/lang"):
                if file.endswith(".json"):
                    langs.append(file.replace(".json", ""))
            return langs

    class Winreg():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root

        def display_language(self):
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r"Control Panel\Desktop")
                value, _ = winreg.QueryValueEx(key, "PreferredUILanguages")
                return value[0]
            except Exception as e:
                print("Failed to get display language:", e)
                return None
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
