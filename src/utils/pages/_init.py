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

from PySide6.QtWidgets import QWidget

from ..bus import bus
from ..registry import registry


def _shell():
    """宿主体（三栏页容器）：left / main / right。

    页面此前靠 self.parent.parent.left 这类链去摸它 —— 那是「我的 parent 的
    parent 恰好有三栏容器」的假设：窗口内部一改层级就静默失效，而且报错位置
    离真正原因很远（三层同名 Main 里换一层，取到的就是另一个东西）。
    改从注册器按 key 取：页面认的是具名条目，不是窗口结构。
    """
    return registry.entry("core.shell", "core.shell.workspace").obj


class Leftw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(None)
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        _shell().left.addWidget(self)

    def resizeEvent(self, event):
        _shell().left.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width

       
class Mainw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        _shell().main.addWidget(self)

class Rightw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        _shell().right.addWidget(self)

    def resizeEvent(self, event):
        _shell().right.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width


class Page():
    """页面基类。

    子类只做两件事：
      1. 用类属性声明自己是谁（name 语言键 / icon 图标 / order 顺序 / default 默认页）；
      2. 实现 init_wid() 建自己的三栏内容。
    注册交给 @page("core.xxx") 装饰器（见 pages/start.py 末尾），
    装配方按注册表构建，不认识任何一个页面类。

    构造只需要一个 btn（导航按钮，装配方建好注入）；页容器从注册表取
    （见 _shell），不再顺着 parent 链猜。
    """

    # ── 元信息：子类覆盖 ──
    name = ""            # 语言键 —— 左栏按钮上的文案
    icon = ""            # 图标：内置用 resources 常量，插件用 "${plugin}/…"
    order = 100          # 左栏顺序
    default = False      # 是否是启动默认页（只有 core.pages 认这个）

    def __init__(self, btn=None):
        super().__init__()
        # 导航按钮由装配方（core.pages 的构建循环）建好后注入，点击也在那边接。
        # 这里原先是 self.root.window.left.pagebtns.add_btn(...) —— 一条从页面
        # 反向摸到主窗口、再摸进左栏按钮组的链，页面因此知道主窗口长什么样。
        self.btn = btn
        shell = _shell()
        self.id = len(shell.pages)
        shell.pages.append(self)
        shell.btns.append(self)
        self.init_wid()

    def changePage(self):
        shell = _shell()
        shell.left.setCurrentWidget(self.left)
        shell.main.setCurrentWidget(self.main)
        shell.right.setCurrentWidget(self.right)
        shell.left.setFixedWidth(self.left.width_)
        shell.right.setFixedWidth(self.right.width_)

    def click(self):
        self.btn.click()

    def init_wid(self):
        cls_left = self.Left if hasattr(self, 'Left') else Leftw
        self.left = cls_left(self)

        cls_main = self.Main if hasattr(self, 'Main') else Mainw
        self.main = cls_main(self)

        cls_right = self.Right if hasattr(self, 'Right') else Rightw
        self.right = cls_right(self)
