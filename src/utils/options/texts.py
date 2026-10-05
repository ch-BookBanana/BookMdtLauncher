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

from ..events import events
from ._init import *


class Title(QWidget):
    def __init__(self, parent=None, text=None):
        super().__init__()
        self.parent = parent
        self.text_ = text
        self.init_wid()
        bus.bind(self)

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
        self.text.setText(events.lang.get(self.text_))


class Line(QWidget):
    def __init__(self, parent=None, text=None):
        super().__init__()
        self.parent = parent
        self.init_wid()

    def init_wid(self):
        self.setFixedHeight(1)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.line = QWidget()
        self.line.setProperty("wid","line")
        self.line.setAttribute(Qt.WA_StyledBackground,True)
        self.layout.addWidget(self.line)
