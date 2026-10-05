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

内置资源路径表 —— src/assets 下所有图标的唯一出处。

为什么要有这个文件：
  * 同一个图标此前散在多处各写一遍字面量（tips.png 5 处、close.png 3 处、
    intro.png 3 处），改名/挪目录时必然漏改；
  * 路径拼错不会当场报错 —— change_color 拿到空 QPixmap 不抛异常，
    只会在界面上变成一个看不见的图标，很难发现；
  * 散落的字面量看不出「这个项目到底有哪些资源」，也没法统一自检。

约定：
  * 值一律是「相对项目根 + src/ 前缀」的字符串，交给 getPath() 解析
    （path_utils 靠 startswith("src") 区分「打包内置资源」与「exe 旁用户数据」，
    所以这个前缀不能省）；
  * 本模块只放数据，不 import 任何项目模块 —— 任何层引用它都不会引入依赖，
    也不会把业务链拖进来；
  * 需要一次性枚举（自检 / 打包核对）用 all_paths()。
"""

__all__ = [
    # 页面按钮
    "BTN_START", "BTN_DOWNLOAD", "BTN_GAME", "BTN_SETTING",
    # 窗口控制
    "TBT_CLOSE", "TBT_MINIMIZE", "TBT_MAXIMIZE", "TBT_MAXIMIZE2",
    # 动作图标
    "ACT_TIPS", "ACT_INTRO", "ACT_ON", "ACT_OFF", "ACT_EYE", "ACT_EYE_OFF", "ACT_DL_LIST", "ACT_UNITS",
    # 导航
    "NAV_MENU", "NAV_LINK", "NAV_BACK",
    # 文件
    "FILE_FOLDER", "FILE_IMAGE", "FILE_GENERIC",
    # 品牌 / 背景
    "BRAND_GITHUB", "BACKG_MAIN",
    # 应用图标
    "ICON_APP_DARK", "ICON_APP_LIGHT",
    # 下载源图标
    "ICON_MDT", "ICON_MDTX", "ICON_MDTARC",
    # 目录与工具
    "ASSETS_DIR", "app_icon", "all_paths",
]

# ─────────────────────────── 页面按钮 src/assets/buttons/ ───────────────────────────
BTN_START    = "src/assets/buttons/start.png"
BTN_DOWNLOAD = "src/assets/buttons/download.png"
BTN_GAME     = "src/assets/buttons/game.png"
BTN_SETTING  = "src/assets/buttons/setting.png"

# ─────────────────────────── 窗口控制 src/assets/tribtns/ ───────────────────────────
TBT_CLOSE     = "src/assets/tribtns/close.png"
TBT_MINIMIZE  = "src/assets/tribtns/minimize.png"
TBT_MAXIMIZE  = "src/assets/tribtns/maximize.png"
TBT_MAXIMIZE2 = "src/assets/tribtns/maximize2.png"

# ─────────────────────────── 动作图标 src/assets/actions/ ───────────────────────────
ACT_TIPS     = "src/assets/actions/tips.png"
ACT_INTRO    = "src/assets/actions/intro.png"
ACT_ON       = "src/assets/actions/btn_on.png"
ACT_OFF      = "src/assets/actions/btn_off.png"
ACT_EYE      = "src/assets/actions/eye.png"
ACT_EYE_OFF  = "src/assets/actions/eye-off.png"
ACT_DL_LIST  = "src/assets/actions/dl_list.png"
ACT_UNITS    = "src/assets/actions/units.png"

# ─────────────────────────── 导航 src/assets/nav/ ───────────────────────────
NAV_MENU = "src/assets/nav/menu.png"
NAV_LINK = "src/assets/nav/link.png"
NAV_BACK = "src/assets/nav/back.png"

# ─────────────────────────── 文件 src/assets/files/ ───────────────────────────
FILE_FOLDER  = "src/assets/files/folder.png"
FILE_IMAGE   = "src/assets/files/file-image.png"
FILE_GENERIC = "src/assets/files/file.png"

# ─────────────────────────── 品牌 / 背景 ───────────────────────────
BRAND_GITHUB = "src/assets/brands/github.png"
BACKG_MAIN   = "src/assets/backg/1.png"

# ─────────────────────────── 应用图标 src/assets/icons/ ───────────────────────────
# 标题栏 logo 与托盘图标：浅色主题配深色图，深色主题配浅色图（见 app_icon()）
ICON_APP_DARK  = "src/assets/icons/dark.png"
ICON_APP_LIGHT = "src/assets/icons/light.png"

# ─────────────────────────── 下载源图标 src/assets/icons/mdt/ ───────────────────────────
ICON_MDT    = "src/assets/icons/mdt/mdt.png"
ICON_MDTX   = "src/assets/icons/mdt/mdtx.png"
ICON_MDTARC = "src/assets/icons/mdt/mdtarc.png"

# ─────────────────────────── 目录 ───────────────────────────
ASSETS_DIR = "src/assets"


def app_icon(light: bool) -> str:
    """标题栏 / 托盘的 logo 路径。

    图标本身是「深色图 / 浅色图」一对：light=True（浅色主题）要深色图才看得见，
    所以这里做了取反 —— 调用点不必各写一遍三元表达式。
    """
    return ICON_APP_DARK if light else ICON_APP_LIGHT


def all_paths() -> list:
    """枚举表中所有资源相对路径（供资源自检 / 打包核对使用）。

    只收集模块级的字符串常量，跳过目录与函数。
    """
    out = []
    for name in __all__:
        value = globals().get(name)
        if isinstance(value, str) and value != ASSETS_DIR:
            out.append(value)
    return sorted(set(out))
