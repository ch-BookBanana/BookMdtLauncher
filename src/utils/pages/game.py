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
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout

from ._init import *


class Game(Page):
    def __init__(self, parent=None, root=None, text=None, logo=None):
        super().__init__(parent, root, text, logo)

    class Main(Mainw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
            self.init_wid()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.todoText = QLabel("UNFINISHED")
            self.todoText.setProperty("wid", "text")
            self.todoText.setAlignment(Qt.AlignCenter)
            self.todoText.setStyleSheet("font-size: 20px;")
            self.layout.addWidget(self.todoText,1)

        def open_manage(self, game):
            page = self.gameManage(game, self, self.root)
            self.root.window.floatingOverlay.add_page(page)

        class gameManage(QWidget):
            """游戏管理页：叠加浮层（FloatingOverlay）页面。

            骨架阶段仅搭好「顶栏 + 分割线 + 主体」三层结构与关闭出口，
            除关闭外的交互逻辑一律留空待实现。"""

            def __init__(self, game, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.game = game
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                # 遮罩与居中由所属叠加浮层统一提供，本页自身保持透明
                pass

            def init_wid(self):
                self.layout = QHBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignCenter)

                self.panel = self.Panel(self, self.root)
                self.layout.addWidget(self.panel, 0)


            class Panel(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setFixedSize(520, 365)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.top = self.Top(self, self.root)
                    self.layout.addWidget(self.top, 0)

                    self.line = QWidget(self)
                    self.line.setFixedHeight(1)
                    self.line.setProperty("wid", "line")
                    self.layout.addWidget(self.line, 0)

                    self.body = self.Body(self, self.root)
                    self.layout.addWidget(self.body, 1)

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

                        self.title = QLabel("游戏管理")
                        self.title.setProperty("wid", "title")
                        self.title.setStyleSheet("font-size: 16px;")
                        self.layout.addWidget(self.title, 1)

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
                        """主体内容区：后续在此填充管理项"""

                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.init_wid()

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(20, 20, 20, 20)
                            self.layout.setSpacing(10)
                            self.layout.setAlignment(Qt.AlignTop)

                            self.todoText = QLabel("UNFINISHED")
                            self.todoText.setProperty("wid", "title")
                            self.todoText.setAlignment(Qt.AlignCenter)
                            self.todoText.setStyleSheet("font-size: 20px;")
                            self.layout.addWidget(self.todoText, 1)


