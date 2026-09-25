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

import os
import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPalette, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedLayout, QStackedWidget, QTextEdit, QVBoxLayout

from src.utils.path_utils import getPath

from ..mdtScanner import mdtScanner
from ..utils import change_color, t

from ._init import *
from .fStack.gameManage import GameManage


# 游戏（Arc/Mindustry）日志行前缀，如 "[I] xxx" / "[E] xxx"
_LOG_TAG = re.compile(r"^\[([A-Za-z])\]\s*")

# 日志前缀 -> (写入日志文件的等级, 控制台配色角色)
_LOG_STYLES = {
    "I": ("info",    "good"),      # 信息
    "E": ("error",   "error"),     # 错误
    "W": ("warning", "warning"),   # 警告
    "D": ("debug",   "debug"),     # 调试
    "V": ("debug",   "debug"),     # 详细
}

# 日志正文配色：角色 -> (R, G, B)。浅色主题必须用深色字，否则浅底上几乎看不见
# 色值一律用整数三元组：QColor 不认 "rgb(r, g, b)" 这种 CSS 字符串，
# 字符串会得到无效颜色，填进调色板/字符格式就是黑色——暗色主题下正好黑底黑字
_LOG_COLORS = {
    "dark": {
        "info":     (219, 219, 219),   # 无前缀的普通输出：白
        "error":    (232, 106, 106),   # 错误：红（整行）
        "warning":  (230, 190, 100),   # 警告：黄（整行）
        "debug":    (130, 170, 220),   # 调试：蓝（整行）
        "good":     (219, 219, 219),   # [I] 正文：跟随主题的黑白
        "launcher": (150, 150, 150),   # [L] 正文：灰
    },
    "light": {
        "info":     (64, 64, 64),
        "error":    (190, 40, 40),
        "warning":  (158, 108, 0),
        "debug":    (38, 100, 174),
        "good":     (64, 64, 64),
        "launcher": (110, 110, 110),
    },
}

# 日志前缀配色：只有「前缀与正文不同色」的角色列在这里（[L] 紫、[I] 绿）；
# 没列的角色取正文色，整行同色（警告、报错就是全字段渲染）
_LOG_TAG_COLORS = {
    "dark": {
        "good":     (126, 200, 126),   # [I]：绿
        "launcher": (186, 140, 235),   # [L]：紫
    },
    "light": {
        "good":     (24, 124, 56),
        "launcher": (128, 78, 190),
    },
}

# 控制台底色（跟随主题）：QTextEdit 的正文区是视口画的，视口调色板在创建时就固定了，
# 单靠 qss 背景或控件调色板都改不动它，必须在 Console.lighting 里直接设视口调色板
_CONSOLE_BG = {
    "dark":  (55, 55, 55),
    "light": (229, 228, 228),
}


def _log_colors(light=False):
    """按主题取日志正文配色表（light=True 用浅色主题配色）。"""
    return _LOG_COLORS["light" if light else "dark"]


def _log_tag_colors(light=False):
    """按主题取日志前缀配色表（只有需要与正文区分的角色）。"""
    return _LOG_TAG_COLORS["light" if light else "dark"]


def _parse_log_line(text, fallback="info"):
    """解析一行游戏输出，返回 (日志等级, 配色角色, 前缀)。

    带 [I]/[E]/[W]/[D]/[V] 前缀时以前缀为准，并把前缀切出来交给控制台单独上色；
    无前缀时用 fallback（stdout → info、stderr → error）决定，前缀为空串。
    """
    match = _LOG_TAG.match(text)
    if match:
        style = _LOG_STYLES.get(match.group(1).upper())
        if style:
            return style[0], style[1], match.group(0)
    return fallback, ("error" if fallback == "error" else "info"), ""


class Start(Page):
    def __init__(self, parent=None, root=None, text=None, logo=None):
        root.signals.register("start_gameChanged", Signal(object))
        super().__init__(parent, root, text, logo)
        # 左侧信息改为事件驱动：启动刷新一次 + 订阅 mdtScanner 事件（替代 1 秒轮询）
        self.left.refresh()
        self.root.mdtScanner.on_game_changed.connect(self.left._on_game_changed)
        self.root.launcher.game_launched.connect(self._on_game_launched)
        self.root.launcher.game_started.connect(lambda: self.main.stack.setCurrentIndex(4))
        self.root.launcher.game_started.connect(lambda: self.left.main.setCurrentIndex(4))
        self.root.launcher.lifecycle_finished.connect(lambda: self.main.stack.setCurrentIndex(0))
        self.root.launcher.lifecycle_finished.connect(lambda: self.left.main.setCurrentIndex(0))
        # 启动阶段（校验/Java 流程）与游戏进程输出：写入日志文件 + 主区控制台
        self.root.launcher.log.connect(self._on_launcher_log)
        self.root.launcher.game_log.connect(self._on_game_log)

    def _on_game_launched(self):
        """每次启动游戏：先清空上一次的控制台日志，再切到「启动中」页。

        清空必须发生在 launcher 发日志之前，因此挂在 game_launched（最先发出）上。
        """
        self.main.clear_log()
        self.main.stack.setCurrentIndex(3)
        self.left.main.setCurrentIndex(3)

    def _on_launcher_log(self, dic):
        """启动阶段消息（参数校验、Java 流程）：写入日志文件 + 主区控制台。"""
        text = dic["text"]
        if dic["type"] == "error":
            self.root.logger.error("[launcher]" + text)
        else:
            self.root.logger.info("[launcher]" + text)
        self.main.append_log("[L] ", text, "launcher")

    def _on_game_log(self, dic):
        """游戏进程输出：写入日志文件 + 主区控制台（[I] 绿 / [E] 红，其余按等级着色）。"""
        text = dic["text"]
        level, role, prefix = _parse_log_line(text, dic["type"])
        if level == "error":
            self.root.logger.error("[game]" + text, name="Game")
        elif level == "warning":
            self.root.logger.warning("[game]" + text, name="Game")
        else:
            self.root.logger.info("[game]" + text, name="Game")
        self.main.append_log(prefix, text[len(prefix):], role)

    def changeGame(self, game=None):
        if game == self.root.settings["defaultGame"]: return
        mdts = self.root.mdtScanner.getMdts()
        self.root.settings["defaultGame"] = game if game in mdts else (mdts[0] if mdts else None)
        self.root.signals.emit("start_gameChanged", game)
        self.left.refresh()

    class Left(Leftw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
            self.resize_(250)
            self.init_wid()
            self.game = {
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

        def refresh(self):
            """defaultGame 或其图标/版本变化时刷新左侧信息（主线程调用）。

            替代旧 changeTimer：不再 1 秒轮询，由 mdtScanner 事件驱动触发；
            直接调用 sets 更新 UI（主线程安全，无需 QThTimer 中转）。"""
            default_game = self.root.mdtScanner.ensure_default_game()
            game_msg = self.root.mdtScanner.getMdtMsg(default_game) if default_game else None
            # 底部按钮随「有无游戏」切换（无游戏时改为跳转下载页）
            self.main.set_have_game(default_game is not None)
            if self.game["name"] != default_game:
                if default_game is None:
                    self.game["name"] = self.game["vers"] = self.game["icon_key"] = None
                    # 图标需显式清空，否则会残留上一份游戏的图标
                    self.sets((True,QPixmap()),(True,self.root.langer.get("wid.pages.start.gameNotfound")),(True,self.root.langer.get("wid.pages.start.gameNotfound2")))
                else:
                    self.game["name"] = default_game
                    self.game["vers"] = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}" if game_msg else None
                    self.sets((False,None),(True,default_game),(True,self.game["vers"] or ""))
            elif self.game["name"] and game_msg:
                new_vers = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}"
                if self.game["vers"] != new_vers:
                    self.game["vers"] = new_vers
                    self.sets((False,None),(False,None),(True,new_vers))
            # 图标：icon_key 由 路径+mtime+size 构成，变化才重载
            if self.game["name"] and game_msg:
                try:
                    icon_key = f"{game_msg['icon']}:{os.path.getmtime(game_msg['icon'])}:{os.path.getsize(game_msg['icon'])}"
                except OSError:
                    icon_key = None
            else:
                icon_key = None
            if self.game["icon_key"] != icon_key:
                self.game["icon_key"] = icon_key
                self.sets((True, QPixmap(game_msg["icon"]) if icon_key else QPixmap()),(False,None),(False,None))

        def _on_game_changed(self, data):
            """mdtScanner 事件：defaultGame 受影响时刷新左侧信息。"""
            etype = data["type"]
            if etype in ("newGame", "deleteGame", "nameChanged"):
                self.refresh()
            elif etype == "iconChanged" and data["game"] == self.game["name"]:
                self.refresh()
            
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

            def set_have_game(self, have: bool):
                """切换左侧底部按钮：有游戏显示「选择游戏」，无游戏显示「下载界面」。"""
                self.start.set_have_game(have)

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
                    self.have_game = True
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                    self.action =self.Btn(self,self.root)
                    self.action.setFixedSize(QSize(170,50))
                    self.layout.addWidget(self.action)

                    self.action.clicked.connect(self._on_click)

                def _on_click(self):
                    # 有游戏：进入游戏选择列表；无游戏：前往下载页的「游戏本体」分类
                    if self.have_game:
                        self.parent.setCurrentIndex(2)
                        self.parent.parent.parent.main.stack.setCurrentIndex(2)
                    else:
                        download = self.root.window.main.main.download
                        download.click()
                        download.main.game.btn.click()

                def set_have_game(self, have: bool):
                    if self.have_game == have:
                        return
                    self.have_game = have
                    self.langing()

                def langing(self):
                    btn = "wid.pages.start.gamebtn" if self.have_game else "wid.pages.start.downloadbtn"
                    self.action.setText(self.root.langer.get(btn))

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
                """左侧栏「游戏运行中」页：唯一按钮是强制关闭（强杀游戏进程）。"""
                def __init__(self, parent=None, root=None):
                    super().__init__(parent,root)
                    self.init_wid()
                    self.langing()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(30,50,30,50)
                    self.layout.setSpacing(10)
                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                    self.stop = self.Btn(self,self.root)
                    self.stop.setFixedSize(QSize(170,50))
                    self.layout.addWidget(self.stop)

                    self.stop.clicked.connect(self._on_click)

                def _on_click(self):
                    """强杀游戏进程；成功则回主界面交给生命周期结束信号，
                    失败（进程已不在）自己回，避免卡在运行页。"""
                    if self.root.launcher.kill_game():
                        return
                    self.parent.setCurrentIndex(0)
                    self.parent.parent.parent.main.stack.setCurrentIndex(0)

                def langing(self):
                    self.stop.setText(self.root.langer.get("wid.pages.start.suspend.stop"))

    class Main(Mainw):
        LOG_MAX_LINES = 2000   # 控制台保留的最大行数，超出后丢弃最旧的行

        def __init__(self,parent=None,root=None):
            super().__init__(parent,root)
            # 已输出的日志（前缀, 正文, 配色角色）：主题切换时按新配色整篇重绘
            self.log_lines = []
            self.light = bool(root.settings["theme"])
            self.colors = _log_colors(self.light)
            self.tags = _log_tag_colors(self.light)
            self.init_wid()

        def init_wid(self):
            self.layout = QStackedLayout(self)
            self.layout.setStackingMode(QStackedLayout.StackAll)

            self.backg = self.Backg(self,self.root)
            self.layout.addWidget(self.backg)

            self.stack = QStackedWidget()
            self.layout.addWidget(self.stack)

            self.layout.setCurrentIndex(1)

            # 日志控制台：Launch（启动准备中）与 Log（进程运行中）两页
            self.consoles = []

            self.start = self.Start(self,self.root)
            self.mod = self.Mod(self,self.root)
            self.world = self.World(self,self.root)
            self.launch = self.Console(self,self.root)
            self.log = self.Console(self,self.root)

        def append_log(self, prefix, text, role):
            """记录一行日志并刷新两个控制台视图（两页内容保持一致）。

            前缀与正文分开上色：前缀色取自 tags（[L] 紫、[I] 绿），
            没列前缀色的角色（警告、报错）整行用正文色，即全字段渲染。
            """
            self.log_lines.append((prefix, text, role))
            if len(self.log_lines) > self.LOG_MAX_LINES:
                del self.log_lines[:len(self.log_lines) - self.LOG_MAX_LINES]
            color = self.colors[role]
            tag_color = self.tags.get(role, color)
            for console in self.consoles:
                console.append(prefix, text, color, tag_color)

        def clear_log(self):
            """开始一次新的启动：清空上一次残留的输出（Launch / Log 两页同时清）。"""
            self.log_lines.clear()
            for console in self.consoles:
                console.clear_log()

        def lighting(self, light):
            """主题切换：换配色表并把已输出的日志整篇重绘。"""
            if self.light == light:
                return
            self.light = light
            self.colors = _log_colors(light)
            self.tags = _log_tag_colors(light)
            for console in self.consoles:
                console.render(self.log_lines, self.colors, self.tags)

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
                self.settings.clicked.connect(lambda: self.root.window.floatingStack.add_page(GameManage(self.root.settings["defaultGame"], self, self.root)))

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
            """游戏分组列表：订阅 mdtScanner 事件增量更新，不做整页重建。"""

            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)
                self.groups = {}
                self.init_wid()
                self.rebuild()
                self.groups["<:|default|:>"].show_items()
                # 订阅 mdtScanner 事件，按类型精确更新对应条目
                self.root.mdtScanner.on_game_changed.connect(self._on_game_changed)

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(0)

                self.scroll = QScrollArea(self)
                self.scroll.setWidgetResizable(True)
                self.scroll.setFrameShape(QFrame.NoFrame)
                self.layout.addWidget(self.scroll)

                self.box = QWidget()
                self.box.setProperty("wid","color2")
                self.box_l = QVBoxLayout(self.box)
                self.box_l.setContentsMargins(10,10,10,10)
                self.box_l.setSpacing(10)
                self.box_l.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
                self.scroll.setWidget(self.box)

            def rebuild(self):
                """按 settings.gameList 全量重建分组（仅初始构建）。"""
                for group in self.groups.values():
                    group.release_all()
                    group.deleteLater()
                self.groups = {}
                for name, games in self.root.settings["gameList"].items():
                    self.groups[name] = self.Group(self, self.root, name, games)

            def _on_game_changed(self, data):
                """newGame/deleteGame/nameChanged/iconChanged → 精确更新对应条目。"""
                etype = data["type"]
                game = data["game"]
                if etype == "newGame":
                    # checkGame 总是把新游戏追加到 default 组
                    group = self.groups.get("<:|default|:>")
                    if group:
                        group.add(game)
                elif etype == "deleteGame":
                    for group in self.groups.values():
                        if group.remove(game):
                            break
                elif etype == "nameChanged":
                    for group in self.groups.values():
                        if group.rename(data["old_name"], game):
                            break
                elif etype == "iconChanged":
                    for group in self.groups.values():
                        if group.refresh_icon(game):
                            break

            class Group(QWidget):
                """一个游戏分组：标题栏 + 可折叠的条目列表。"""

                def __init__(self,parent=None,root=None,name="",games=()):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.name = name
                    self.items = {}
                    self.light = None
                    self.foldPix = [QPixmap(), QPixmap()]
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.setStyleSheet("border-radius:10px;max-width:600px;")
                    self.init_wid()
                    self.parent.box_l.addWidget(self)
                    self.body.hide()
                    self.langing()
                    self.add_many(games)

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(10,10,10,10)
                    self.layout.setSpacing(5)

                    # 标题栏：分组名 + 数量 + 折叠按钮
                    self.head = QWidget()
                    self.head.setFixedHeight(40)
                    self.layout.addWidget(self.head)
                    self.head_l = QHBoxLayout(self.head)
                    self.head_l.setContentsMargins(15,0,0,0)
                    self.head_l.setSpacing(5)
                    self.head_l.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

                    self.title = QLabel()
                    self.title.setProperty("wid","text")
                    self.title.setStyleSheet("font-size:16px;")
                    self.head_l.addWidget(self.title, 0)

                    self.count = QLabel()
                    self.count.setProperty("wid","lbtn")
                    self.count.setStyleSheet("font-size:14px;")
                    self.head_l.addWidget(self.count, 0)
                    self.head_l.addStretch(1)

                    self.fold_btn = QPushButton()
                    self.fold_btn.setFixedSize(40,40)
                    self.fold_btn.setProperty("wid","lbtn")
                    self.fold_btn.setStyleSheet("border-radius:20px;")
                    self.fold_btn.clicked.connect(self.toggle)
                    self.head_l.addWidget(self.fold_btn)

                    # 条目容器（可折叠）
                    self.body = QWidget()
                    self.layout.addWidget(self.body)
                    self.body_l = QVBoxLayout(self.body)
                    self.body_l.setContentsMargins(0,0,0,0)
                    self.body_l.setSpacing(5)
                    self.line = QWidget()
                    self.line.setFixedHeight(1)
                    self.line.setProperty("wid","line")
                    self.body_l.addWidget(self.line)

                def langing(self):
                    self.title.setText(self.name if self.name != "<:|default|:>" else self.root.langer.get("text.default"))

                def lighting(self,light):
                    if self.light != light:
                        self.light = light
                        color = QColor(25,25,25) if light else QColor(220,220,220)
                        self.foldPix[1] = change_color(getPath("src/assets/actions/eye.png"), color)
                        self.foldPix[0] = change_color(getPath("src/assets/actions/eye-off.png"), color)
                    self._sync_fold_icon()

                def add_many(self, names):
                    for name in names:
                        self.add(name)

                def add(self, name):
                    """新增条目（幂等，newGame 事件用）。"""
                    if name not in self.items:
                        self.items[name] = self.Item(self, self.root, name)
                        self.count.setText(f"({len(self.items)})")

                def remove(self, name):
                    """移除条目（deleteGame 事件用）；命中返回 True。"""
                    item = self.items.pop(name, None)
                    if item is not None:
                        item.release()
                        item.deleteLater()
                        self.count.setText(f"({len(self.items)})")
                    return item is not None

                def rename(self, old, new):
                    """改名：换 key 与显示文本（nameChanged 事件用）；命中返回 True。"""
                    item = self.items.pop(old, None)
                    if item is not None:
                        item.release()
                        item.game = new
                        item.title.setText(new)
                        item.acquire()
                        self.items[new] = item
                    return item is not None

                def refresh_icon(self, name):
                    """图标文件变化：重取条目图标（iconChanged 事件用）；命中返回 True。"""
                    item = self.items.get(name)
                    if item is not None:
                        item.acquire(force=True)
                    return item is not None

                def release_all(self):
                    """释放本组所有条目图标引用（分组销毁前调用）。"""
                    for item in self.items.values():
                        item.release()
                    self.items.clear()

                def toggle(self):
                    self.body.setVisible(not self.body.isVisible())
                    self._sync_fold_icon()

                def show_items(self):
                    """展开条目（default 组初始展开用）。"""
                    self.body.show()
                    self._sync_fold_icon()

                def _sync_fold_icon(self):
                    self.fold_btn.setIcon(QIcon(self.foldPix[int(self.body.isVisible())]))

                class Item(QPushButton):
                    """单个游戏条目：图标 + 名称 + 版本。"""

                    def __init__(self,parent=None,root=None,game=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.game = game
                        self._held = False
                        self.parent.body_l.addWidget(self)
                        self.setFixedHeight(40)
                        self.setProperty("wid","lbtn")
                        self.init_wid()
                        self.clicked.connect(lambda:self.parent.parent.parent.parent.changeGame(self.game))

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(5,5,5,5)
                        self.layout.setSpacing(10)

                        self.icon = QLabel()
                        self.icon.setFixedSize(30,30)
                        self.icon.setScaledContents(True)
                        self.layout.addWidget(self.icon,0)

                        self.textW = QWidget()
                        self.textW.setStyleSheet("background:transparent;")
                        self.layout.addWidget(self.textW)
                        self.textL = QVBoxLayout(self.textW)
                        self.textL.setContentsMargins(0,0,0,0)
                        self.textL.setSpacing(0)

                        self.title = QLabel()
                        self.title.setStyleSheet("background:transparent;font-size:14px;")
                        self.title.setProperty("wid","text")
                        self.title.setFixedHeight(20)
                        self.textL.addWidget(self.title,0)

                        self.version = QLabel()
                        self.version.setStyleSheet("background:transparent;")
                        self.version.setProperty("wid","lbtn")
                        self.version.setFixedHeight(10)
                        self.textL.addWidget(self.version,0)

                        self.layout.addStretch(1)

                    def showEvent(self,event):
                        super().showEvent(event)
                        vers = self.root.mdtScanner.getMdtMsg(self.game)
                        if vers:
                            self.acquire()
                            self.title.setText(self.game)
                            self.version.setText(f"v{vers['number']}.{vers['build']}{vers['modifier']}")

                    def acquire(self, force=False):
                        """取图标 +1 引用；force 先释放旧引用再重取（iconChanged 用）。"""
                        if force and self._held:
                            mdtScanner.release_icon_pixmap(self.game)
                            self._held = False
                        if not self._held:
                            pix = mdtScanner.get_icon_pixmap(self.game, 30)
                            self._held = True
                            if not pix.isNull():
                                self.icon.setPixmap(pix)

                    def release(self):
                        """释放图标引用（-1，归零自动清缓存）；条目销毁前调用。"""
                        if self._held:
                            mdtScanner.release_icon_pixmap(self.game)
                            self._held = False
                            self.icon.clear()

        class Console(_Main):
            """主区日志控制台：Launch（启动准备中）与 Log（进程运行中）两页各一个视图。"""
            def __init__(self,parent=None,root=None):
                super().__init__(parent,root)
                self.setAttribute(Qt.WA_StyledBackground,True)
                self.parent.consoles.append(self)
                self.init_wid()
                self.lighting(self.parent.light)

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(20,20,20,20)
                self.layout.setSpacing(0)

                self.view = QTextEdit(self)
                self.view.setReadOnly(True)
                self.view.setFrameShape(QFrame.NoFrame)
                # 边框/字体由 qss（QTextEdit[wid="console"]）提供；
                # 底色统一走调色板（见 lighting），避免两处色值各写一份
                self.view.setProperty("wid","console")
                self.layout.addWidget(self.view)

            def lighting(self, light):
                """主题切换：控制台底色与默认字色跟着换。

                视口调色板必须单独设一份：QTextEdit 的正文区由视口的 QPalette.Base 绘制，
                视口自己显式设过调色板后就不会再继承父控件的，只改控件调色板会露系统黑底。
                """
                palette = self.view.palette()
                palette.setColor(QPalette.Base, QColor(*_CONSOLE_BG["light" if light else "dark"]))
                palette.setColor(QPalette.Text, QColor(*_log_colors(light)["info"]))
                self.view.setPalette(palette)
                self.view.viewport().setPalette(palette)
                self.view.viewport().setAutoFillBackground(True)

            def append(self, prefix, text, color, tag_color):
                """追加一行着色文本；仅当停在底部时才跟随滚动，不打断用户翻阅。"""
                bar = self.view.verticalScrollBar()
                follow = bar.value() >= bar.maximum() - 4
                self._write(prefix, text, color, tag_color)
                self._trim()
                if follow:
                    self.view.moveCursor(QTextCursor.End)

            def render(self, lines, colors, tags):
                """按当前主题整篇重绘（主题切换时用）。"""
                bar = self.view.verticalScrollBar()
                follow = bar.value() >= bar.maximum() - 4
                self.view.clear()
                for prefix, text, role in lines:
                    color = colors[role]
                    self._write(prefix, text, color, tags.get(role, color))
                if follow:
                    self.view.moveCursor(QTextCursor.End)

            def clear_log(self):
                """清空本视图的全部日志，并把滚动位置归零。"""
                self.view.clear()
                self.view.moveCursor(QTextCursor.Start)

            # ---- 内部 ----

            def _write(self, prefix, text, color, tag_color):
                """在文档末尾写入一行：前缀用 tag_color、正文用 color，各一段。"""
                cursor = self.view.textCursor()
                cursor.movePosition(QTextCursor.End)
                if prefix:
                    tag = QTextCharFormat()
                    tag.setForeground(QColor(*tag_color))
                    cursor.insertText(prefix, tag)
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(*color))
                cursor.insertText(text + "\n", fmt)

            def _trim(self):
                """行数上限：超出后丢掉最旧的行，避免长时间挂机把内存吃满。

                blockCount 比行数多 1（末尾换行会多出一个空块）。
                """
                doc = self.view.document()
                while doc.blockCount() - 1 > self.parent.LOG_MAX_LINES:
                    clip = QTextCursor(doc)
                    clip.movePosition(QTextCursor.Start)
                    clip.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
                    clip.removeSelectedText()

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
