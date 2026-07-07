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


def getPath(relative_path):
    """获取资源的绝对路径，兼容开发环境和 PyInstaller 打包后的环境
    规则：
      - 以 src 开头的路径 → PyInstaller 释放目录 (_MEIPASS)
      - 其他路径（如 BML/） → exe 同目录
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if relative_path.startswith('src'):
            base_path = getattr(sys, '_MEIPASS', exe_dir)
        else:
            base_path = exe_dir
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)
