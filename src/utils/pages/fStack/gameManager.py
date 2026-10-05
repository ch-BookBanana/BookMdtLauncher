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

游戏管理浮层：左栏功能菜单 + 右栏内容。

形态和设置页一样（左栏选、右栏看），区别只在于它活在浮层里、对象是某一个
游戏实例。

    左栏（core.gameManager.pages）        右栏
    ├── 设置  → GameSettings（文件夹 / Java / 改名 / 删除…）
    └── …     将来加 Mods、存档之类

加一页 = 写一个模块 + 在它末尾加一条 registry.add（见 gameSettings.py 末尾），
本文件一行都不用动 —— 它是纯容器，不认识任何一个具体页。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ...events import events
from ...registry import Box, registry


class GameManager(QWidget):
    """某个实例的游戏管理浮层。"""

    LEFT_WIDTH = 180        # 与设置页左栏同宽，视觉上是一套

    def __init__(self, game, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.game = game            # 管理的实例名（现取，改名后跟着换）
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.init_wid()

    def init_wid(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 左栏：功能菜单。项来自扩展点，这里只负责摆位置与切页。
        self.left = QWidget()
        self.left.setFixedWidth(self.LEFT_WIDTH)
        self.left.setAttribute(Qt.WA_StyledBackground, True)
        self.left_layout = QVBoxLayout(self.left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)
        self.left_layout.setAlignment(Qt.AlignTop)

        self.line = QWidget()
        self.line.setProperty("wid", "line")
        self.line.setFixedWidth(1)
        self.line.setAttribute(Qt.WA_StyledBackground, True)

        # 右栏：各功能页
        self.pages = QStackedWidget()

        self.layout.addWidget(self.left, 0)
        self.layout.addWidget(self.line, 0)
        self.layout.addWidget(self.pages, 1)

        self._build_pages()

    def _build_pages(self):
        """按 core.gameManager.pages 构建左栏与右栏。

        子页的 init 由各自提供（注册方知道怎么造），这里只备一个 parent
        （就是本浮层，子页要用 self.game 时从 b.parent.game 现取）。
        """
        self.btns = []
        for e in registry.entries("core.gameManager.pages"):
            wid = e.init(Box(parent=self, root=self.root, entry=e))
            self.pages.addWidget(wid)

            btn = QPushButton(events.lang.get(e.title))
            btn.setProperty("wid", "lbtn")
            btn.setFixedHeight(40)
            btn.setAttribute(Qt.WA_StyledBackground, True)
            btn.clicked.connect(lambda _checked=False, w=wid: self.pages.setCurrentWidget(w))
            self.left_layout.addWidget(btn, 0)
            self.btns.append(btn)

        if self.btns:
            self.btns[0].click()
