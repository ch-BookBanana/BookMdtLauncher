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

流式布局：子项从左到右排，当前行放不下就换行（纯标准 Qt，不依赖业务）。
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    """一排按钮放不下时自己折行，而不是把父布局顶宽。

    为什么需要它
    ------------
    游戏管理页那排「改名 / 分组 / 导出 / 删除」是四颗定宽按钮（122×40 +
    8px 间距 ≈ 536px），而正文列最宽 600、窗口窄下来就只剩 500 出头。
    QHBoxLayout 不会折行：它把这一行算成「至少这么宽」，父级 QScrollArea
    又关掉了横条，于是最右边的按钮被窗口边缘直接切掉一截 —— 看得见字，
    但边框和右边距没了。

    换成流式之后，这一行的**最小宽度**只是一颗按钮的宽度，正文列可以缩到
    窗口那么窄；宽度不够时第四颗按钮落到第二行，行高由 heightForWidth
    报到外层布局，滚动区照常滚。

    实现照 Qt 官方的 FlowLayout 例子：hasHeightForWidth + heightForWidth，
    只在 test_only=False 时真的 setGeometry，量高度和摆位置共用同一段计算。
    """

    def __init__(self, parent=None, spacing=8, margins=(0, 0, 0, 0)):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(*margins)

    # ── QLayout 要求的四件套 ──

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    # ── 尺寸 ──

    def expandingDirections(self):
        # 两个方向都不主动吃掉多余空间：多出来的宽度由外层布局给，
        # 折行判断看的是自己拿到的 rect 宽度。
        return Qt.Orientations()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def sizeHint(self):
        # 与 Qt 例子一致：首选尺寸就是「一颗按钮那么大」。
        # 报成整排宽度的话，外层布局会按整排去要空间，折行永远不会发生。
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # ── 摆放 ──

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def _do_layout(self, rect, test_only):
        """按 rect 的宽度把子项摆开，返回内容总高。

        test_only=True 只算高度不落几何 —— heightForWidth 会被布局反复调用，
        真去 setGeometry 会在同一帧里把按钮挪来挪去。
        """
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        gap = self.spacing()
        x, y, line = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            # 放不下且本行已经有东西 → 换行。line == 0 时即使一颗按钮比整行
            # 还宽也硬放（否则会无限换行），超出的部分交给父级裁。
            if line and x + hint.width() > area.x() + area.width():
                x = area.x()
                y += line + gap
                line = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + gap
            line = max(line, hint.height())
        return y + line - rect.y() + m.bottom()
