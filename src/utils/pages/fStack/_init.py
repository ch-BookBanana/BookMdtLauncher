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
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ...utils import change_color


class FloatingStack(QWidget):
    def __init__(self,parent=None,root=None):
        super().__init__(parent)
        self.parent = parent
        self.root = root
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.init_wid()
        self.refresh()

    def init_wid(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignTop)

        self.line = QWidget()
        self.line.setProperty("wid","line")
        self.line.setFixedHeight(1)
        self.layout.addWidget(self.line)

        self.l2w = QWidget()
        self.layout.addWidget(self.l2w,1)

        self.l2 = QHBoxLayout(self.l2w)
        self.l2.setContentsMargins(0,0,0,0)
        self.l2.setSpacing(0)
        self.l2.setAlignment(Qt.AlignLeft)

        self.left = self.Left(self,self.root)
        self.l2.addWidget(self.left,0)

        self.line2 = QWidget()
        self.line2.setProperty("wid","line")
        self.line2.setFixedWidth(1)
        self.l2.addWidget(self.line2,0)

        self.main = self.Main(self,self.root)
        self.l2.addWidget(self.main,1)

    def refresh(self):
        # 栈空时隐藏整个浮层，否则显示并提层
        if self.main.count() <= 0:
            self.hide()
        else:
            self.show()
        self.left.refresh()

    def add_page(self,wid):
        # 入栈：添加页面并切换到栈顶（已在栈中先移出，支持 deletable=False 后复用）
        if self.main.indexOf(wid) >= 0:
            self.main.removeWidget(wid)
        self.main.addWidget(wid)
        self.main.setCurrentWidget(wid)
        def close_page():
            self.pop_page(wid)
        wid.close_page = close_page
        self.refresh()

    def pop_page(self, wid=None, deletable=True):
        # 出栈：移除指定页面（缺省为栈顶）；deletable=True 销毁，False 仅移出保留实例
        if self.main.count() <= 0:
            return
        if wid is None:
            wid = self.main.currentWidget()
        index = self.main.indexOf(wid)
        if index < 0:
            return
        self.main.removeWidget(wid)
        wid.hide()
        on_close = getattr(wid, "on_close", None)
        if on_close is not None:
            on_close()
        if deletable:
            wid.deleteLater()
        if self.main.count() > 0:
            self.main.setCurrentIndex(self.main.count() - 1)
        self.refresh()

    def clear(self, deletable=True):
        # 清空栈；deletable=True 销毁页面，False 仅移出保留实例
        while self.main.count() > 0:
            wid = self.main.widget(0)
            self.main.removeWidget(wid)
            wid.hide()
            on_close = getattr(wid, "on_close", None)
            if on_close is not None:
                on_close()
            if deletable:
                wid.deleteLater()
        self.refresh()

    class Left(QWidget):
        def __init__(self,parent=None,root=None):
            super().__init__(parent)
            self.parent = parent
            self.root = root
            self.setFixedWidth(40)
            self.init_wid()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(5,5,5,5)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

            # 内置退出按钮（左箭头，返回上一页）
            self.back = self.NavBtn(self, self.root, "src/assets/nav/back.png", "text.return", self.parent.pop_page)
            self.layout.addWidget(self.back,0,Qt.AlignHCenter)

            # 清空整个栈按钮（叉号）
            self.btn_close = self.NavBtn(self, self.root, "src/assets/tribtns/close.png", "wid.top.close", self.parent.clear)
            self.layout.addWidget(self.btn_close,0,Qt.AlignHCenter)

        def refresh(self):
            # 栈空时禁用两个按钮
            enabled = self.parent.main.count() > 0
            self.back.setEnabled(enabled)
            self.btn_close.setEnabled(enabled)

        class NavBtn(QPushButton):
            """浮动栈导航按钮：Back/Close 通用（图标、tooltip、回调参数化）"""
            def __init__(self, parent=None, root=None, icon=None, tip_key=None, callback=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.icon_ = icon
                self.tip_key_ = tip_key
                self.setFixedSize(30,30)
                self.setAttribute(Qt.WA_StyledBackground, False)
                self.setProperty("wid","tbtn")
                self.langing()
                self.lighting(self.root.settings["theme"])
                if callback is not None:
                    # clicked 自带 checked(bool) 参数，必须丢弃：
                    # 否则会顶替 pop_page(wid) 的 wid 或 clear(deletable) 的 deletable
                    self.clicked.connect(lambda: callback())

            def lighting(self, light: bool):
                color = QColor(120,120,120) if light else QColor(200,200,200)
                logo = change_color(self.icon_, color)
                self.setIcon(QIcon(logo.pixmap(48,48)))

            def langing(self):
                self.setToolTip(self.root.langer.get(self.tip_key_))

    class Main(QStackedWidget):
        def __init__(self,parent=None,root=None):
            super().__init__(parent)
            self.parent = parent
            self.root = root
            self.init_wid()

        def init_wid(self):
            # QStackedWidget 内部自带 QStackedLayout 管理页面，无需（也不能）再设置 layout
            pass
