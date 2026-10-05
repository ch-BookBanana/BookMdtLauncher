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

from ._init import *


class Scroll(QScrollArea):
    """自带浮条的滚动区。

    原生条在 qss 里做不出「贴着内容边、5px 宽、需要时才露」的样子（qss 管不到它的
    尺寸策略，Qt 还会按样式给它算宽度），所以统一把原生条藏掉，另挂一条浮条，
    位置在 resizeEvent 里按自身尺寸算。滚动本身还是走原生条，浮条只是它的门面。

    内容容器放在 self.main，往里加东西用 self.add()（加完顺手刷一次浮条显隐）；
    容器布局是 self.scroll_layout，需要精细操作时直接用它。

    horizontal=True 换成横向区（浮条贴底），滚轮自动转为横向滚动，
    再要「空白处按住拖动」就传 drag=True。
    虚拟列表这类自己 setGeometry 摆子控件的，传 layout=False 别给它套布局。
    """

    def __init__(self, parent=None, horizontal=False, margins=(0, 0, 0, 0),
                 spacing=0, align=None, content=None, content_align=None,
                 bar_size=5, layout=True, drag=False):
        super().__init__(parent)
        self.horizontal = horizontal
        self._bar_size = bar_size
        self._drag = drag
        self._drag_pos = None

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        # 原生条一律藏起来，位置让给自己的浮条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if content_align is not None:
            self.setAlignment(content_align)

        self.main = QWidget() if content is None else content
        self.scroll_layout = None
        if layout:
            box = QHBoxLayout(self.main) if horizontal else QVBoxLayout(self.main)
            box.setContentsMargins(*margins)
            box.setSpacing(spacing)
            if align is None:
                align = (Qt.AlignLeft | Qt.AlignTop) if horizontal else Qt.AlignTop
            box.setAlignment(align)
            self.scroll_layout = box
        self.setWidget(self.main)

        # 浮条 ↔ 原生条 双向同步（浮条拖动改原生条，原生条滚动回写浮条）
        bar = self.bar()
        self.scroll_slider = QScrollBar(Qt.Horizontal if horizontal else Qt.Vertical, self)
        self.scroll_slider.valueChanged.connect(bar.setValue)
        bar.rangeChanged.connect(self.scroll_slider.setRange)
        bar.valueChanged.connect(self.scroll_slider.setValue)

        if drag:
            self.viewport().installEventFilter(self)

    def bar(self):
        """浮条背后真正的滚动实体（原生条）。"""
        return self.horizontalScrollBar() if self.horizontal else self.verticalScrollBar()

    def add(self, wid, spacing=0):
        """往内容里挂一个控件，spacing 是加在它上方的空隙。"""
        if self.scroll_layout is None:
            raise RuntimeError("Scroll(layout=False) 没有内容布局，子控件请自己定位到 self.main")
        if spacing:
            self.scroll_layout.addSpacing(spacing)
        self.scroll_layout.addWidget(wid)
        self.barShow()
        return wid

    def barShow(self):
        """内容没溢出就把浮条收起来。"""
        bar = self.bar()
        self.scroll_slider.setVisible(bar.maximum() > bar.minimum())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = self._bar_size
        if self.horizontal:
            self.scroll_slider.setGeometry(0, self.height() - size, self.width(), size)
        else:
            self.scroll_slider.setGeometry(self.width() - size, 0, size, self.height())
        self.barShow()

    def showEvent(self, event):
        super().showEvent(event)
        # 显示前尺寸可能是旧的，浮条显隐要按当前溢出情况重算
        self.barShow()

    def wheelEvent(self, event):
        if not self.horizontal:
            return super().wheelEvent(event)
        # 横向区：竖着滚滚轮也当横向滚，省得去够底部那条细条
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar = self.bar()
        bar.setValue(bar.value() - delta)
        event.accept()

    def eventFilter(self, obj, event):
        if self._drag and obj is self.viewport():
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.pos()
            elif event.type() == QEvent.MouseMove and self._drag_pos is not None:
                bar = self.bar()
                bar.setValue(bar.value() - (event.pos().x() - self._drag_pos.x()))
                self._drag_pos = event.pos()
                return True
            elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                self._drag_pos = None
        return super().eventFilter(obj, event)
