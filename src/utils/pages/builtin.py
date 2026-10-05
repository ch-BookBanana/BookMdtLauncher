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

内置界面：声明扩展点契约 + import 各页面模块完成登记。

各页面模块在自己末尾往扩展点登记条目（见 pages/start.py 末尾），所以
「有哪些内置页面」的出处在这里，而不在 main.py —— main.py 只 import 本模块
触发登记，再按 registry.entries(...) 构建，不认识任何一个页面类。

加一个内置页面 = 写页面模块（末尾自登记）+ 在下面加一行 import。
导航顺序由各条目的 order 决定，import 顺序不影响它。

为什么契约集中在这里声明
------------------------
声明是**静态契约**，必须在任何登记发生之前就位。原先各扩展点的 declare
散在 init_wid 里（构建期才执行），而插件是在 Main 构造期加载的 —— 那时界面
还没建，插件一 add 就撞上「扩展点 'core.setting.items' 尚未声明」。
集中到这里 = import 即声明，早于一切登记（内置的、插件的都在其后）。

顺带一个好处：所有扩展点长什么样，在一个文件里看得全。
"""

from ..registry import registry

# ─────────────────────────── 契约声明 ───────────────────────────

registry.declare("core.pages", registrant="core",
                 fields=("init", "title", "icon", "order", "default"),
                 required=("init", "title"),
                 built=("main", "btn"),
                 doc="主窗口左栏导航页（顺序由各条目的 order 决定）")

registry.declare("core.setting.pages", registrant="core.setting",
                 fields=("init", "title", "icon", "order"),
                 required=("init", "title", "icon"),
                 doc="设置页左栏的子页")

registry.declare("core.setting.items", registrant="core.setting",
                 fields=("init", "group", "order", "title", "spacing", "attr"),
                 required=("init", "group", "title"),
                 doc="设置子页里的条目（Title 分组标题 / Bool / Combo …）。"
                     "attr 可选：内置条目靠它绑回 self 上的老名字，插件用不着。"
                     "group='plugins' 的条目会被设置页单独归到末尾")

registry.declare("core.start.bottom", registrant="core.start",
                 fields=("init", "attr", "order"),
                 required=("init", "attr"),
                 doc="启动页左栏底部的按钮页（选择游戏 / 挂起…）")

registry.declare("core.download.tabs", registrant="core.download",
                 fields=("init", "title", "icon", "order"),
                 required=("init", "title", "icon"),
                 built=("main", "btn"),
                 doc="下载页左栏的页签")

registry.declare("core.download.sources", registrant="core.download",
                 fields=("init", "title", "icon", "order", "color"),
                 required=("init", "title", "icon"),
                 built=("main", "btn"),
                 doc="下载页顶部页签的游戏来源")

registry.declare("core.download.item.actions", registrant="core.download",
                 fields=("init", "title", "icon", "order", "attr"),
                 required=("init", "title", "icon"),
                 doc="下载列表项右侧的操作按钮（下载 / 仓库信息 / 链接）")

# 游戏管理浮层左栏的功能页（设置 / Mods / …）。项由各子页自己登记。
registry.declare("core.gameManager.pages", registrant="core.gameManager",
                 fields=("init", "title", "order"),
                 required=("init", "title"),
                 built=("main", "btn"),
                 doc="游戏管理浮层左栏的功能页（设置 / Mods / …）")

registry.declare("core.gameSettings.sections", registrant="core.gameSettings",
                 fields=("init", "attr", "order", "spacing"),
                 required=("init", "attr"),
                 doc="游戏管理页的区块（文件夹 / Java …）")

# ─────────────────────────── 内置条目登记 ───────────────────────────
# 下面这几行 import 会执行各页面模块末尾的 registry.add，
# 所以必须排在契约声明之后。

from . import start      # noqa: E402,F401
from . import download   # noqa: E402,F401
from . import game       # noqa: E402,F401
from . import setting    # noqa: E402,F401
from .fStack import gameSettings   # noqa: E402,F401  它的末尾往 core.gameManager.pages 登记
from .fStack import gameManager    # noqa: E402,F401
