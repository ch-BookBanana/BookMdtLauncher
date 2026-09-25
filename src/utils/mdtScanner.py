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

import shutil

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPixmap

import os, zipfile, json, logging
from .path_utils import getPath
from .javaScanner import javaScanner
from .QThTimer import QThTimer

_log = logging.getLogger("Main.MdtScanner")

# 实例名里 Windows 不允许的字符（与下载页命名校验保持一致）
_INVALID_NAME_CHARS = '\\/:*?"<>|'
# Windows 保留设备名：拿它们当目录名会被系统当成设备，根本创建不出来
_RESERVED_NAMES = ({"CON", "PRN", "AUX", "NUL"}
                   | {f"COM{i}" for i in range(1, 10)}
                   | {f"LPT{i}" for i in range(1, 10)})
_MAX_NAME_LEN = 255   # 单个目录名长度上限（NTFS）


def _key_path(keys):
    """把 "a" / ["a","b"] 统一成键路径列表，供 setData 用。"""
    return [keys] if isinstance(keys, str) else list(keys)


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

class mdtScanner(QObject):
    base_dir = getPath("BML/.Mindustrys")
    DEFAULT_ICON = "src/assets/icons/mdt/mdt.png"
    on_game_changed = Signal(dict)

    # ---- 游戏图标全局缓存表（引用计数，仅主线程操作） ----
    # QPixmaps: {game: QPixmap}；_pixmap_refs: {game: int}
    # 有任一引用即常驻内存；引用归零立即删除释放资源
    QPixmaps = {}
    _pixmap_refs = {}

    # ---- 缓存系统 (mtime-based) ----
    _mdts_cache = None
    _mdts_cache_mtime = 0
    _mdt_msg_cache = {}
    # 图标变化检测的键记录：独立于 _mdt_msg_cache（缓存被 pop 后仍能继续比较）
    _icon_check_keys = {}

    def __init__(self, settings, parent=None, root=None):
        super().__init__(parent)
        self.settings = settings
        self.timer = None
        self.checkGame()
        self.icon_timer = QThTimer.taskP(1000, lambda e: self.check_icons())
        self.icon_timer.setParent(self)
        self.on_game_changed.connect(print)

    @classmethod
    def invalidate_cache(cls, game=None):
        """使缓存失效。game 为 None 时清空全部缓存，否则只清除指定游戏。"""
        if game:
            cls._mdt_msg_cache.pop(game, None)
            cls._icon_check_keys.pop(game, None)
        else:
            cls._mdts_cache = None
            cls._mdt_msg_cache.clear()
            cls._icon_check_keys.clear()

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
    def setData(cls, subdir_name, keys, value):
        """通用写 BML.json 字段：keys 为键路径列表（支持嵌套如 ["a","b"]）。

        setData(subdir_name, ["icon_path"], icon_path) 等价于旧的 _write_icon_path。
        成功返回 True，失败（文件缺失/磁盘错误）返回 False 且不抛异常。
        """
        bml_path = getPath(f"BML/.Mindustrys/{subdir_name}/BML.json")
        try:
            with open(bml_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            node = data
            for k in keys[:-1]:
                child = node.get(k)
                if not isinstance(child, dict):
                    child = {}
                    node[k] = child
                node = child
            node[keys[-1]] = value
            with open(bml_path, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
            return True
        except Exception as exc:
            _log.debug(f"setData({subdir_name}, {keys}) failed: {exc!r}")
            return False

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
            cls.setData(subdir_name, ["icon_path"], icon_path)
            try:
                bml_mtime = os.path.getmtime(bml_path)
            except OSError:
                pass
        # icon_path 指向的文件不存在或非有效图片 → 写回默认图标
        cand = getPath(icon_path) if not os.path.isabs(icon_path) else icon_path
        if os.path.isfile(cand) and cls._is_valid_image(cand):
            png = cand
        else:
            cls.setData(subdir_name, ["icon_path"], cls.DEFAULT_ICON)
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

    def check_icons(self):
        """随周期检查各游戏图标状态（子线程执行）。

        - icon_path 为 null/空或指向无效图片 → 写回默认图标
        - BML.json 或 icon.png 变化 → 使对应游戏的消息缓存失效
        检测到变化时 emit on_game_changed({"type": "iconChanged", "game": ...})；
        QPixmaps 缓存的失效由主线程收到事件后处理（GUI 资源禁止跨线程操作）。"""
        for mdt in self.getMdts():
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
                if os.path.isfile(cand) and self._is_valid_image(cand):
                    resolved = cand
            if resolved is None:
                self.setData(mdt, ["icon_path"], self.DEFAULT_ICON)
                self._mdt_msg_cache.pop(mdt, None)
                self.on_game_changed.emit({"type": "iconChanged", "game": mdt})
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
                jar_mtime = os.path.getmtime(self._get_mdt_jar_path(mdt))
            except OSError:
                pass
            new_key = (jar_mtime, bml_mtime, resolved, png_mtime, png_size)
            if self._icon_check_keys.get(mdt) != new_key:
                # 首次检查只建立基线不通知（启动时 UI 自行加载图标，无需全量刷）
                first = mdt not in self._icon_check_keys
                self._icon_check_keys[mdt] = new_key
                if not first:
                    self._mdt_msg_cache.pop(mdt, None)
                    self.on_game_changed.emit({"type": "iconChanged", "game": mdt})

    @classmethod
    def get_icon_pixmap(cls, game, size=None):
        """获取游戏图标 QPixmap 并 +1 引用（主线程调用）。

        缓存未命中时按 getMdtMsg 的图标解析结果加载；
        size 指定时返回缩放副本（缓存保留原始尺寸，供多次不同尺寸复用）。
        调用方不再需要时必须成对调用 release_icon_pixmap(game)。"""
        pix = cls.QPixmaps.get(game)
        if pix is None:
            path = None
            try:
                msg = cls.getMdtMsg(game)
                path = msg.get("icon") if msg else None
            except Exception:
                path = None
            if not path or not os.path.isfile(path):
                path = getPath(cls.DEFAULT_ICON)
            pix = QPixmap(path)
            if pix.isNull():
                pix = QPixmap(getPath(cls.DEFAULT_ICON))
            cls.QPixmaps[game] = pix
            cls._pixmap_refs[game] = 0
        cls._pixmap_refs[game] += 1
        if size:
            return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return pix

    @classmethod
    def release_icon_pixmap(cls, game):
        """释放游戏图标引用（主线程调用）。引用计数归零时从 QPixmaps 删除并释放资源。"""
        refs = cls._pixmap_refs.get(game, 0)
        if refs <= 1:
            cls._pixmap_refs.pop(game, None)
            cls.QPixmaps.pop(game, None)
        else:
            cls._pixmap_refs[game] = refs - 1

    @classmethod
    def invalidate_icon_pixmap(cls, game):
        """图标文件变化后使 QPixmaps 缓存失效（主线程调用）。

        删除表条目（保留引用计数），下次 get_icon_pixmap 时重新加载新图标。"""
        cls.QPixmaps.pop(game, None)

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
            "javaPath": "<:|follow|:>"
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
                # 保留未知字段（name、icon_path 等），避免写回时被清掉
                merged[key] = value
                continue
            if isinstance(default_data[key], dict) and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key in default_data[key]:
                        merged[key][sub_key] = sub_value
            else:
                merged[key] = value
        # 内容无变化则不写回：避免每次 checkGame 刷新 BML.json mtime，
        # 否则 check_icons 的缓存键(bml_mtime)永远不匹配，每秒全量误报 iconChanged
        if merged == file_data:
            return
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

    # ==================== 实例编辑 ====================

    def edit(self, name):
        """取某个实例的编辑入口：mdtScanner.edit("原版-146").rename("我的原版")。

        edit 只做一件事：把实例名注入编辑器类再实例化，返回现成的编辑器对象。
        名字只在这一处传，之后每个编辑方法都从编辑器自身的 name 取目标，
        所以能一路点下去（a.b(1).c()）。写方法返回编辑器自身，成败看 ok / error。

        edit 只认正式实例（目录里 mdt.jar 有效且含 version.properties，与
        getMdts() / 界面列表同一判据）：下载中的半截目录不是实例，
        对它的任何写操作都报 notFound。
        """
        return self.Editor(self, name)

    @classmethod
    def check_name(cls, name):
        """校验实例名是否可用：合法返回 None，否则返回 Editor.error 同款失败码。

        按 Windows 的目录命名收口：非空、无 \\/:*?"<>| 、无控制字符、
        不以点开头、不以点或空格结尾、不是 CON/COM1 之类保留设备名、长度不超 255。
        以点开头单独给 "dot"（下载页对它有专属文案），其余一律 "invalidName"。
        重名不在这里判——那要看目录与登记集合，用 name_conflict() / unique_name()。
        """
        name = str(name).strip()
        if not name or len(name) > _MAX_NAME_LEN:
            return "invalidName"
        if any(ch in name for ch in _INVALID_NAME_CHARS) or any(ch < " " for ch in name):
            return "invalidName"
        if name.startswith("."):
            return "dot"
        if name.endswith(".") or name.endswith(" "):
            return "invalidName"
        if name.split(".")[0].upper() in _RESERVED_NAMES:
            return "invalidName"
        return None

    def taken_names(self):
        """已被占用的实例名集合（统一 normcase，大小写不敏感）。

        两个来源：.Mindustrys 下的全部子目录（含下载中、含 jar 损坏的），
        加上 gameList 里的登记。用目录实测而不是 getMdts()——名字最终要落在
        真实目录上，半截目录与损坏目录一样会撞名；登记也要算：目录被删后
        那笔登记得等下一轮 checkGame 才清。
        """
        taken = set()
        try:
            for item in os.listdir(self.base_dir):
                if os.path.isdir(os.path.join(self.base_dir, item)):
                    taken.add(os.path.normcase(item))
        except OSError:
            pass
        for games in self.settings["gameList"].values():
            taken.update(os.path.normcase(str(game)) for game in games)
        return taken

    def name_conflict(self, name, except_name=None):
        """name 能否用作实例名：可用返回 None，否则返回失败码（大小写不敏感）。

            downloading  这个名字正被下载中的任务占着（它比“已存在”更该被看到）
            exists       已是别的实例目录，或 gameList 里已登记
        except_name 是改名时略过的自身旧名，让「只改大小写」不被当成重名。
        """
        norm = os.path.normcase(name)
        if except_name and norm == os.path.normcase(except_name):
            return None
        if norm not in self.taken_names():
            return None
        if os.path.isfile(os.path.join(self.base_dir, name, "downloading.json")):
            return "downloading"
        return "exists"

    def unique_name(self, name, existing=None):
        """name 已被占用时依次尝试 name(1)、name(2)…返回第一个可用的名字。

        existing 是占用名集合；省略则现取 taken_names()。
        下载页的默认名与重名自动改名都走这里，后缀规则只有这一份。
        """
        taken = self.taken_names() if existing is None else existing
        taken = {os.path.normcase(str(n)) for n in taken}
        name = str(name).strip()
        if os.path.normcase(name) not in taken:
            return name
        index = 1
        while os.path.normcase("%s(%d)" % (name, index)) in taken:
            index += 1
        return "%s(%d)" % (name, index)

    class Editor:
        """单个实例的编辑接口（mdtScanner.edit(name) 返回，勿直接构造）。

        读：exists()。写：set() / java() / icon() / rename()，全部返回 self。

        ok 与 error 是最近一次操作的结果（error 为 None 即成功），失败码：
            notFound      不是正式实例（目录不存在，或只是下载中的半截目录）
            invalidName   名称非法（空、含 \\/:*?"<>| 、以点或空格结尾、保留设备名）
            dot           名称以点开头
            exists        目标名称已被占用
            downloading   目标名正被下载中的任务占用
            locked        实例正在运行（被启动器锁住），改名被系统拒绝
            invalidJava   传入的 Java 路径不是有效 Java
            invalidImage  传入的图标不是有效图片
            ioError       其它磁盘错误
        失败码留给调用方翻成语言键——本类不碰 UI 与翻译。
        名称规则只有一份：check_name() 判字形、name_conflict() 判占用。
        改名成功后发 on_game_changed 的 nameChanged 事件，
        UI 侧按事件释放旧图标、按新名重取（图标缓存不在这里搬）。
        """

        def __init__(self, scanner, name):
            self._scanner = scanner
            self.name = name                  # 实例名（= 目录名，改完名同步更新）
            self.ok = True
            self.error = None

        @property
        def path(self):
            """实例目录（随 name 走，改名后自然跟着变，不用手动同步）。"""
            return os.path.join(self._scanner.base_dir, self.name)

        # ---------- 结果 ----------
        def _ok(self):
            self.ok = True
            self.error = None
            return self

        def _fail(self, code, exc=None):
            self.ok = False
            self.error = code
            _log.debug(f"edit({self.name}) failed: {code}" + (f" ({exc!r})" if exc else ""))
            return self

        # ---------- 读 ----------
        def exists(self):
            """该实例是否存在：只认正式实例——目录里有可用的 mdt.jar。

            与 getMdts() / 界面列表同一判据。下载中的目录只有半截 jar 和
            downloading.json，不是实例，所以写操作全报 notFound。
            """
            return os.path.isdir(self.path) and self._scanner.isMdtFile(self.name)

        # ---------- 写 ----------
        def set(self, keys, value):
            """写 BML.json 字段：keys 可为 "a" 或 ["a","b"]（嵌套）。"""
            if not self.exists():
                return self._fail("notFound")
            if not self._scanner.setData(self.name, _key_path(keys), value):
                return self._fail("ioError")
            return self._ok()

        def java(self, path=None):
            """设置实例使用的 Java：path=None 表示跟随全局设置。"""
            if path is None:
                return self.set("javaPath", "<:|follow|:>")
            if not path or not javaScanner.isJava(path):
                return self._fail("invalidJava")
            return self.set("javaPath", path)

        def icon(self, src=None):
            """设置实例图标：src 为图片路径 → 复制成实例内 icon.png；
            src=None → 删掉 icon.png 恢复默认图标。"""
            if not self.exists():
                return self._fail("notFound")
            png = os.path.join(self.path, "icon.png")
            if src is None:
                try:
                    if os.path.isfile(png):
                        os.remove(png)
                except OSError as exc:
                    return self._fail("ioError", exc)
            else:
                if not self._scanner._is_valid_image(src):
                    return self._fail("invalidImage")
                try:
                    shutil.copyfile(src, png)
                except OSError as exc:
                    return self._fail("ioError", exc)
            # icon_path 归位默认值：实例内 icon.png 优先级更高，
            # 留着旧路径会在 icon.png 被删后又把旧图标捡回来
            self._scanner.setData(self.name, ["icon_path"], self._scanner.DEFAULT_ICON)
            self._scanner.invalidate_cache(self.name)
            self._scanner.invalidate_icon_pixmap(self.name)
            self._scanner.on_game_changed.emit({"type": "iconChanged", "game": self.name})
            return self._ok()

        def rename(self, new_name):
            """重命名实例：改目录名 + 同步 BML.json 的 name 与 settings 里的登记。

            三种「改不了」各有自己的码：
                notFound     目标实例不是正式实例（目录没了，或只是下载中的半截目录）
                exists       新名已有实例目录，或 gameList 里已登记同名
                downloading  新名正被下载中的任务占用
                locked       实例正在运行（mdtLocker 握着句柄，系统拒绝改名）
            只改大小写不算重名，照常改。
            """
            new_name = str(new_name).strip()
            if not self.exists():
                return self._fail("notFound")
            if new_name == self.name:
                return self._ok()
            error = self._scanner.check_name(new_name)
            if error:
                return self._fail(error)
            old_name = self.name
            conflict = self._scanner.name_conflict(new_name, except_name=old_name)
            if conflict:
                return self._fail(conflict)
            target = os.path.join(self._scanner.base_dir, new_name)
            try:
                os.rename(self.path, target)
            except PermissionError as exc:
                return self._fail("locked", exc)
            except OSError as exc:
                return self._fail("ioError", exc)
            self.name = new_name
            self._scanner.setData(new_name, ["name"], new_name)
            self._scanner.invalidate_cache(old_name)
            self._sync_settings(old_name, new_name)
            self._scanner.on_game_changed.emit({"type": "nameChanged", "game": new_name, "old_name": old_name})
            return self._ok()

        # ---------- 内部 ----------
        def _sync_settings(self, old_name, new_name):
            """把 settings 里的登记从旧名换成新名（gameList 各分组与 defaultGame）。

            必须在发 nameChanged 之前完成：主线程收事件后会存盘。
            同名只可能有一处（重名在前面已被 name_conflict 挡住），所以按精确名字换。
            """
            for games in self._scanner.settings["gameList"].values():
                for index, game in enumerate(games):
                    if game == old_name:
                        games[index] = new_name
            if self._scanner.settings["defaultGame"] == old_name:
                self._scanner.settings["defaultGame"] = new_name

    def _checkGame(self):
        mdts = self.getMdts()
        setting = []
        for _, value in self.settings["gameList"].items():
            setting += value.copy()
        for mdt in mdts:
            data = self.getMdtData(mdt, self.settings)
            # 1. 目录名与 BML.json 的 name 不一致 → 重命名（以目录名为准）
            old_name = data.get("name", None)
            if old_name is not None and old_name != mdt:
                self.on_game_changed.emit({"type": "nameChanged", "game": mdt, "old_name": old_name})
                self.setData(mdt, ["name"], mdt)
                if mdt in setting:
                    # 重名：目录名早就有登记了，旧名那笔是残留（或同一个实例被记了两次）。
                    # 只把旧名清掉，别再插一笔同名的，否则 gameList 里会出现两份。
                    for _, value in self.settings["gameList"].items():
                        while old_name in value:
                            value.remove(old_name)
                    setting = [v for v in setting if v != old_name]
                    self.on_game_changed.emit({"type": "deleteGame", "game": old_name})
                else:
                    for _, value in self.settings["gameList"].items():
                        if old_name in value:
                            value[value.index(old_name)] = mdt
                    for i, v in enumerate(setting):
                        if v == old_name:
                            setting[i] = mdt
                if self.settings["defaultGame"] == old_name:
                    self.settings["defaultGame"] = mdt
            # 2. 目录存在但不在 gameList → 新游戏
            if mdt not in setting:
                self.settings["gameList"].setdefault("<:|default|:>", []).append(mdt)
                self.on_game_changed.emit({"type": "newGame", "game": mdt})
            # 3. 图片检测：BML.json 的 icon_path 缺失或指向无效图片 → 写回默认并通知
            icon_path = data.get("icon_path", None)
            cand = getPath(icon_path) if icon_path and not os.path.isabs(icon_path) else icon_path
            if not (icon_path and os.path.isfile(cand) and self._is_valid_image(cand)):
                self.setData(mdt, ["icon_path"], self.DEFAULT_ICON)
                self.on_game_changed.emit({"type": "iconChanged", "game": mdt})
        # 4. 在 gameList 但目录已不存在 → 删除
        for dat in setting:
            if dat not in mdts:
                self.on_game_changed.emit({"type": "deleteGame", "game": dat})
                for _, value in self.settings["gameList"].items():
                    if dat in value:
                        value.remove(dat)
                        break
        # 5. 维护 defaultGame：缺失/失效时回退到第一个有效副本
        self.ensure_default_game()

    def checkGame(self):
        """立即检查一次。"""
        QThTimer.task(0, lambda e: self._checkGame())
        if self.timer is None:
            self.timer = QThTimer.taskP(3000, lambda e: self._checkGame())
            self.timer.setParent(self)
        else:
            self.timer.start()

    def ensure_default_game(self):
        """修正 settings['defaultGame']：无副本 → None；失效/缺失 → 第一个有效副本。

        返回修正后的 defaultGame（可能为 None）。在 checkGame 周期与
        事件驱动刷新（start.py Left.refresh）中调用，保证引用始终有效。"""
        mdts = self.getMdts()
        if not mdts:
            self.settings["defaultGame"] = None
        elif self.settings["defaultGame"] not in mdts:
            self.settings["defaultGame"] = mdts[0]
        return self.settings["defaultGame"]