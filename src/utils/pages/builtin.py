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

内置界面：声明扩展点契约 + 调用各页面模块的 register()。

各页面模块导出顶层 register()，本文件逐个调（见文件末尾）。import 本身
不登记任何东西，所以「有哪些内置条目」在这里一眼看得全，不必翻到各模块
末尾去数。main.py 只 import 本模块，再按 registry.entries(...) 构建，
不认识任何一个页面类。

加一个内置页面 = 写页面模块（带 register()）+ 在末尾加两行（import + 调）。
导航顺序由各条目的 order 决定，调用顺序不影响它。

目录按「这一页活在哪一层」分
----------------------------
    *.py            主窗口左栏的导航页（core.pages）
    fOverlay/       叠加层：盖在窗口上、带遮罩居中的卡片／面板
    fStack/         浮层栈：整页导航，一页压一页
    downloads/      下载页内部：各下载源的页签

文件夹不是摆设：浮层页面登记 core.overlays 时用 layer 字段声明自己在哪一层
（'overlay' / 'stack'），open_overlay 照它发请求。放在哪一层看得见、也不必让
每个调用方记住该发哪个信号。

为什么契约集中在这里声明
------------------------
声明是**静态契约**，必须在任何登记发生之前就位。原先各扩展点的 declare
散在 init_wid 里（构建期才执行），而插件是在 Main 构造期加载的 —— 那时界面
还没建，插件一 add 就撞上「扩展点 'core.setting.items' 尚未声明」。
集中到这里 = 本模块一被 import 就声明完，早于一切登记（内置的、插件的都在其后）。

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

registry.declare("core.qss", registrant="core",
                 fields=("qss", "theme", "order"),
                 required=("qss",),
                 doc="追加到全局样式表末尾的 css 片段。theme: None = 两套主题都加，"
                     "False = 只在深色，True = 只在浅色。片段排在主题文件之后，"
                     "同名选择器以它为准 —— 扩展能盖内置样式，不必改主题文件；"
                     "换主题时会重新收一遍，不用自己监听。")

registry.declare("core.tray.menu", registrant="core",
                 fields=("init", "title", "order"),
                 required=("init", "title"),
                 doc="系统托盘右键菜单里的一项：init(Box) 返回 QAction。"
                     "title 是语言键，语言切换时托盘会照它重设文案。")

registry.declare("core.setting.sections", registrant="core.setting",
                 fields=("init", "title", "order", "spacing", "attr"),
                 required=("init", "title"),
                 doc="设置子页里的分组容器（标题 + 它容纳的条目）。"
                     "容器由 init 建（Box 的本次上下文里带 items：这一组的条目表），"
                     "所以「分组长什么样」也是可换的。"
                     "attr 可选：设置页要往这一组里补控件时，用它在页面上取容器。")

registry.declare("core.setting.items", registrant="core.setting",
                 fields=("init", "section", "order", "title", "spacing", "attr"),
                 required=("init", "section", "title"),
                 doc="设置子页里的条目（Bool / Combo / 插件自绘的控件…），"
                     "section 指向它所属的容器 key（core.setting.sections 里的条目）。"
                     "attr 可选：内置条目靠它绑回页面上的老名字，插件用不着。")

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
# 浮层页面：盖在窗口上的整页界面，由 FloatingStack 承载。
# 与 core.pages 的区别是它不进左栏、而是弹出来；条目形态一样。
registry.declare("core.overlays", registrant="core",
                 fields=("init", "title", "order", "layer"),
                 required=("init", "title"),
                 doc="浮层页面（盖在窗口上的整页界面）。"
                     "layer 决定它在哪一层被打开，也就是发哪个请求："
                     "'overlay'（缺省）= 叠加层，带遮罩、内容居中，见 pages/fOverlay/；"
                     "'stack' = 浮层栈，整页导航、一页压一页，见 pages/fStack/。"
                     "发错请求的表现是「点了没反应」，所以别让调用方自己记着。")

registry.declare("core.gameManager.pages", registrant="core.gameManager",
                 fields=("init", "title", "icon", "order"),
                 required=("init", "title"),
                 built=("main", "btn"),
                 doc="游戏管理浮层左栏的功能页（设置 / Mods / …）。icon 可省")

registry.declare("core.gameSettings.sections", registrant="core.gameSettings",
                 fields=("init", "attr", "order", "spacing"),
                 required=("init", "attr"),
                 doc="游戏管理页的区块（文件夹 / Java …）")

# ─────────────────────────── 内置条目登记 ───────────────────────────
# 每个页面模块导出顶层 register()，这里逐个调 —— import 本身不登记。
# 「有哪些内置条目」于是全在这一个文件里看得见，不必翻到各模块末尾去数；
# 调用顺序必须排在契约声明之后（register 里的 add 会校验契约）。

from . import start                # noqa: E402,F401
from . import download             # noqa: E402,F401
from . import game                 # noqa: E402,F401
from . import setting              # noqa: E402,F401
from .fOverlay import githubSetting    # noqa: E402,F401
from .fStack import dlList             # noqa: E402,F401
from .downloads import game as _download_sources   # noqa: E402,F401
from .fStack import gameManager    # noqa: E402,F401
# 关闭询问浮层住在基层（settings.py）—— 它问的就是基层那个字段，控件跟着字段
# 走；登记仍然由这里统一叫（register 见那个文件的第二级）。
from ..settings import register as _register_close_ask    # noqa: E402,F401

start.register()                   # core.start.bottom（底部按钮页）
download.register()                # core.download.tabs（左栏页签）
setting.register()                 # core.setting.pages + core.setting.items
githubSetting.register()           # core.overlays：GitHub 设置页（叠加层）
dlList.register()                  # core.overlays：下载列表（浮层栈）
_download_sources.register()       # core.download.sources（三个下载源）
gameManager.register()             # core.overlays + 管理浮层的功能页与区块
_register_close_ask()              # core.overlays：关闭询问（叠加层）

