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

给插件用的现成控件 —— 和内置界面是同一批。

为什么建议直接用它们
--------------------
插件当然可以自己写 QWidget，但主题切换（lighting）与语言热切换（langing）
是靠这两个钩子挂在总线上的，自己写就得手动补；用这里的控件就自动有了，
而且外观、间距、配色跟内置页面保持一致。

控件构造签名（各不一样，按类看）
--------------------------------
    Bool / Combo / Slider / Title / Line   (parent, text=None)
        这几个是标准的「设置项」控件：`self.add_setting(name, cls, title=…)`
        会把 (parent, 语言键) 拼好传进来，主题与语言由控件自己跟总线。

    值型控件（Bool / Combo / Slider）实现同一套接口：value() / set_value(v) /
    refresh()，外加 push 信号。所以「控件 ↔ 存储」这条线不认具体类：

        from BMLCore import Widgets
        Widgets.bind(Widgets.Bool(ctx.parent, "开关"), entry)      # v3 设置条目
        Widgets.bind(Widgets.Bool(ctx.parent, "开关"),
                     Widgets.MappingSource(events.settings, "theme"))   # 宿主设置

    Title / Line 是装饰（分组标题、分隔线），不参与取值，也没有这套接口。

    Section(page, title, items, fields=None)
        设置页里的一个分组容器（`registrar("core/setting/sections").new` 的构建函数用它，
        `ctx.items` 是这一组容纳的条目）。

    Scroll(parent, horizontal=False, …)
        滚动区，宿主内部用得多；它**不是**设置项控件（签名对不上），
        别交给 add_setting。
"""

from ..utils.options.base import MappingSource, SettingItem, bind
from ..utils.options.items import Bool, Combo, Slider
from ..utils.options.scrolls import Scroll
from ..utils.options.sections import Section
from ..utils.options.texts import Line, Title

def control(ctx, cls=None, **kwargs):
    """在 build 工厂里用：建控件并接到条目上。

        section.add("probe", default=True,
                    build=lambda ctx: Widgets.control(ctx, Widgets.Bool))

    ctx 是建控件时传进来的 Box（ctx.parent 挂载父控件、ctx.title 语言键、
    ctx.entry 就是这条设置项本身）；cls 必须是实现 value/set_value/refresh 的
    设置项控件。返回已经接好线的控件。
    """
    widget = (cls or Bool)(ctx.parent, ctx.title, **kwargs)
    return bind(widget, ctx.entry)


__all__ = ["Bool", "Combo", "Slider", "Scroll", "Section", "Title", "Line",
           "bind", "control", "SettingItem", "MappingSource"]
