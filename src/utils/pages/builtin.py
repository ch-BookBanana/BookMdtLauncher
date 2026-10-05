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

内置页面：import 本模块 = 完成内置页面的登记。

各页面模块在自己末尾往 core.pages 登记条目（见 pages/start.py 末尾），所以
「有哪些内置页面」这件事的出处在这里，而不在 main.py —— main.py 只 import
本模块触发登记，然后按 registry.entries("core.pages") 构建，不认识任何一个
页面类。

加一个内置页面 = 写一个页面模块（末尾自登记）+ 在下面加一行 import。
导航顺序由各条目自己的 order 决定，import 顺序不影响它。
"""

from ..registry import registry

# core.pages 的契约在这里声明：谁提供条目谁声明它。
# 必须排在下面那几行 import 之前 —— 那些模块 import 时就会立刻往表里 add，
# 扩展点还没声明的话 add 会直接报错。
registry.declare("core.pages", registrant="core",
                 fields=("init", "title", "icon", "order", "default"),
                 required=("init", "title"),
                 built=("main", "btn"),
                 doc="主窗口左栏导航页（顺序由各条目的 order 决定）")

from . import start      # noqa: E402,F401
from . import download   # noqa: E402,F401
from . import game       # noqa: E402,F401
from . import setting    # noqa: E402,F401
