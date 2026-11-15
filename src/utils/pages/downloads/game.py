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

import copy, hashlib, json, os, re, time, webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPixmap, QTextOption
from src.BMLCore import registrar
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget
)

from ...events import events
from ...QDownloader import QDownloader
from ...mdtManager import mdtManager
from ...qthtimer import QThTimer
from ...options.scrolls import Scroll
from ...path_utils import getPath
from ...utils import _apply_md_image, change_color, md_to_html, t
from ...resources import (ACT_EYE, ACT_EYE_OFF, ACT_TIPS, BTN_DOWNLOAD,
                          FILE_GENERIC, ICON_MDT, ICON_MDTARC, ICON_MDTX,
                          NAV_LINK, NAV_MENU, TBT_CLOSE)
from ...registry import Box, registry

# 条目 key → 那一项的界面参数（原先写在登记里，现在归本文件自己拿）



_ACTIVE_DOWNLOADS = []






@registrar("core/download.item.actions").add("download", title="core.wid.pages.download.item.download", icon=BTN_DOWNLOAD)
def _item_action_download(b):
    """下载：点开下载弹窗（叠加浮层）。"""
    item = b.parent
    btn = item.RBtn(getPath(b.icon), b.title, item)
    btn.clicked.connect(lambda: events.emit(
        "overlayRequested", item.template.Download(item, item.data)))
    return btn


@registrar("core/download.item.actions").add("repoInfo", title="core.wid.pages.download.item.repoInfo", icon=NAV_MENU)
def _item_action_repo(b):
    """仓库信息：压进浮层栈。"""
    item = b.parent
    btn = item.RBtn(getPath(b.icon), b.title, item)
    btn.clicked.connect(lambda: events.emit(
        "stackRequested", item.template.RepoInfo(item, item.data, item.pixmap)))
    return btn


@registrar("core/download.item.actions").add("link", title="core.wid.pages.download.item.link", icon=NAV_LINK)
def _item_action_link(b):
    """外部链接：交给系统浏览器。"""
    item = b.parent
    btn = item.RBtn(getPath(b.icon), b.title, item)
    btn.clicked.connect(item.open_release)
    return btn


@registrar("core/download.tabs").add("game", title="core.wid.pages.download.game", icon=NAV_MENU)
class Game(QWidget):
    def __init__(self, parent=None, text=None, icon=None):
        super().__init__()
        # 条目 init 收到的是 Box（见 sources/_init.unpack_box 的说明）
        parent, text, icon = unpack_box(parent, text, icon)
        self.parent = parent
        self.text = text
        self.icon = icon
        self.init_wid()

    def init_wid(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(0)

        self.top = self.Top(self)
        self.layout.addWidget(self.top,0)

        self.line = QWidget()
        self.line.setFixedHeight(1)
        self.line.setProperty("wid", "line")
        self.line.setAttribute(Qt.WA_StyledBackground, True)
        self.layout.addWidget(self.line,0)

        self.main = self.Main(self)
        self.layout.addWidget(self.main, 1)
    
    class Top(QWidget):
        def __init__(self, parent=None):
            super().__init__()
            self.parent = parent
            self.setFixedHeight(35)  # 30 按钮 + 5 底部横向滑块
            self.init_wid()

        def init_wid(self):
            self.layout = QHBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            # 横向区：滚轮转为横向滚动，空白处可拖拽
            self.scroll = Scroll(self, horizontal=True, drag=True)
            self.layout.addWidget(self.scroll)

            self.bthGroup = QButtonGroup(self)

        def add_btn(self, text=None, icon=None, color=True):
            btn = self.Btns(text, getPath(icon), self, color)
            self.scroll.add(btn)
            self.bthGroup.addButton(btn)
            return btn

        class Btns(QPushButton):
            def __init__(self, text=None, icon=None, parent=None, color=True):
                super().__init__()
                self.parent = parent
                self.text_ = text
                self.icon_ = icon
                self.colorable = color
                self.init_ui()
                self.init_wid()
                events.theme.changed.connect(self.lighting)
                self.lighting(events.theme.light)
                events.lang.changed.connect(self.langing)

            def init_ui(self):
                self.setFixedHeight(30)
                self.setMinimumWidth(100)
                self.setAttribute(Qt.WA_StyledBackground, False)
                self.setProperty("wid", "btn-text")
                self.setCheckable(True)

            def init_wid(self):
                self.layout = QHBoxLayout(self)
                self.layout.setContentsMargins(5, 0, 5, 0)
                self.layout.setSpacing(5)

                self.icon = QLabel()
                self.icon.setAttribute(Qt.WA_StyledBackground, False)
                self.icon.setFixedSize(20, 20)
                self.icon.setScaledContents(False)
                self.layout.addWidget(self.icon)
                self.icon.setAlignment(Qt.AlignCenter)

                self.text = QLabel()
                self.text.setAttribute(Qt.WA_StyledBackground, False)
                self.text.setProperty("wid", "btn-text")
                self.langing()
                self.layout.addWidget(self.text)

            def langing(self):
                if self.text_ is not None:
                    self.text.setText(events.lang.get(self.text_))
                    self.setToolTip(events.lang.get(self.text_))

            def lighting(self, light: bool):
                if self.icon_ is not None:
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    logo = change_color(self.icon_, color) if self.colorable else QIcon(self.icon_)
                    pixmap = logo.pixmap(20, 20)

                    if not pixmap.isNull():
                        smooth_pixmap = pixmap.scaled(
                            16, 16,
                            Qt.KeepAspectRatio,
                            Qt.FastTransformation
                        )
                        self.icon.setPixmap(smooth_pixmap)
                    else:
                        events.logger.warning(f"Failed to load pixmap for {self.icon_}")

            def setText(self, _text):
                self.text_ = _text
                self.langing()

            def setIcon(self, _icon):
                self.icon_ = _icon
                self.lighting(events.settings["theme"])

    class Main(QWidget):
        def __init__(self, parent=None):
            super().__init__()
            self.parent = parent
            self.init_wid()
            self.btns_[0].click()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignHCenter)

            # 页面栈（每个 Template 自带滚动 + 按钮栏）
            self.stack = QStackedWidget()
            self.layout.addWidget(self.stack, 1)

            self.pages_ = []
            self.btns_ = []

            # 下载源从注册表取：本模块的 register() 登记一次（由 builtin.py 调）。
            for e in registry.entries("core.download.sources"):
                page = self.add_page(e, color=_FIELDS.get(e.key.replace("/", "."), {}).get("color", True))
                registry.bind("core.download.sources", e.key, main=page, btn=page.btn)

        def add_page(self, entry, color=True):
            """按条目建一个下载源：备好页签按钮 → 交给条目的 init 去造。"""
            btn = self.parent.top.add_btn(entry.title, entry.icon, color=color)
            page_ = entry.init(Box(parent=self, entry=entry))
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.stack.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.stack.setCurrentWidget(page_))
            if len(self.btns_) == 1:
                btn.click()
            return page_

        # 下载界面游戏本体模板


# 三个源在 sources/ 下（Template 在 sources/_init.py），import 即登记
from .sources._init import _FIELDS, unpack_box
from .sources import mindustryarc, mindustryx, origin    # noqa: F401,E402
