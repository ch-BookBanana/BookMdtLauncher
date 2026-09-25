
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
from PySide6.QtWidgets import  (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QScrollBar, QStackedWidget, QVBoxLayout
)
from ..utils import change_color

from ._init import *
from .downloads.game import Game

class Download(Page):
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

        def resizeEvent(self, event):
            self.scroll_slider.setGeometry(self.scroll.width() - 5, 0, 5, self.scroll.height())
            self.barShow()
            super().resizeEvent(event)

        def showEvent(self, event):
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

            def lighting(self, light: bool):
                if self.icon_ is not None:
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    logo = change_color(self.icon_, color)
                    pixmap = logo.pixmap(30, 30)

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
            super().__init__(parent)
            self.root = root
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


            self.game = self.add_page(Game,"wid.pages.download.game", "src/assets/nav/menu.png")

        def add_page(self, page_cls, text=None, icon=None):
            btn = self.parent.left.add_btn(text, icon)
            page_ = page_cls(self, self.root, text, icon)
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.stack.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.stack.setCurrentWidget(page_))
            if len(self.btns_) == 1:
                btn.click()
            return page_

