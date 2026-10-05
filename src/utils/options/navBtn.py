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

左栏导航按钮（图标 + 文字、可选中、跟着主题与语言走）。

设置页左栏与游戏管理浮层的左栏是同一个东西 —— 同一套尺寸、同一套选中态、
同样要在主题/语言切换时自己刷新。所以按钮类放在这里共用，而不是各写各的
（各写各的下场就是两边长得不一样，改一处忘了另一处）。

用它的地方要自己准备：
    * 一个 QButtonGroup —— 选中是互斥的
    * 一个 Scroll —— 项多了要能滚
见 Setting.Left 与 GameManager._build_pages。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from ..bus import bus
from ..events import events
from ..utils import change_color

__all__ = ["NavBtn"]


class NavBtn(QPushButton):
    """左栏的一颗按钮。

    text 传**语言键**（不是翻好的文字）：语言一换，langing 自己重取，
    调用方不用管。icon 传 resources 常量或插件的 "${plugin}/…"，可为 None。
    """

    WIDTH = 120
    HEIGHT = 30
    ICON_BOX = 30
    TEXT_BOX = 90

    def __init__(self, text=None, icon=None, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.text_ = text
        self.icon_ = icon
        self.init_ui()
        self.init_wid()
        bus.bind(self)

    def init_ui(self):
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setProperty("wid", "lbtn")
        self.setCheckable(True)

    def init_wid(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        self.icon = QLabel()
        self.icon.setAttribute(Qt.WA_StyledBackground, False)
        self.icon.setFixedSize(self.ICON_BOX, self.ICON_BOX)
        self.icon.setScaledContents(False)
        self.icon.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.icon)

        self.text = QLabel()
        self.text.setAttribute(Qt.WA_StyledBackground, False)
        self.text.setFixedSize(self.TEXT_BOX, self.HEIGHT)
        self.text.setProperty("wid", "lbtn")
        self.langing()
        self.layout.addWidget(self.text)

    def langing(self):
        if self.text_ is not None:
            self.text.setText(events.lang.get(self.text_))
            self.setToolTip(events.lang.get(self.text_))

    def lighting(self, light: bool):
        """图标是白图，按主题改成深/浅色才看得见。"""
        if self.icon_ is None:
            return
        color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
        pixmap = change_color(self.icon_, color).pixmap(self.ICON_BOX, self.ICON_BOX)
        if pixmap.isNull():
            events.logger.warning(f"Failed to load pixmap for {self.icon_}")
            return
        self.icon.setPixmap(pixmap.scaled(22, 22, Qt.KeepAspectRatio,
                                          Qt.FastTransformation))

    def setText(self, _text):
        self.text_ = _text
        self.langing()

    def setIcon(self, _icon):
        self.icon_ = _icon
        self.lighting(bool(events.settings["theme"]))
