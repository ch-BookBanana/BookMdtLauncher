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

import os, zipfile, hashlib, json
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

    # ---- 缓存系统 (mtime-based) ----
    _mdts_cache = None
    _mdts_cache_mtime = 0
    _mdt_msg_cache = {}       # {subdir_name: ((jar_mtime, png_mtime), data)}
    _base_dir_mtime = 0

    @classmethod
    def invalidate_cache(cls, game=None):
        """使缓存失效。game 为 None 时清空全部缓存，否则只清除指定游戏。"""
        if game:
            cls._mdt_msg_cache.pop(game, None)
        else:
            cls._mdts_cache = None
            cls._mdt_msg_cache.clear()

    @classmethod
    def preload_all(cls):
        """预加载所有游戏的版本信息到缓存，加速后续切换。"""
        for mdt in cls.getMdts():
            cls.getMdtMsg(mdt)

    @classmethod
    def _get_mdt_jar_path(cls, subdir_name):
        """返回子目录下 mdt.jar 的完整路径"""
        return os.path.join(cls.base_dir, subdir_name, "mdt.jar")

    @classmethod
    def _get_base_dir_mtime(cls):
        try:
            return os.path.getmtime(cls.base_dir)
        except OSError:
            return 0

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
        """返回 version.properties 解析后的字典，失败返回 None。
        使用 (jar_mtime, png_mtime, png_size) 作为缓存键，避免重复读取 zip。"""
        # 计算 png 路径与 mtime/size
        png = None
        png_mtime = 0
        png_size = 0
        try:
            png_path = getPath(f"BML/.Mindustrys/{subdir_name}/icon.png")
            if os.path.isfile(png_path):
                png = png_path
                png_mtime = os.path.getmtime(png_path)
                png_size = os.path.getsize(png_path)
        except OSError:
            png = getPath("src/assets/icons/mdt/mdt.png")

        jar_path = cls._get_mdt_jar_path(subdir_name)
        jar_mtime = 0
        try:
            jar_mtime = os.path.getmtime(jar_path)
        except OSError:
            pass

        cache_key = (jar_mtime, png_mtime, png_size)

        # 命中缓存（mtime 未变）
        if subdir_name in cls._mdt_msg_cache:
            cached_key, cached_data = cls._mdt_msg_cache[subdir_name]
            if cached_key == cache_key:
                return cached_data

        # 缓存未命中，读取 jar
        if not os.path.isfile(jar_path):
            cls._mdt_msg_cache.pop(subdir_name, None)
            return None

        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                if 'version.properties' not in zf.namelist():
                    cls._mdt_msg_cache.pop(subdir_name, None)
                    return None
                data = zf.read('version.properties').decode('utf-8')
                result = _parse_simple_config_typed(data) | {"icon": png}
                cls._mdt_msg_cache[subdir_name] = (cache_key, result)
                return result
        except Exception:
            cls._mdt_msg_cache.pop(subdir_name, None)
            return None

    @classmethod
    def getMdts(cls):
        """返回 .Mindustrys 下所有有效副本目录的名称列表。
        使用 base_dir 的 mtime 做缓存，目录未变化时直接返回缓存列表。"""
        current_mtime = cls._get_base_dir_mtime()
        if cls._mdts_cache is not None and cls._mdts_cache_mtime == current_mtime:
            return list(cls._mdts_cache)

        if not os.path.isdir(cls.base_dir):
            cls._mdts_cache = []
            cls._mdts_cache_mtime = current_mtime
            return []

        result = []
        for item in os.listdir(cls.base_dir):
            subdir = os.path.join(cls.base_dir, item)
            if os.path.isdir(subdir) and cls.isMdtFile(item):
                result.append(item)

        cls._mdts_cache = result
        cls._mdts_cache_mtime = current_mtime
        return list(result)