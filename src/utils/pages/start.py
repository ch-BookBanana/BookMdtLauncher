import os, copy

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedLayout, QStackedWidget, QVBoxLayout

from src.utils.path_utils import getPath

from ..mdtScanner import mdtScanner
from ..QThTimer import QThTimer
from ..utils import change_color, t

from ._init import *


class Start(Page):
    def __init__(self, parent=None, root=None, text=None, logo=None):
        root.signals.register("start_gameChanged", Signal(object))
        super().__init__(parent, root, text, logo)
        QThTimer.taskP(1000, self.left.changeTimer, [self.left.sets])
        QThTimer.task(0, self.left.changeTimer, [self.left.sets])
        self.root.launcher.game_launched.connect(lambda: self.main.stack.setCurrentIndex(3))
        self.root.launcher.game_launched.connect(lambda: self.left.main.setCurrentIndex(3))
        self.root.launcher.game_started.connect(lambda: self.main.stack.setCurrentIndex(4))
        self.root.launcher.game_started.connect(lambda: self.left.main.setCurrentIndex(4))
        self.root.launcher.lifecycle_finished.connect(lambda: self.main.stack.setCurrentIndex(0))
        self.root.launcher.lifecycle_finished.connect(lambda: self.left.main.setCurrentIndex(0))
        self.root.launcher.appdata_save_step.connect(self._on_appdata_save_step)
        self.root.launcher.appdata_save_done.connect(self._on_appdata_save_done)
        self.root.launcher.appdata_import_started.connect(self._on_appdata_import_started)
        self.root.launcher.appdata_import_done.connect(self._on_appdata_import_done)
        self.root.launcher.log.connect(lambda dic: (self.root.logger.info("[launcher]"+dic["text"]) if dic["type"] == "info" else self.root.logger.error("[launcher]"+dic["text"])))

    def changeGame(self, game=None):
        mdts = mdtScanner.getMdts()
        if game == self.root.settings["defaultGame"]: return
        if game not in mdts:
            if len(mdts) == 0:
                self.root.settings["defaultGame"] = None
            else:
                self.root.settings["defaultGame"] = mdts[0]
        else:
            self.root.settings["defaultGame"] = game
        self.root.signals.emit("start_gameChanged", game)
        QThTimer.task(0, self.left.changeTimer, [self.left.sets])

    def _on_appdata_save_step(self, step):
        """appdataCopy 保存步骤：切换两个界面到 index 5 并设置 finished 文本。"""
        try:
            self.left.main.setCurrentIndex(5)
            self.main.stack.setCurrentIndex(5)
            self.left.main.finished.setStatus(step)
            self.main.finished.setStatus(step)
        except Exception:
            pass

    def _on_appdata_save_done(self):
        """appdataCopy 保存完成：两个界面切回 index 0。"""
        try:
            self.main.stack.setCurrentIndex(0)
            self.left.main.setCurrentIndex(0)
        except Exception:
            pass

    def _on_appdata_import_started(self):
        """appdataCopy 开始导入数据：两个界面切到 finished 页显示"正在导入数据"。"""
        try:
            text = self.root.langer.get("wid.pages.start.finished.importing")
            self.left.main.finished.label.setText(text)
            self.main.finished.label.setText(text)
            self.left.main.setCurrentIndex(5)
            self.main.stack.setCurrentIndex(5)
        except Exception:
            pass

    def _on_appdata_import_done(self):
        """appdataCopy 导入完成：切回 launch 页等待游戏启动。"""
        try:
            self.main.stack.setCurrentIndex(3)
            self.left.main.setCurrentIndex(3)
        except Exception:
            pass

            

    class Left(Leftw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
            self.resize_(250)
            self.init_wid()
            self.game = {
                "icon": None,
                "name": None,
                "vers": None,
                "icon_key": None
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
            self.main = self.Bottom(self,self.root)
            self.layout.addWidget(self.main,1)

        def sets(self,icon=(False,None),gameTxt=(False,None),versTxt=(False,None)):
            if icon[0]:
                pm = icon[1]
                if pm and not pm.isNull():
                    pm = pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.FastTransformation)
                self.icon.setPixmap(pm)
            if gameTxt[0]:
                self.gameTxt.setText(QFontMetrics(self.gameTxt.font()).elidedText(gameTxt[1], Qt.ElideRight, 150))
            if versTxt[0]:
                self.versTxt.setText(QFontMetrics(self.versTxt.font()).elidedText(versTxt[1], Qt.ElideRight, 130))

        def changeTimer(self,event):
            i = [(False,None),(False,None),(False,None)]
            mdts = mdtScanner.getMdts()
            if len(mdts) == 0:
                if self.root.settings["defaultGame"] is not None:
                    self.root.settings["defaultGame"] = None
            elif self.root.settings["defaultGame"] is None or self.root.settings["defaultGame"] not in mdts:
                self.root.settings["defaultGame"] = mdts[0]
            default_game = self.root.settings["defaultGame"]
            game_msg = mdtScanner.getMdtMsg(default_game) if default_game else None
            if self.game["name"] != default_game:
                if default_game is None:
                    i[1] = (True,self.root.langer.get("wid.pages.start.left.noGame"))
                    i[2] = (True,self.root.langer.get("wid.pages.start.left.DGame"))
                    self.game["name"] = self.game["vers"] = self.game["icon_key"] = None
                else:
                    self.game["name"] = default_game
                    if game_msg:
                        self.game["vers"] = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}"
                    i[1] = (True,default_game)
                    i[2] = (True,self.game["vers"])
            elif self.game["name"] is not None and game_msg:
                new_vers = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}"
                if self.game["vers"] != new_vers:
                    self.game["vers"] = new_vers
                    i[2] = (True,new_vers)
            if self.game["name"] is not None and game_msg and game_msg["icon"]:
                icon_path = game_msg["icon"]
                try:
                    icon_key = f"{icon_path}:{os.path.getmtime(icon_path)}:{os.path.getsize(icon_path)}"
                except OSError:
                    icon_key = None
            else:
                icon_key = None

            if self.game.get("icon_key") != icon_key:
                self.game["icon_key"] = icon_key
                if icon_key is not None:
                    i[0] = (True, QPixmap(game_msg["icon"]))
                else:
                    i[0] = (True, QPixmap())

            if i[0][0] or i[1][0] or i[2][0]:
                event.lambdas[0].emit(i[0],i[1],i[2])
            
        class Bottom(QStackedWidget):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.root = root
                self.parent = parent
                self.init_wid()
                
            def init_wid(self):
                self.start = self.Start(self,self.root)
                self.mod = self.Mod(self,self.root)
                self.world = self.World(self,self.root)
                self.launch = self.Launch(self,self.root)
                self.suspend = self.Suspend(self,self.root)
                self.finished = self.Finished(self,self.root)

            class Pages(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.root = root
                    self.parent = parent
                    self.index = self.parent.addWidget(self)

                class Btn(QPushButton):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.root = root
                        self.parent = parent
                        self.setProperty("wid","btn")

            class Start(Pages):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                    self.world =self.Btn(self,self.root)
                    self.world.setFixedSize(QSize(170,50))
                    self.layout.addWidget(self.world)

                    self.world.clicked.connect(lambda: self.parent.setCurrentIndex(2))
                    self.world.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(2))

                def langing(self):
                    self.world.setText(self.root.langer.get("wid.pages.start.gamebtn"))

            class Mod(Pages):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                    self.cancle =self.Btn(self,self.root)
                    self.cancle.setFixedSize(QSize(170,50))
                    self.layout.addWidget(self.cancle)

                    self.cancle.clicked.connect(lambda: self.parent.setCurrentIndex(0))
                    self.cancle.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(0))

                def langing(self):
                    self.cancle.setText(self.root.langer.get("text.return"))

            class World(Pages):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                    self.cancle =self.Btn(self,self.root)
                    self.cancle.setFixedSize(QSize(170,50))
                    self.layout.addWidget(self.cancle)

                    self.cancle.clicked.connect(lambda: self.parent.setCurrentIndex(0))
                    self.cancle.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(0))

                def langing(self):
                    self.cancle.setText(self.root.langer.get("text.return"))

            class Launch(Pages):
                """左 stacked 的启动/Java 下载状态页：只允许有一个 label 显示状态。"""
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignCenter)
                    self.label = QLabel(self)
                    self.label.setProperty("wid", "title")
                    self.label.setWordWrap(True)
                    self.label.setAlignment(Qt.AlignCenter)
                    self.label.setStyleSheet("font-size:14px;")
                    self.layout.addWidget(self.label)

                def langing(self):
                    self.label.setText(self.root.langer.get("wid.pages.start.java.idle"))

                def setStatus(self, status, pct=None):
                    """唯一状态 label：resume/downloading/extracting/done/error/idle。

                    pct 不为 None 时追加百分比（如 正在下载Java... 45%）。
                    """
                    key = "wid.pages.start.java." + status
                    text = self.root.langer.get(key)
                    if pct is not None:
                        text = t(text, pct)
                    else:
                        # 无百分比时移除 $1 占位符（避免显示字面量）
                        text = text.replace("$1%", "").replace("$1", "")
                    self.label.setText(text)

            class Suspend(Pages):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)

            class Finished(Pages):
                """保存游戏数据进度页（index 5）。"""
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignCenter)
                    self.label = QLabel(self)
                    self.label.setProperty("wid", "title")
                    self.label.setWordWrap(True)
                    self.label.setAlignment(Qt.AlignCenter)
                    self.label.setStyleSheet("font-size:14px;")
                    self.layout.addWidget(self.label)

                def setStatus(self, step):
                    self.label.setText(self.root.langer.get("wid.pages.start.finished.save%d" % step))

    class Main(Mainw):
        def __init__(self,parent=None,root=None):
            super().__init__(parent,root)
            self.init_wid()

        def init_wid(self):
            self.layout = QStackedLayout(self)
            self.layout.setStackingMode(QStackedLayout.StackAll)

            self.backg = self.Backg(self,self.root)
            self.layout.addWidget(self.backg)

            self.stack = QStackedWidget()
            self.layout.addWidget(self.stack)

            self.layout.setCurrentIndex(1)

            self.start = self.Start(self,self.root)
            self.mod = self.Mod(self,self.root)
            self.world = self.World(self,self.root)
            self.launch = self.Launch(self,self.root)
            self.log = self.Log(self,self.root)
            self.finished = self.Finished(self,self.root)




        class _Main(QWidget):
            def __init__(self,parent=None,root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.setProperty("wid","color2")
                self.index = self.parent.stack.addWidget(self)

            def showEvent(self,event):
                super().showEvent(event)
                self.parent.backg.setVisible(not self.testAttribute(Qt.WA_StyledBackground))
                self.parent.stack.setStyleSheet(""if self.testAttribute(Qt.WA_StyledBackground) else "background:transparent;")


        class Start(_Main):
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.init_wid()
                self.langing()
                self.setAttribute(Qt.WA_StyledBackground,False)

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

                self.settings = self.Btn(self,self.root,"110,65,151")
                self.settings.setFixedSize(50,50)
                self.settings.setIconSize(QSize(25,25))
                self.settings.setIcon(QIcon(QPixmap(getPath("src/assets/buttons/setting.png")).scaled(50,50,Qt.KeepAspectRatio,Qt.FastTransformation)))
                self.layout.addWidget(self.settings,2,2,1,1)

                self.mod = self.Btn(self,self.root,"52, 152, 219")
                self.mod.setFixedHeight(50)
                self.layout.addWidget(self.mod,2,1,1,1)

                self.start.clicked.connect(self.on_start_clicked)

            def on_start_clicked(self):
                """开始游戏：无可用 Java 时自动触发下载流程（launcher 会发 java_missing）。"""
                root = self.root
                if root.java_flow is not None:
                    return  # 已有 Java 下载流程在运行
                # 手动指定了 Java 则直接用，否则 launcher 内部自动选择并校验
                root.launcher.run(root.settings["defaultGame"])

            def langing(self):
                self.start.setText(self.root.langer.get("wid.pages.start.startbtn"))
                self.mod.setText(self.root.langer.get("wid.pages.start.modbtn"))
                

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
                            font-size:16px;

                        }}
                        QPushButton:hover{{
                            background-color:rgba({self.color},1);
                        }}
                    """)

        class Mod(_Main):
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)

        class World(_Main):
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)
                self.games = {}
                self.init_wid()
                self.renovate()
                self.games["<:|default|:>"].gameW.show()
                self.root.signals.connect("gameRenovated", self.renovate)

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(0)

                self.scroll = QScrollArea(self)
                self.scroll.setWidgetResizable(True)
                self.scroll.setFrameShape(QFrame.NoFrame)
                self.layout.addWidget(self.scroll)

                self.main = QWidget()
                self.main.setProperty("wid","color2")
                self.scroll_layout = QVBoxLayout(self.main)
                self.scroll_layout.setContentsMargins(10,10,10,10)
                self.scroll_layout.setSpacing(10)
                self.scroll_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
                self.scroll.setWidget(self.main)

            def renovate(self):
                games = copy.deepcopy(self.root.settings["gameList"])
                keys_to_delete = []
                for key, value in list(self.games.items()):
                    if key not in games:
                        value.deleteLater()
                        keys_to_delete.append(key)
                    else:
                        if set(value.games) != set(games[key]):
                            value.renovate(key)
                        del games[key]
                for key in keys_to_delete:
                    del self.games[key]
                for key, value in games.items():
                    self.games[key] = self.Lists(self, self.root)
                    self.games[key].renovate(key)
                

            class Lists(QWidget):
                def __init__(self,parent=None,root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.light = None
                    self.game = ""
                    self.btnPix = [QPixmap(),QPixmap()]
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.games = {}
                    self.launch = False
                    self.setStyleSheet("border-radius:10px;max-width:600px;")
                    self.init_wid()
                    
                    self.parent.scroll_layout.addWidget(self)

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(10,10,10,10)
                    self.layout.setSpacing(5)

                    self.top = QWidget()
                    self.top.setFixedHeight(40)
                    self.layout.addWidget(self.top)

                    self.topL = QHBoxLayout(self.top)
                    self.topL.setContentsMargins(15,0,0,0)
                    self.topL.setSpacing(5)
                    self.topL.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

                    self.label = QLabel()
                    self.label.setProperty("wid","text")
                    self.label.setStyleSheet("font-size:16px;")
                    self.topL.addWidget(self.label,0)

                    self.label2 = QLabel()
                    self.label2.setProperty("wid","lbtn")
                    self.label2.setStyleSheet("font-size:14px;")
                    self.topL.addWidget(self.label2,0)

                    self.topL.addStretch(1)

                    self.button = QPushButton()
                    self.button.setFixedSize(40,40)
                    self.button.setProperty("wid","lbtn")
                    self.button.setStyleSheet("border-radius:20px;")
                    self.topL.addWidget(self.button)

                    class VisiWidget(QWidget):
                        visibled = Signal(bool)

                        def showEvent(self,event):
                            self.visibled.emit(True)
                            super().showEvent(event)

                        def hideEvent(self,event):
                            self.visibled.emit(False)
                            super().hideEvent(event)

                    self.gameW = VisiWidget()
                    self.gameW.visibled.connect(lambda i:self.button.setIcon(QIcon(self.btnPix[int(i)])))
                    self.layout.addWidget(self.gameW)
                    self.gameW.hide()

                    self.gameL = QVBoxLayout(self.gameW)
                    self.gameL.setContentsMargins(0,0,0,0)
                    self.gameL.setSpacing(5)
                    self.line = QWidget()
                    self.line.setFixedHeight(1)
                    self.line.setProperty("wid","line")
                    self.gameL.addWidget(self.line)

                    self.button.clicked.connect(lambda:self.gameW.setVisible(not self.gameW.isVisible()))


                def renovate(self, games):
                    self.game = games
                    gamelist = copy.deepcopy(self.root.settings["gameList"][games])
                    for key, value in list(self.games.items()):
                        value.deleteLater()
                    self.games.clear()
                    for game_name in gamelist:
                        self.games[game_name] = self.Item(self, self.root, game_name)
                    self.langing()
                    self.label2.setText(f"({len(gamelist)})")

                def langing(self):
                    self.label.setText(self.game if self.game != "<:|default|:>" else self.root.langer.get("text.default"))

                def lighting(self,light):
                    if self.light != light:
                        self.light = light
                        self.btnPix[1] = change_color(getPath("src/assets/actions/eye.png"),QColor(25,25,25) if light else QColor(220,220,220))
                        self.btnPix[0] = change_color(getPath("src/assets/actions/eye-off.png"),QColor(25,25,25) if light else QColor(220,220,220))
                    self.button.setIcon(QIcon(self.btnPix[int(self.gameW.isVisible())]))

                class Item(QPushButton):
                    def __init__(self,parent=None,root=None,game=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.game = game
                        self.parent.gameL.addWidget(self)
                        self.setFixedHeight(40)
                        self.setProperty("wid","lbtn")
                        self.init_wid()
                        self.clicked.connect(lambda:self.parent.parent.parent.parent.changeGame(self.game))

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(5,5,5,5)
                        self.layout.setSpacing(10)

                        self.pixmap = QLabel()
                        self.pixmap.setFixedSize(30,30)
                        self.pixmap.setStyleSheet("width:30px;")
                        self.pixmap.setScaledContents(True)
                        self.layout.addWidget(self.pixmap,0)

                        self.textW = QWidget()
                        self.textW.setStyleSheet("background:transparent;")
                        self.layout.addWidget(self.textW)

                        self.textL = QVBoxLayout(self.textW)
                        self.textL.setContentsMargins(0,0,0,0)
                        self.textL.setSpacing(0)

                        self.text = QLabel()
                        self.text.setStyleSheet("background:transparent;font-size:14px;")
                        self.text.setProperty("wid","text")
                        self.textL.addWidget(self.text,0)
                        self.text.setFixedHeight(20)

                        self.version = QLabel()
                        self.version.setStyleSheet("background:transparent;")
                        self.version.setProperty("wid","lbtn")
                        self.textL.addWidget(self.version)
                        self.version.setFixedHeight(10)

                        self.layout.addStretch(1)

                    def showEvent(self,event):
                        super().showEvent(event)
                        vers = mdtScanner.getMdtMsg(self.game)
                        if vers:
                            pngPath = vers.get("icon")
                            if pngPath is not None:
                                self.pixmap.setPixmap(QPixmap(pngPath))
                            self.text.setText(self.game)
                            self.version.setText(f"v{vers['number']}.{vers['build']}{vers['modifier']}")



        class Launch(_Main):
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)

        class Log(_Main):
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)

        class Finished(_Main):
            """保存游戏数据进度页（index 5）。"""
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)
                self.init_wid()

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(30,30,30,30)
                self.layout.setSpacing(10)
                self.layout.setAlignment(Qt.AlignCenter)
                self.label = QLabel(self)
                self.label.setProperty("wid", "title")
                self.label.setWordWrap(True)
                self.label.setAlignment(Qt.AlignCenter)
                self.label.setStyleSheet("font-size:16px;")
                self.layout.addWidget(self.label)

            def setStatus(self, step):
                self.label.setText(self.root.langer.get("wid.pages.start.finished.save%d" % step))




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
