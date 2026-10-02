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

可复用的界面单元：选项块在 items.py，标题/分隔线在 texts.py，滚动区在 scrolls.py。
各文件用 `from ._init import *` 拿公共导入，不各自再写一遍。
块自己不进 scroll_layout，由页面调用 add() 挂上去。
"""

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScrollBar, QSlider, QStyle, QStyleOptionComboBox, QStyleOptionSlider, QVBoxLayout, QWidget

from ..path_utils import getPath

from ..bus import bus
from ..utils import change_color
