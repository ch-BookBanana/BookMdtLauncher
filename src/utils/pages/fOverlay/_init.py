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
from PySide6.QtWidgets import QWidget, QGridLayout

from ...events import events


class FloatingOverlay(QWidget):
    """叠加形悬浮窗：注册方式与 FloatingStack 相同（add_page/pop_page/clear + close_page 闭包），
    但页面为叠加显示（后进者盖在上层、互不销毁），样式参照 GithubSetting（全屏半透明遮罩+居中）。"""
    def __init__(self,parent=None,root=None):
        super().__init__(parent)
        self.parent = parent
        self.root = root
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid_", "_window.overlay")
        self.setStyleSheet('QWidget[wid_="_window.overlay"]{background-color: rgba(0,0,0,0.5);}')
        self._pages = []
        self.init_wid()
        self.hide()

    def init_wid(self):
        # 所有页面置于同一格子：重叠显示、居中，后添加者在上层
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter)

    def add_page(self,wid):
        # 入叠：添加页面并提到最上层（已在叠中则仅重新提到最上层，_pages 始终按层序排列）
        if wid in self._pages:
            self._pages.remove(wid)
        else:
            self.layout.addWidget(wid,0,0,Qt.AlignCenter)
            # 页面（小窗口）截断鼠标事件冒泡：点其空白处不应传到遮罩触发窗口拖动
            wid.setAttribute(Qt.WA_NoMousePropagation, True)
            def close_page():
                self.pop_page(wid)
            wid.close_page = close_page
        self._pages.append(wid)
        wid.show()
        wid.raise_()
        self.show()

    def pop_page(self, wid=None, deletable=True):
        # 出叠：移除指定页面（缺省为最上层），露出下层页面；deletable=True 销毁，False 仅移出保留实例
        if wid is None:
            wid = self._pages[-1] if self._pages else None
        if wid is None or wid not in self._pages:
            return
        self._pages.remove(wid)
        self.layout.removeWidget(wid)
        wid.hide()
        on_close = getattr(wid, "on_close", None)
        if on_close is not None:
            on_close()
        if deletable:
            wid.deleteLater()
        if self._pages:
            self._pages[-1].raise_()
        else:
            self.hide()

    def clear(self, deletable=True):
        # 清空全部叠加页面；deletable=True 销毁页面，False 仅移出保留实例
        while self._pages:
            wid = self._pages.pop(0)
            self.layout.removeWidget(wid)
            wid.hide()
            on_close = getattr(wid, "on_close", None)
            if on_close is not None:
                on_close()
            if deletable:
                wid.deleteLater()
        self.hide()

    def showEvent(self, event):
        # 显示时提层，盖过 floatingStack 等覆盖控件
        super().showEvent(event)
        self.raise_()

    def mousePressEvent(self, event):
        # 灰色遮罩区域按下：拖动无边框窗口（与 Left.Logo 共用 Window 的拖动逻辑）。
        # 走事件而不是直接点 window：遮罩不需要知道窗口长什么样，谁想接管拖动谁订阅。
        events.emit("dragRequested", "begin", event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        events.emit("dragRequested", "move", event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        events.emit("dragRequested", "end", event)
        super().mouseReleaseEvent(event)