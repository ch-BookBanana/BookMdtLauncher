
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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout
)
from ..events import events
from ..options.navBtn import NavBtn
from ..options.scrolls import Scroll
from ..utils import change_color
from ..resources import (BTN_DOWNLOAD, NAV_MENU)
from ..registry import page, Box, registry

from ._init import *
from .downloads.game import Game

@page("core.download")
class Download(Page):
    name = "core.wid.pages.download"
    icon = BTN_DOWNLOAD
    order = 20

    def __init__(self, btn=None):
        super().__init__(btn)

    class Left(Leftw):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.resize_(120)
            self.init_wid()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.scroll = Scroll(self)
            self.layout.addWidget(self.scroll)

            self.bthGroup = QButtonGroup(self)

        def add_btn(self, text=None, icon=None):
            btn = NavBtn(text, icon, self)
            self.scroll.add(btn)
            self.bthGroup.addButton(btn)
            return btn

    class Main(Mainw):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.init_wid()

        def init_wid(self):
            self.layout = QHBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignLeft)

            self.line = QWidget()
            self.line.setProperty("wid", "line")
            self.line.setAttribute(Qt.WA_StyledBackground, True)
            self.line.setFixedWidth(1)
            self.layout.addWidget(self.line, 0)

            self.stack = QStackedWidget()
            self.layout.addWidget(self.stack, 1)

            self.pages_ = []
            self.btns_ = []

            # 页签从注册表取：登记在模块加载时做一次（见文件末尾）。
            for e in registry.entries("core.download.tabs"):
                page = self.add_page(e)
                setattr(self, e.name, page)          # self.game
                registry.bind("core.download.tabs", e.key, main=page, btn=page.btn)

        def add_page(self, entry):
            """按条目建一个页签：备好按钮 → 交给条目的 init 去造。"""
            btn = self.parent.left.add_btn(entry.title, entry.icon)
            page_ = entry.init(Box(parent=self, entry=entry, btn=btn))
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.stack.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.stack.setCurrentWidget(page_))
            if len(self.btns_) == 1:
                btn.click()
            return page_



# ── 左栏页签的登记（模块加载时一次）──
# init 从 Box.parent（承载它的下载页 Main 实例）取宿主；title/icon 走条目字段。

registry.add("core.download.tabs", "core.download.game",
             init=lambda b: Game(b.parent, b.title, b.icon),
             order=10,
             title="core.wid.pages.download.game", icon=NAV_MENU)
