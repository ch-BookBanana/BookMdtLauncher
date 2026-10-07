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

设置分组的容器：一行标题 + 它容纳的那几项。

为什么要有容器
--------------
原先分组标题是**混在条目里**的一条 Title（order 正好排在哪两项之间，它就算哪一组的
标题），于是「这个标题管着哪几项」只能靠 order 去猜，插件想往某一组里加东西也无处
可依。现在容器是容器、条目是条目：

    core.setting.sections   容器：key / title / order（本模块的 Section 是内置那个）
    core.setting.items      条目：用 section 字段指向容器 key

容器从注册表来，所以「长什么样」也是可换的：想要能折叠的、带说明文字的，换一个
容器类登记上去就行，条目一条都不用动。
"""

from ._init import *                                        # noqa: F401,F403
from .texts import Title
from ..registry import Box


class Section(QWidget):
    """一个设置分组：标题那一行（Title）+ 下面容纳的条目。

    条目由设置页按 section 字段挑好、连 Box 的本次上下文一起递进来；这里只负责
    「按条目自己的 init 建出来、摆进 body」。容器不替条目决定它长什么样 ——
    那是条目自己的事（Bool / Combo / 插件自绘的控件都行）。

    摆法照 Scroll.add 的规矩：spacing 是加在**这一项上方**的空隙。
    """

    def __init__(self, page=None, title=None, items=(), fields=None):
        super().__init__()
        self.page = page
        self.title_ = title
        self.fields = fields or {}
        self.wids = []
        self.init_wid()
        for e in items:
            wid = e.init(Box(parent=page, entry=e))
            f = self.fields.get(e.key, {})
            if f.get("attr"):
                setattr(page, f["attr"], wid)
            self.add_wid(wid, f.get("spacing", 0))

    def init_wid(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignTop)

        self.title = Title(self, self.title_)
        self.layout.addWidget(self.title, 0)

        self.body = QWidget()
        self.layout.addWidget(self.body, 1)
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(0, 0, 0, 0)
        self.body_l.setSpacing(0)
        self.body_l.setAlignment(Qt.AlignTop)

    def add_wid(self, wid, spacing=0):
        """往容器里再挂一个控件（页面手写的复合行也走这儿），返回它。"""
        self.wids.append(wid)
        if spacing:
            self.body_l.addSpacing(spacing)
        self.body_l.addWidget(wid, 0)
        return wid
