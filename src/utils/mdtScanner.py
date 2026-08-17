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

    # ---- 缓存系统 (sha + size based) ----
    _mdts_cache = None
    _mdts_cache_mtime = 0
    _mdt_data_cache = {}       # {subdir_name: (jar_size, data)}  BML.json + version 缓存

    @classmethod
    def invalidate_cache(cls, game=None):
        """使缓存失效。game 为 None 时清空全部缓存，否则只清除指定游戏。"""
        if game:
            cls._mdt_data_cache.pop(game, None)
        else:
            cls._mdts_cache = None
            cls._mdt_data_cache.clear()

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
        """返回 version.properties 解析后的字典 + icon，失败返回 None。

        version 信息通过 BML.json 持久化缓存（jarSha + jarSize + version），
        由 _retrieve_mdt_data 以「sha + 文件字节数」校验缓存有效性，
        避免每次重复打开 jar 读取 version.properties。

        icon 来源（按优先级）：
            BML.json 的 icon_path 非空（None/空串视为未配置）→ 直接按 getPath
            解析（相对路径基于 exe 所在目录，绝对路径如 C:/ 直接使用）；
            解析出的文件必须存在且可读，否则视为不可用，icon 直接返回 None；
            icon_path 未配置 → 使用副本内 icon.png，缺失时退回全局默认图标
            src/assets/icons/mdt/mdt.png。
        """
        data = cls._retrieve_mdt_data(subdir_name)
        version = data.get("version")
        if not version:
            return None
        png = None
        icon_path = data.get("icon_path")
        if icon_path:
            # 用户显式配置：必须存在且可读，不可用 → icon 直接返回 None（不兜底）
            try:
                png = getPath(icon_path)
                if not os.path.isfile(png) or not os.access(png, os.R_OK):
                    png = None
            except OSError:
                png = None
            result = dict(version)
            result["icon"] = png
            return result
        # 未配置：默认使用副本内 icon.png，缺失时退回全局默认图标
        try:
            png_path = getPath(f"BML/.Mindustrys/{subdir_name}/icon.png")
            if os.path.isfile(png_path) and os.access(png_path, os.R_OK):
                png = png_path
        except OSError:
            png = None
        if png is None:
            try:
                png = getPath("src/assets/icons/mdt/mdt.png")
                if not os.path.isfile(png) or not os.access(png, os.R_OK):
                    png = None
            except Exception:
                png = None
        result = dict(version)
        result["icon"] = png
        return result

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
    def _jar_sha256(cls, jar_path):
        """计算 jar 文件的 sha256（64KB 分块），失败返回 None。"""
        sha256 = hashlib.sha256()
        try:
            with open(jar_path, "rb") as f:
                while True:
                    data = f.read(65536)  # 64KB
                    if not data:
                        break
                    sha256.update(data)
            return sha256.hexdigest()
        except OSError:
            return None

    @classmethod
    def _read_version_from_jar(cls, jar_path):
        """从 jar 内读取并解析 version.properties，失败返回 None。"""
        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                if 'version.properties' not in zf.namelist():
                    return None
                data = zf.read('version.properties').decode('utf-8')
                return _parse_simple_config_typed(data)
        except Exception:
            return None

    @classmethod
    def _retrieve_mdt_data(cls, subdir_name):
        """读取/初始化 BML.json，并将 jar 的版本信息（sha256 + 字节数 + 解析结果）持久化。

        缓存校验策略（比较 sha + 文件字节数）：
            - 先取 jar 当前字节数（os.path.getsize，廉价）；
            - 与内存缓存 / BML.json 中记录的 jarSize 比较：
                * 一致 → jar 内容未变（sha 在写入时已计算验证），直接使用缓存的 version；
                * 不一致 → jar 已变化 → 重新计算 sha256 并重新读取 version.properties，
                  更新缓存并写回 BML.json。
        sha256 仅在校验失败（jar 变化）时计算一次，避免每次全量读文件。
        """
        default_data = {
            "javaPath": "<:|follow|:>",
            "jarSha": "",
            "jarSize": 0,
            "version": None,
            "icon_path": None
        }
        data_path = os.path.join(cls.base_dir, subdir_name, "BML.json")
        jar_path = cls._get_mdt_jar_path(subdir_name)

        try:
            jar_size = os.path.getsize(jar_path)
        except OSError:
            jar_size = 0

        # 内存缓存命中：size 相同 → jar 未变 → version 有效
        cached = cls._mdt_data_cache.get(subdir_name)
        if cached is not None and cached[0] == jar_size:
            # icon_path 是用户配置项（可能被外部编辑），每次从 BML.json 实时刷新
            if os.path.isfile(data_path):
                try:
                    with open(data_path, "r", encoding="utf-8") as f:
                        cached[1]["icon_path"] = json.load(f).get("icon_path")
                except Exception:
                    pass
            return cached[1]

        file_data = {}
        if os.path.isfile(data_path):
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
            except Exception:
                file_data = {}
        merged = dict(default_data)
        for key, value in file_data.items():
            if key in default_data:
                merged[key] = value

        if jar_size > 0 and merged["jarSize"] == jar_size and merged["version"]:
            # 磁盘缓存有效（sha 在写入时已验证），仅回填内存缓存
            cls._mdt_data_cache[subdir_name] = (jar_size, merged)
            return merged

        # 缓存无效或缺失 → 重算 sha + 重读 version
        if jar_size > 0:
            merged["jarSize"] = jar_size
            merged["jarSha"] = cls._jar_sha256(jar_path) or ""
            merged["version"] = cls._read_version_from_jar(jar_path)
        else:
            merged["jarSize"] = 0
            merged["jarSha"] = ""
            merged["version"] = None
        try:
            os.makedirs(os.path.dirname(data_path), exist_ok=True)
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, separators=(',', ':'), ensure_ascii=False)
        except Exception:
            pass
        cls._mdt_data_cache[subdir_name] = (jar_size, merged)
        return merged


    @classmethod
    def getMdtData(cls, subdir_name, settings):
        """返回指定子目录的 BML.json 内容（含 jar 的版本信息），失败返回默认值。

        data 结构：
            javaPath  - Java 配置（见下方取值语义）
            jarSha    - jar 文件的 sha256（缓存有效性指纹）
            jarSize   - jar 文件字节数（缓存有效性指纹）
            version   - jar 内 version.properties 解析后的字典
            icon_path - 自定义图标路径（None/空串=默认副本内 icon.png，
                        其余按 getPath 解析）

        javaPath 取值语义：
            None           - 自动匹配（settings["javaPath"]=None 时占位，不写入 BML.json）
            "<:|follow|:>" - 跟随全局设置（写入 BML.json 的标识符）
            具体路径       - 已选定的 Java
        具体路径不可用（Java 缺失/无效）时直接改为 "<:|follow|:>" 写入并返回，
        """
        data = cls._retrieve_mdt_data(subdir_name)
        data_path = os.path.join(cls.base_dir, subdir_name, "BML.json")
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