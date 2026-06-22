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

import os, zipfile
from .path_utils import getPath

def _parse_simple_config_typed(content: str) -> dict:
    """解析 version.properties 内容为字典"""
    config = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            val_str = value.strip()
            # 尝试转 int
            if val_str.lstrip('-').isdigit():
                val = int(val_str)
            # 尝试转 float
            elif val_str.replace('.', '', 1).lstrip('-').isdigit() and val_str.count('.') <= 1:
                val = float(val_str)
            else:
                val = val_str
            config[key] = val
    return config

class mdtScanner:
    # 根目录：.Mindustrys，相对于启动器脚本同级目录
    # 假设 .Mindustrys 位于启动器脚本同级目录
    base_dir = getPath("BML/.Mindustrys")

    @classmethod
    def _get_mdt_jar_path(cls, subdir_name):
        """返回子目录下 mdt.jar 的完整路径"""
        return os.path.join(cls.base_dir, subdir_name, "mdt.jar")

    @classmethod
    def isMdtFile(cls, subdir_name):
        """检查子目录下的 mdt.jar 是否有效（存在且包含 version.properties）"""
        jar_path = cls._get_mdt_jar_path(subdir_name)
        if not os.path.isfile(jar_path):
            return False
        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                return 'version.properties' in zf.namelist()
        except zipfile.BadZipFile:
            return False

    @classmethod
    def getMdtMsg(cls, subdir_name):
        """返回 version.properties 解析后的字典，失败返回 None"""
        if not cls.isMdtFile(subdir_name):
            return None
        jar_path = cls._get_mdt_jar_path(subdir_name)
        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                data = zf.read('version.properties').decode('utf-8')
                return _parse_simple_config_typed(data)
        except Exception:
            return None

    @classmethod
    def getMdts(cls):
        """返回 .Mindustrys 下所有有效副本目录的名称列表"""
        if not os.path.isdir(cls.base_dir):
            return []
        result = []
        for item in os.listdir(cls.base_dir):
            subdir = os.path.join(cls.base_dir, item)
            if os.path.isdir(subdir) and cls.isMdtFile(item):
                result.append(item)
        return result