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

控件构造签名统一为 (parent, root, title)：root 现在还没从控件里削掉（那是
宿主内部下一批的活），但插件不必关心 —— 用 Plugin.add_setting(cls) 就行，
参数由宿主拼。
"""

from ..utils.options.items import Bool, Combo, Slider
from ..utils.options.scrolls import Scroll
from ..utils.options.texts import Line, Title

__all__ = ["Bool", "Combo", "Slider", "Scroll", "Title", "Line"]
