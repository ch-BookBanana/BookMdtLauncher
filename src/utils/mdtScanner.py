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

import os, zipfile, json
from .path_utils import getPath
from .javaScanner import javaScanner

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
    base_dir = getPath("BML/.Mindustrys")
    DEFAULT_ICON = "src/assets/icons/mdt/mdt.png"

    # ---- 缓存系统 (mtime-based) ----
    _mdts_cache = None
    _mdts_cache_mtime = 0
    _mdt_msg_cache = {}       # {subdir_name: (cache_key, data)}

    @classmethod
    def invalidate_cache(cls, game=None):
        """使缓存失效。game 为 None 时清空全部缓存，否则只清除指定游戏。"""
        if game:
            cls._mdt_msg_cache.pop(game, None)
        else:
            cls._mdts_cache = None
            cls._mdt_msg_cache.clear()

    @classmethod
    def _is_valid_image(cls, path):
        """通过文件头魔数检测是否为有效图片（PNG/JPEG/GIF/WebP）。"""
        if not path or not os.path.isfile(path):
            return False
        try:
            with open(path, "rb") as f:
                head = f.read(16)
            if head[:8] == b"\x89PNG\r\n\x1a\n":                 # PNG
                return True
            if head[:2] == b"\xff\xd8":                           # JPEG
                return True
            if head[:4] in (b"GIF8",):                             # GIF87a/GIF89a
                return True
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":     # WebP
                return True
            return False
        except OSError:
            return False

    @classmethod
    def _write_icon_path(cls, subdir_name, icon_path):
        """把 icon_path 写回 BML.json（保留其他字段），失败时静默。"""
        bml_path = getPath(f"BML/.Mindustrys/{subdir_name}/BML.json")
        try:
            with open(bml_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            data["icon_path"] = icon_path
            with open(bml_path, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
        except Exception:
            pass

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

        图标解析优先级：子目录 icon.png > BML.json 的 icon_path > 默认图标。
        icon_path 为 null 或指向无效图片时自动写回默认图标（DEFAULT_ICON）。
        使用 (jar_mtime, bml_mtime, png, png_mtime, png_size) 作为缓存键，
        避免重复读取 zip。"""
        # 计算 png 路径与 mtime/size
        png = None
        png_mtime = 0
        png_size = 0
        bml_mtime = 0
        bml_path = getPath(f"BML/.Mindustrys/{subdir_name}/BML.json")
        icon_path = None
        try:
            if os.path.isfile(bml_path):
                bml_mtime = os.path.getmtime(bml_path)
                with open(bml_path, "r", encoding="utf-8") as f:
                    icon_path = (json.load(f) or {}).get("icon_path")
        except (OSError, ValueError, TypeError):
            pass
        # icon_path 为 null/空 → 写回默认图标
        if not icon_path:
            icon_path = cls.DEFAULT_ICON
            cls._write_icon_path(subdir_name, icon_path)
            try:
                bml_mtime = os.path.getmtime(bml_path)
            except OSError:
                pass
        # icon_path 指向的文件不存在或非有效图片 → 写回默认图标
        cand = getPath(icon_path) if not os.path.isabs(icon_path) else icon_path
        if os.path.isfile(cand) and cls._is_valid_image(cand):
            png = cand
        else:
            cls._write_icon_path(subdir_name, cls.DEFAULT_ICON)
            png = getPath(cls.DEFAULT_ICON)
            try:
                bml_mtime = os.path.getmtime(bml_path)
            except OSError:
                pass
        # 子目录 icon.png 存在则优先
        try:
            png_path = getPath(f"BML/.Mindustrys/{subdir_name}/icon.png")
            if os.path.isfile(png_path):
                png = png_path
                png_mtime = os.path.getmtime(png_path)
                png_size = os.path.getsize(png_path)
        except OSError:
            pass
        if png is None:
            png = getPath(cls.DEFAULT_ICON)

        jar_path = cls._get_mdt_jar_path(subdir_name)
        jar_mtime = 0
        try:
            jar_mtime = os.path.getmtime(jar_path)
        except OSError:
            pass

        cache_key = (jar_mtime, bml_mtime, png, png_mtime, png_size)
        if subdir_name in cls._mdt_msg_cache:
            cached_key, cached_data = cls._mdt_msg_cache[subdir_name]
            if cached_key == cache_key:
                return cached_data
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
    def check_icons(cls):
        """随 getMdts 检索周期检查各游戏图标状态。

        - icon_path 为 null/空或指向无效图片 → 写回默认图标
        - BML.json 或 icon.png 变化 → 使对应游戏的消息缓存失效
        返回发生变化的游戏名称列表（供 UI 刷新）；无变化返回 []。"""
        changed = []
        for mdt in cls.getMdts():
            bml_path = getPath(f"BML/.Mindustrys/{mdt}/BML.json")
            bml_mtime = 0
            icon_path = None
            try:
                if os.path.isfile(bml_path):
                    bml_mtime = os.path.getmtime(bml_path)
                    with open(bml_path, "r", encoding="utf-8") as f:
                        icon_path = (json.load(f) or {}).get("icon_path")
            except (OSError, ValueError, TypeError):
                pass
            # 处理 null / 无效 icon_path → 写回默认值
            resolved = None
            if icon_path:
                cand = getPath(icon_path) if not os.path.isabs(icon_path) else icon_path
                if os.path.isfile(cand) and cls._is_valid_image(cand):
                    resolved = cand
            if resolved is None:
                cls._write_icon_path(mdt, cls.DEFAULT_ICON)
                cls._mdt_msg_cache.pop(mdt, None)
                changed.append(mdt)
                continue
            # icon.png 存在则优先
            png_path = getPath(f"BML/.Mindustrys/{mdt}/icon.png")
            png_mtime = 0
            png_size = 0
            if os.path.isfile(png_path):
                resolved = png_path
                png_mtime = os.path.getmtime(png_path)
                png_size = os.path.getsize(png_path)
            jar_mtime = 0
            try:
                jar_mtime = os.path.getmtime(cls._get_mdt_jar_path(mdt))
            except OSError:
                pass
            new_key = (jar_mtime, bml_mtime, resolved, png_mtime, png_size)
            cached = cls._mdt_msg_cache.get(mdt)
            if cached:
                cached_key, _ = cached
                if cached_key != new_key:
                    cls._mdt_msg_cache.pop(mdt, None)
                    changed.append(mdt)
        return changed

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

    @classmethod
    def getDownloadingMdts(cls):
        """返回 .Mindustrys 下所有含 downloading.json 的子目录名称及内容。

        返回 {子目录名: downloading.json 内容}；
        没有任何子目录存在 downloading.json 时返回 None。"""
        result = {}
        if not os.path.isdir(cls.base_dir):
            return None
        for item in os.listdir(cls.base_dir):
            subdir = os.path.join(cls.base_dir, item)
            if not os.path.isdir(subdir):
                continue
            dfile = os.path.join(subdir, "downloading.json")
            if os.path.isfile(dfile):
                try:
                    with open(dfile, "r", encoding="utf-8") as f:
                        result[item] = json.load(f)
                except Exception:
                    continue
        return result if result else None

    @classmethod
    def _retrieve_mdt_data(cls, subdir_name):
        """读取 data.json，与默认值深度合并后写回。"""
        default_data = {
            "javaPath": "<:|follow|:>",
            "appdataCopy": False
        }
        data_path = os.path.join(cls.base_dir, subdir_name, "BML.json")
        file_data = {}
        if os.path.isfile(data_path):
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
            except Exception:
                file_data = {}
        merged = dict(default_data)
        for key, value in file_data.items():
            if key not in default_data:
                continue
            if isinstance(default_data[key], dict) and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key in default_data[key]:
                        merged[key][sub_key] = sub_value
            else:
                merged[key] = value
        try:
            os.makedirs(os.path.dirname(data_path), exist_ok=True)
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, separators=(',', ':'), ensure_ascii=False)
        except Exception:
            pass


    @classmethod
    def getMdtData(cls, subdir_name, settings):
        """返回指定子目录的 BML.json 内容，失败返回默认值。

        javaPath 取值语义：
            None           - 自动匹配（settings["javaPath"]=None 时占位，不写入 BML.json）
            "<:|follow|:>" - 跟随全局设置（写入 BML.json 的标识符）
            具体路径       - 已选定的 Java
        具体路径不可用（Java 缺失/无效）时直接改为 "<:|follow|:>" 写入并返回，
        """
        cls._retrieve_mdt_data(subdir_name)
        data_path = getPath(os.path.join(cls.base_dir, subdir_name, "BML.json"))
        data = {}
        if os.path.isfile(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if (data["javaPath"] == "<:|follow|:>" and settings["javaPath"] is None) or data["javaPath"] is None:
            # 自动选择：优先 17，其次最高版本
            max_vers = -1
            max_path = None
            for path, version in settings["javaPaths"]:
                vers = version.split(".")[0]
                if int(vers) > max_vers:
                    max_vers = int(vers)
                    max_path = path
                if vers == "17":
                    max_path = path
                    max_vers = 17
                    break
            data["javaPath"] = max_path
        elif data["javaPath"] == "<:|follow|:>":
            data["javaPath"] = settings["javaPath"]

        # 仅校验具体路径：不可用 → 改回 follow 写入并返回
        # （None 表示自动匹配，不参与 isJava 校验，也不写入 BML.json）
        java_path = data["javaPath"]
        if java_path and java_path != "<:|follow|:>" and not javaScanner.isJava(java_path):
            data["javaPath"] = "<:|follow|:>"
            try:
                with open(data_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
            except Exception:
                pass
            return data
        return data   