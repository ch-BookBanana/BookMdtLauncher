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

import os
import sys


def _is_nuitka():
    """检测是否运行在 Nuitka 编译产物中。

    Nuitka 不提供 sys.frozen（不像 PyInstaller），而是向每个编译模块
    注入模块级全局 __compiled__（README 官方的运行时检测方式）。
    """
    try:
        __compiled__  # noqa: F821  Nuitka 注入的模块级全局
        return True
    except NameError:
        return False


# 当前正在加载的插件目录，由 pluginLoader 在 setup 期间设置。
# 插件资源统一写 getPath("${plugin}/assets/xxx.png") —— 不写死自己叫什么、
# 也不写死装在哪个位置，换个 id 或换个安装目录都不用改代码。
_PLUGIN_DIR = None


def set_plugin_dir(path):
    """加载器进出插件上下文时调用（退出传 None）。"""
    global _PLUGIN_DIR
    _PLUGIN_DIR = path


def getPath(relative_path):
    """获取资源的绝对路径，兼容开发环境 / PyInstaller / Nuitka 打包环境

    路径语义在三种环境下保持一致：
      - 以 src 开头的路径（图标/语言/json/qss 等内置资源） → 打包解压目录
      - 其他路径（如 BML/ 用户数据）                       → exe 同目录

    各环境定位方式：
      - 开发环境    ：__file__ 上溯到项目根
      - PyInstaller ：sys.frozen → _MEIPASS(内置资源) / dirname(sys.executable)(exe旁)
      - Nuitka onefile：sys.argv[0]=原始exe路径(已绝对化)，__file__=解压临时目录
      - Nuitka standalone：二者同在 dist 目录，逻辑可复用
    """
    norm = str(relative_path).replace("\\", "/")
    if norm == "${plugin}" or norm.startswith("${plugin}/"):
        if _PLUGIN_DIR is None:
            raise RuntimeError(
                "getPath('${plugin}/…') 只在插件加载期间可用（setup 里）。"
                "运行期才要取的资源，请在 setup 里先把路径取好再登记。")
        tail = norm[len("${plugin}"):].strip("/")
        return os.path.join(_PLUGIN_DIR, *tail.split("/")) if tail else _PLUGIN_DIR

    if _is_nuitka():
        if relative_path.startswith('src'):
            # 内置资源位于解压目录/二进制目录。Nuitka 的 __file__ 为
            # runtime 引用（--file-reference-choice=runtime 默认），包结构
            # 保持，src/utils/path_utils.py 三次上溯即数据根（同开发模式）。
            base_path = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        else:
            # BML/ 等 exe 旁用户数据：必须用 sys.argv[0] 定位。
            # onefile 下 sys.executable 指向解压临时位置，而 sys.argv[0]
            # 保持为原始 exe 的绝对路径（README 明确该行为）。
            base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.join(base_path, relative_path)

    if getattr(sys, 'frozen', False):
        # PyInstaller
        exe_dir = os.path.dirname(sys.executable)
        if relative_path.startswith('src'):
            base_path = getattr(sys, '_MEIPASS', exe_dir)
        else:
            base_path = exe_dir
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)
