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

import base64, hashlib, os, struct, time, zipfile, json, logging
from .path_utils import getPath
from .javaManager import javaManager
from .qthtimer import QThTimer
from .resources import (ICON_MDT)

_log = logging.getLogger("Main.MdtManager")

# 实例名里 Windows 不允许的字符（与下载页命名校验保持一致）
_INVALID_NAME_CHARS = '\\/:*?"<>|'
# Windows 保留设备名：拿它们当目录名会被系统当成设备，根本创建不出来
_RESERVED_NAMES = ({"CON", "PRN", "AUX", "NUL"}
                   | {f"COM{i}" for i in range(1, 10)}
                   | {f"LPT{i}" for i in range(1, 10)})


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


# ═══════════════════ 游戏设置 settings.bin 编解码 ═══════════════════
#
# Mindustry 把玩家设置写在「游戏数据目录」下的 settings.bin，布局与游戏
# SettingsIO 完全一致（实测 5 个在用实例 + 20 份备份/历史快照逐字节印证）：
#
#     int32 BE 条数 N
#     重复 N 组: uint16 BE key 长度 | key 字节 | uint8 类型码 | 该类型的值
#         0 bool     1 字节
#         1 int32    4 字节 BE 有符号
#         2 int64    8 字节 BE 有符号
#         3 float32  4 字节 BE IEEE754
#         4 String   uint16 BE 长度 + 字节
#         5 byte[]   int32 BE 长度 + 原始字节（内容多为游戏侧序列化对象，不解释）
#
# 没有版本号头、没有时间戳、没有校验和：唯一的自洽校验就是「N 条走完必须恰好到
# EOF」，多一字节少一字节都当坏文件。key 与字符串走 Java writeUTF（modified
# UTF-8）：NUL 写成 C0 80、增补平面写成两个 3 字节代理对；BMP 字符（含中文）与
# 标准 UTF-8 完全一致，所以「标准解码能过」就是快路径，「解不动」才需要手工处理。
#
# BML.json 里另存一份 JSON 镜像（mdtData）做双向变更检测。镜像里**每个键都写成
# [类型码, 值]**：
#       "musicvol":                 [1, 100]
#       "MetricCollector.lastPost": [2, 1791120307016]
#       "maxzoomingamemultiplier":  [3, 1.0]
#       "uuid":                     [4, "7qiif72Y7fY="]
#       "serpulo-campaign-stats":   [5, "e3iICnBsYXl0aW1l..." ]
# 把类型码显式存下来有三个好处：int32 与 int64 分得清（不会把「值很小的 long
# 键」写回 int32 让游戏端 getLong() 抛 ClassCastException）；byte[] 不必靠字符串
# 前缀打标记（前缀总有和真实字符串撞车的可能）；镜像本身就是一份带类型的设置表，
# 谁读都能看懂。公开接口（getSettings/setSettings）进出仍是原生类型。

_SETTINGS_BOOL, _SETTINGS_INT, _SETTINGS_LONG = 0, 1, 2
_SETTINGS_FLOAT, _SETTINGS_STR, _SETTINGS_BYTES = 3, 4, 5
_SETTINGS_CODES = (_SETTINGS_BOOL, _SETTINGS_INT, _SETTINGS_LONG,
                   _SETTINGS_FLOAT, _SETTINGS_STR, _SETTINGS_BYTES)
_SETTINGS_INT32_MIN, _SETTINGS_INT32_MAX = -2147483648, 2147483647
_SETTINGS_INT64_MIN, _SETTINGS_INT64_MAX = -9223372036854775808, 9223372036854775807
_SETTINGS_UTF_MAX = 0xFFFF            # writeUTF 的长度上限
_SETTINGS_FLOAT_STRUCT = struct.Struct(">f")


def _settings_decode_utf(raw):
    """writeUTF 的字节 → str：先试标准 UTF-8（BMP 字符全都一致），失败才手工解。"""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return _settings_decode_modified_utf8(raw)


def _settings_decode_modified_utf8(raw):
    """手工解码 Java modified UTF-8（NUL=C0 80、增补平面=两个 3 字节代理对）。

    非法字节序列退化成 U+FFFD，不抛异常 —— 设置文件里不该出现，真出现了也没必要
    为它整份读取失败。
    """
    out = bytearray()
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c < 0x80:
            out.append(c)
            i += 1
        elif (c & 0xE0) == 0xC0 and i + 1 < n:
            out.append(((c & 0x1F) << 6) | (raw[i + 1] & 0x3F))
            i += 2
        elif (c & 0xF0) == 0xE0 and i + 2 < n:
            cp = ((c & 0x0F) << 12) | ((raw[i + 1] & 0x3F) << 6) | (raw[i + 2] & 0x3F)
            i += 3
            # 高代理后面紧跟低代理 → 合成增补平面字符
            if 0xD800 <= cp < 0xDC00 and i + 2 < n and (raw[i] & 0xF0) == 0xE0:
                lo = ((raw[i] & 0x0F) << 12) | ((raw[i + 1] & 0x3F) << 6) | (raw[i + 2] & 0x3F)
                if 0xDC00 <= lo < 0xE000:
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
                    i += 3
            out.extend(chr(cp).encode("utf-8"))
        else:
            out.extend(b"\xef\xbf\xbd")
            i += 1
    return out.decode("utf-8", "replace")


def _settings_encode_utf(text):
    """str → Java writeUTF 字节（modified UTF-8 / CESU-8）。

    与标准 UTF-8 的两处差别，都是 Java 那边的硬要求：
      * NUL 写成 C0 80（标准 UTF-8 是单字节 00）；
      * 增补平面字符（emoji 等）写成**两个 3 字节代理对**，而不是 4 字节序列 ——
        readUTF 只认前者，遇到 4 字节序列会抛 UTFDataFormatException，
        整个 settings.bin 就读不出来了。
    BMP 字符（含中文）与标准 UTF-8 完全一致。
    """
    out = bytearray()
    for ch in text:
        cp = ord(ch)
        if cp == 0:
            out += b"\xc0\x80"
        elif cp <= 0x7F:
            out.append(cp)
        elif cp <= 0x7FF:
            out += bytes((0xC0 | (cp >> 6), 0x80 | (cp & 0x3F)))
        elif cp <= 0xFFFF:
            out += bytes((0xE0 | (cp >> 12),
                          0x80 | ((cp >> 6) & 0x3F),
                          0x80 | (cp & 0x3F)))
        else:
            # 增补平面 → UTF-16 代理对，每个代理各写 3 字节
            v = cp - 0x10000
            for unit in (0xD800 | (v >> 10), 0xDC00 | (v & 0x3FF)):
                out += bytes((0xE0 | (unit >> 12),
                              0x80 | ((unit >> 6) & 0x3F),
                              0x80 | (unit & 0x3F)))
    return bytes(out)


def _settings_decode_typed(data):
    """settings.bin 字节 → {key: (类型码, 原生值)}，类型码原样保留。

    数据不自洽（长度越界、类型码未知、走完不到 EOF 或超出 EOF）一律抛 ValueError，
    由调用方决定怎么兜底 —— 这里不猜、不吞、不修补。
    """
    total = len(data)
    if total < 4:
        raise ValueError("settings.bin 太短: %d 字节" % total)
    count = int.from_bytes(data[0:4], "big", signed=True)
    if count < 0:
        raise ValueError("settings.bin 条数非法: %d" % count)
    out = {}
    from_bytes = int.from_bytes
    unpack_float = _SETTINGS_FLOAT_STRUCT.unpack_from
    pos = 4
    for _ in range(count):
        if pos + 2 > total:
            raise ValueError("key 长度越界 @%d" % pos)
        klen = (data[pos] << 8) | data[pos + 1]
        pos += 2
        end = pos + klen
        if end > total:
            raise ValueError("key 越界 @%d" % pos)
        key = _settings_decode_utf(data[pos:end])
        pos = end
        if pos >= total:
            raise ValueError("类型码越界 @%d" % pos)
        code = data[pos]
        pos += 1
        if code == _SETTINGS_INT:
            if pos + 4 > total:
                raise ValueError("int32 越界 @%d" % pos)
            out[key] = (code, from_bytes(data[pos:pos + 4], "big", signed=True))
            pos += 4
        elif code == _SETTINGS_BOOL:
            if pos + 1 > total:
                raise ValueError("bool 越界 @%d" % pos)
            out[key] = (code, data[pos] != 0)
            pos += 1
        elif code == _SETTINGS_STR:
            if pos + 2 > total:
                raise ValueError("字符串长度越界 @%d" % pos)
            slen = (data[pos] << 8) | data[pos + 1]
            pos += 2
            end = pos + slen
            if end > total:
                raise ValueError("字符串越界 @%d" % pos)
            out[key] = (code, _settings_decode_utf(data[pos:end]))
            pos = end
        elif code == _SETTINGS_LONG:
            if pos + 8 > total:
                raise ValueError("int64 越界 @%d" % pos)
            out[key] = (code, from_bytes(data[pos:pos + 8], "big", signed=True))
            pos += 8
        elif code == _SETTINGS_FLOAT:
            if pos + 4 > total:
                raise ValueError("float32 越界 @%d" % pos)
            out[key] = (code, unpack_float(data, pos)[0])
            pos += 4
        elif code == _SETTINGS_BYTES:
            if pos + 4 > total:
                raise ValueError("byte[] 长度越界 @%d" % pos)
            blen = from_bytes(data[pos:pos + 4], "big", signed=True)
            pos += 4
            end = pos + blen
            if blen < 0 or end > total:
                raise ValueError("byte[] 越界 @%d" % pos)
            out[key] = (code, data[pos:end])
            pos = end
        else:
            raise ValueError("未知类型码 %d（key=%r @%d）" % (code, key, pos - 1))
    if pos != total:
        raise ValueError("尾部多余 %d 字节（count=%d）" % (total - pos, count))
    return out


def _settings_decode(data):
    """settings.bin 字节 → {key: 原生值}（丢掉类型码的扁平版，给外部/测试用）。"""
    return {key: value for key, (_, value) in _settings_decode_typed(data).items()}


def _settings_f32(value, key=None):
    """float → float32 量化后的 Python float。

    settings.bin 里只有 32 位浮点：0.53 存进去就是 0.5299999713897705。镜像与
    typed 表都统一用量化后的值，两者因此永远等价，读-改-写任何一轮都稳定。
    """
    try:
        return _SETTINGS_FLOAT_STRUCT.unpack(_SETTINGS_FLOAT_STRUCT.pack(value))[0]
    except (OverflowError, struct.error):
        raise ValueError("float 超出 float32 范围（key=%r）: %r" % (key, value))


def _settings_normalize_value(code, value, key=None):
    """把值规整成某个类型码对应的 Python 形态；不合格抛 ValueError。"""
    if code == _SETTINGS_BOOL:
        if not isinstance(value, bool):
            raise ValueError("类型码 0 需要 bool（key=%r）: %r" % (key, type(value)))
        return value
    if code in (_SETTINGS_INT, _SETTINGS_LONG):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("类型码 %d 需要 int（key=%r）: %r" % (code, key, type(value)))
        lo, hi = ((_SETTINGS_INT32_MIN, _SETTINGS_INT32_MAX) if code == _SETTINGS_INT
                  else (_SETTINGS_INT64_MIN, _SETTINGS_INT64_MAX))
        if not lo <= value <= hi:
            raise ValueError("整数超出类型码 %d 的范围（key=%r）: %r" % (code, key, value))
        return value
    if code == _SETTINGS_FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("类型码 3 需要数字（key=%r）: %r" % (key, type(value)))
        return _settings_f32(value, key)
    if code == _SETTINGS_STR:
        if not isinstance(value, str):
            raise ValueError("类型码 4 需要 str（key=%r）: %r" % (key, type(value)))
        return value
    if code == _SETTINGS_BYTES:
        if not isinstance(value, (bytes, bytearray)):
            raise ValueError("类型码 5 需要 bytes（key=%r）: %r" % (key, type(value)))
        return bytes(value)
    raise ValueError("未知类型码 %r（key=%r）" % (code, key))


def _settings_pick_code(value, prefer=None, key=None):
    """按 Python 值选类型码；prefer 是原文件里的码，装得下就沿用。

    沿用的意义：一个值很小、但游戏端声明为 long 的键，若只按值推断会被写回 int32，
    游戏 getLong() 读到 Integer 直接 ClassCastException。所以整数一律优先沿用原码。
    """
    if isinstance(value, bool):
        return _SETTINGS_BOOL
    if isinstance(value, int):
        if not _SETTINGS_INT64_MIN <= value <= _SETTINGS_INT64_MAX:
            raise ValueError("整数超出 int64（key=%r）: %r" % (key, value))
        if prefer == _SETTINGS_LONG:
            return _SETTINGS_LONG
        fits32 = _SETTINGS_INT32_MIN <= value <= _SETTINGS_INT32_MAX
        return _SETTINGS_INT if fits32 else _SETTINGS_LONG
    if isinstance(value, float):
        return _SETTINGS_FLOAT
    if isinstance(value, str):
        return _SETTINGS_STR
    if isinstance(value, (bytes, bytearray)):
        return _SETTINGS_BYTES
    raise ValueError("不支持的设置类型 %r（key=%r）" % (type(value), key))


def _settings_values_to_typed(values, prior=None):
    """公开接口的原生 dict → {key: (类型码, 值)}；prior 是已有 typed 表，用来沿用类型码。"""
    if not isinstance(values, dict):
        raise ValueError("settings 必须是 dict，拿到 %r" % type(values))
    prior = prior or {}
    typed = {}
    for key, value in values.items():
        if not isinstance(key, str):
            raise ValueError("settings 的 key 必须是 str，拿到 %r" % (key,))
        old = prior.get(key)
        code = _settings_pick_code(value, old[0] if old else None, key)
        typed[key] = (code, _settings_normalize_value(code, value, key))
    return typed


def _settings_encode_typed(typed):
    """{key: (类型码, 值)} → settings.bin 字节；类型码照写，不再推断。"""
    if not isinstance(typed, dict):
        raise ValueError("typed settings 必须是 dict，拿到 %r" % type(typed))
    buf = bytearray()
    buf += struct.pack(">i", len(typed))
    for key, entry in typed.items():
        code, value = entry
        if not isinstance(key, str):
            raise ValueError("settings 的 key 必须是 str，拿到 %r" % (key,))
        kb = _settings_encode_utf(key)
        if len(kb) > _SETTINGS_UTF_MAX:
            raise ValueError("key 过长（writeUTF 上限 %d 字节）: %r" % (_SETTINGS_UTF_MAX, key))
        buf += struct.pack(">H", len(kb))
        buf += kb
        if code == _SETTINGS_BOOL:
            buf += b"\x00" + (b"\x01" if value else b"\x00")
        elif code == _SETTINGS_INT:
            buf += b"\x01" + struct.pack(">i", value)
        elif code == _SETTINGS_LONG:
            buf += b"\x02" + struct.pack(">q", value)
        elif code == _SETTINGS_FLOAT:
            buf += b"\x03" + _SETTINGS_FLOAT_STRUCT.pack(value)
        elif code == _SETTINGS_STR:
            sb = _settings_encode_utf(value)
            if len(sb) > _SETTINGS_UTF_MAX:
                raise ValueError("字符串过长（writeUTF 上限 %d 字节）: %r" % (_SETTINGS_UTF_MAX, key))
            buf += b"\x04" + struct.pack(">H", len(sb)) + sb
        elif code == _SETTINGS_BYTES:
            raw = bytes(value)
            buf += b"\x05" + struct.pack(">i", len(raw)) + raw
        else:
            raise ValueError("未知类型码 %r（key=%r）" % (code, key))
    return bytes(buf)


def _settings_encode(values):
    """扁平 dict → settings.bin 字节（按值推断类型码的便利入口）。"""
    return _settings_encode_typed(_settings_values_to_typed(values))


def _settings_mirror(typed):
    """typed → BML.json 里的 JSON 镜像 {key: [类型码, 值]}；byte[] 存 base64 字符串。"""
    mirror = {}
    for key, (code, value) in typed.items():
        if code == _SETTINGS_BYTES:
            mirror[key] = [code, base64.b64encode(value).decode("ascii")]
        else:
            mirror[key] = [code, value]
    return mirror


def _settings_typed_from_mirror(mirror):
    """JSON 镜像 → typed；结构不对或类型不匹配抛 ValueError。

    调用方据此认定「这份镜像不可信」（例如手改坏了、或是别处写的旧形状），
    改从 settings.bin 重建，而不是拿坏数据去写游戏文件。
    """
    if not isinstance(mirror, dict):
        raise ValueError("镜像必须是 dict，拿到 %r" % type(mirror))
    typed = {}
    for key, entry in mirror.items():
        if not isinstance(key, str):
            raise ValueError("镜像的 key 必须是 str: %r" % (key,))
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("镜像的键 %r 不是 [类型码, 值] 形状" % (key,))
        code, value = entry
        if isinstance(code, bool) or not isinstance(code, int) or code not in _SETTINGS_CODES:
            raise ValueError("镜像的键 %r 类型码非法: %r" % (key, code))
        if code == _SETTINGS_BYTES:
            if not isinstance(value, str):
                raise ValueError("镜像的键 %r 的类型码是 5，值应为 base64 字符串" % (key,))
            try:
                value = base64.b64decode(value, validate=True)
            except Exception:
                raise ValueError("镜像的键 %r 的 base64 非法" % (key,))
        elif code in (_SETTINGS_INT, _SETTINGS_LONG):
            # JSON 里的整数可能被手改成 1.0 这种写法，整数值就认
            if isinstance(value, float) and value.is_integer():
                value = int(value)
        typed[key] = (code, _settings_normalize_value(code, value, key))
    return typed


def _settings_values(typed):
    """typed → 公开接口用的扁平原生 dict。"""
    return {key: value for key, (_, value) in typed.items()}


def _settings_hash(obj):
    """变更检测用的指纹，两种口径：

    bytes  → sha256(settings.bin 原始字节)，判断「游戏是否改过盘上文件」；
    dict   → sha256(规范化 JSON 镜像)，判断「镜像是否被改过」。
    镜像口径用 sort_keys=True：只比内容不比键序，手改 BML.json 时重排键序不算变更。
    """
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(obj)).hexdigest()
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class mdtManager(QObject):
    base_dir = getPath("BML/.Mindustrys")

    @classmethod
    def ensure_dirs(cls):
        """建好实例目录。路径只此一处 —— 原先 main.py 又抄了一遍字面量去建它，
        改一处忘一处的话，实例扫描会当成「一个都没有」。"""
        os.makedirs(cls.base_dir, exist_ok=True)
    DEFAULT_ICON = ICON_MDT
    MAX_NAME_LEN = 32
    on_game_changed = Signal(dict)
    # BML.json 里「跟随全局设置」的标识符（只写不读：界面按它显示「跟随全局」那个选项）
    FOLLOW = "<:|follow|:>"
    # settings["gameList"] 里默认分组的键（是个符号名，显示前要过 i18n 翻成「默认」）
    DEFAULT_GROUP = "<:|default|:>"

    DATA_ROOT_NAME = "data"
    DATA_DIR_NAME = "Mindustry"
    SETTINGS_FILE_NAME = "settings.bin"
    DATA_FOLDERS = {"data": "", "blueprint": "schematics", "mod": "mods"}

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
    def getDataRoot(cls, subdir_name):
        """实例的数据根路径（<实例目录>/data）；实例名为空返回 ""。

        即启动游戏时给进程设的 %APPDATA% 与工作目录，比 mdtData 高一级。
        """
        if not subdir_name:
            return ""
        return os.path.join(cls.base_dir, subdir_name, cls.DATA_ROOT_NAME)

    @classmethod
    def getDataFolder(cls, subdir_name, kind="data"):
        """实例某个数据文件夹的完整路径；实例名为空或类别未知返回 ""。

        kind 取 DATA_FOLDERS 的键：data（数据目录本体）/ blueprint（蓝图）/ mod（模组）。
        只拼路径，不建目录、也不判断存在——建目录与打开是「要用这个文件夹」时的事。
        """
        if kind not in cls.DATA_FOLDERS:
            return ""
        root = cls.getDataRoot(subdir_name)
        if not root:
            return ""
        return os.path.join(root, cls.DATA_DIR_NAME, cls.DATA_FOLDERS[kind])

    # ==================== 游戏设置（settings.bin）====================
    #
    # 读写口径见模块顶部的编解码说明与规范：
    #   - 位置只有一个「游戏数据目录」= <数据根>/Mindustry（mdtLauncher 把
    #     MINDUSTRY_DATA_DIR 与兜底的 APPDATA 都指到同一处）；
    #   - 读的时候认得旧版启动器留在 <数据根>/settings.bin 的遗留文件，
    #     但**写永远只写规范位置**，不再制造第二份；
    #   - BML.json 里的 mdtData 是设置的 JSON 镜像 + 双指纹，负责「游戏改过没」
    #     与「镜像被改过没」这两个判断。

    @classmethod
    def _settings_file(cls, subdir_name, for_write=False):
        """返回 settings.bin 的路径；实例名为空返回 ""。

        规范位置是 <数据根>/Mindustry/settings.bin。读路径（for_write=False）下，
        规范位置不存在而 <数据根>/settings.bin 存在时返回后者 —— 那是重构前
        启动器把数据目录直接设在数据根上留下的遗留文件，只为读兼容。
        for_write=True 时无论遗留文件在不在都只给规范位置。
        """
        if not subdir_name:
            return ""
        main = os.path.join(cls.getDataFolder(subdir_name, "data"), cls.SETTINGS_FILE_NAME)
        if for_write:
            return main
        if os.path.isfile(main):
            return main
        legacy = os.path.join(cls.getDataRoot(subdir_name), cls.SETTINGS_FILE_NAME)
        if os.path.isfile(legacy):
            return legacy
        return main

    @classmethod
    def _settings_block(cls, subdir_name):
        """读 BML.json 里的 mdtData 块，读不到/结构不对返回 None。"""
        bml_path = getPath(f"BML/.Mindustrys/{subdir_name}/BML.json")
        try:
            with open(bml_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, TypeError):
            return None
        block = data.get("mdtData") if isinstance(data, dict) else None
        return block if isinstance(block, dict) else None

    @classmethod
    def _set_settings_block(cls, subdir_name, bin_hash, json_hash, mirror, current=None):
        """把 mdtData 三个字段整块写回 BML.json。

        **幂等**：内容没变就一个字节都不写。这一步是硬要求而不是优化 —— 白改
        BML.json 的 mtime 会让它自己的 mtime 型缓存全部失效（版本信息缓存要重开
        数十 MB 的 mdt.jar）。三个字段必须一次写完整，不能出现「指纹是新的、
        镜像是旧的」这种中间态。

        current 是调用方手上已有的 mdtData 块（读路径刚解析过 BML.json 时传进来，
        省掉一次重复读盘；BML.json 的每次 open 都不便宜）。
        """
        block = {"binHash": bin_hash, "jsonHash": json_hash, "data": mirror}
        if current is None:
            current = cls._settings_block(subdir_name)
        if current == block:
            return True
        return cls.setData(subdir_name, ["mdtData"], block)

    @staticmethod
    def _write_bytes_atomic(path, raw):
        """原子写字节：同目录唯一临时文件 → flush → fsync → os.replace。

        任意时刻磁盘上的目标要么是旧内容要么是新内容，不会出现半截文件。
        os.replace 在 Windows 上可能被杀毒/索引临时占用，短重试以躲开瞬时锁
        （与 settings.py 的 atomic_write_json 同一套做法）。
        """
        tmp = "%s.%d-%d.tmp" % (path, os.getpid(), time.time_ns())
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            for attempt in range(4):
                try:
                    os.replace(tmp, path)
                    return True
                except PermissionError:
                    if attempt == 3:
                        raise
                    time.sleep(0.05)
        except OSError as exc:
            _log.debug(f"_write_bytes_atomic({path}) failed: {exc!r}")
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return False

    @classmethod
    def _backup_bad_settings(cls, path):
        """把损坏的 settings.bin 复制进 badSettings/ 留证，只保留最近几份。

        只为「别把证据丢了」：getSettings 的返回值契约仍是 {}，不受影响。
        目录与保留份数沿用 settings.json 那套（BAD_DIR / BAD_KEEP），文件名带
        settingsbin. 前缀，与 JSON 备份互不覆盖。延迟导入是为了避开
        settings.py → 页面/注册表 → mdtManager 的循环导入。
        """
        try:
            from .settings import BAD_DIR, BAD_KEEP
            folder = getPath(BAD_DIR)
            os.makedirs(folder, exist_ok=True)
            name = "settingsbin.%s.bin" % time.strftime("%Y%m%d-%H%M%S")
            dest = os.path.join(folder, name)
            shutil.copy2(path, dest)
            names = sorted(n for n in os.listdir(folder)
                           if n.startswith("settingsbin.") and n.endswith(".bin"))
            keep = max(0, int(BAD_KEEP))
            for old in (names if keep == 0 else names[:-keep]):
                try:
                    os.remove(os.path.join(folder, old))
                except OSError:
                    pass
            return dest
        except Exception as exc:
            _log.debug(f"_backup_bad_settings({path}) failed: {exc!r}")
            return None

    @classmethod
    def getSettings(cls, subdir_name):
        """读该实例的游戏设置，返回 dict（值只有 bool/int/float/str/bytes）。

        读不到（实例名无效、游戏还没启动过、文件损坏）一律返回 {}，不抛异常。

        与 BML.json 的 mdtData 镜像按四态同步，判据是两个指纹：
            binHash  = sha256(settings.bin 原始字节) → 游戏改过盘上文件没
            jsonHash = sha256(镜像的规范化 JSON)     → 镜像被改过没
        两边都对得上 → 直接用镜像（只算指纹、不解析 bin、不写盘）
        只有 bin 变了 → 解析 bin 并原子刷新镜像（bin 是设置的唯一权威）
        只有镜像变了 → 返回镜像现值，**绝不自动写 bin**（写不写由调用方 setSettings 决定）
        两边都变了   → 兜底以镜像为准（正常流程下不可达：游戏运行时 BML.json 被
                       mdtLocker 握着只读句柄写不进去，管理界面也同时被锁）

        镜像里每个键是 [类型码, 值]，所以返回值的类型与文件里完全对应；镜像结构
        看不懂时（旧形状、手改坏了）当它不存在，改从 bin 重建。

        损坏的 settings.bin 会复制一份到 badSettings/ 留证，返回值仍是 {}。
        """
        if not subdir_name:
            return {}
        path = cls._settings_file(subdir_name)
        raw = None
        if path:
            try:
                with open(path, "rb") as f:
                    raw = f.read()
            except OSError as exc:
                _log.debug(f"getSettings({subdir_name}) read failed: {exc!r}")
                raw = None
        bin_hash = _settings_hash(raw) if raw is not None else None
        block = cls._settings_block(subdir_name)
        mirror, mirror_hash, typed_mirror = None, None, None
        if block and isinstance(block.get("data"), dict):
            try:
                # 镜像必须能解成 [类型码, 值] 才可信；旧形状/手改坏了 → 当没有镜像，
                # 强制从 bin 重建（绝不用一份看不懂的镜像去写游戏文件）。
                typed_mirror = _settings_typed_from_mirror(block["data"])
                mirror_hash = _settings_hash(block["data"])
                mirror = block["data"]
            except (TypeError, ValueError):
                mirror, mirror_hash, typed_mirror = None, None, None
        # 指纹缺失 = 那份镜像不是本版本写的，不可信 → 一律按 bin 重建。
        # （否则「有 data 但没有 jsonHash」会被误判成冲突，把陈旧镜像当成手改结果供出去。）
        has_prints = bool(isinstance(block, dict)
                          and isinstance(block.get("binHash"), str)
                          and isinstance(block.get("jsonHash"), str))
        bin_ok = bool(typed_mirror is not None and has_prints and block.get("binHash") == bin_hash)
        json_ok = bool(typed_mirror is not None and has_prints and block.get("jsonHash") == mirror_hash)
        # 两边都对上：镜像就是当前设置的忠实表示，不必解析 bin
        if bin_ok and json_ok:
            return _settings_values(typed_mirror)
        if raw is None:
            # 没有 settings.bin：游戏没启动过（或实例数据被清掉）。
            # 不动 mdtData —— 留下旧镜像比把「还没启动过」写成「设置全空」更可恢复。
            return {}
        # 只有镜像被改过（bin 没动）：返回镜像现值，既不解析 bin 也不刷新镜像，
        # 更不能替调用方决定要不要写进游戏 —— 那是 setSettings 的事。
        if bin_ok and not json_ok:
            return _settings_values(typed_mirror)
        try:
            typed = _settings_decode_typed(raw)
        except ValueError as exc:
            _log.warning(f"getSettings({subdir_name}) settings.bin 损坏: {exc}")
            cls._backup_bad_settings(path)
            return {}
        # 两边都变过：兜底以镜像为准（不刷新，避免把玩家的手改冲掉）
        if typed_mirror is not None and has_prints and not bin_ok and not json_ok:
            _log.warning(f"getSettings({subdir_name}) bin 与镜像都变过，以镜像为准")
            return _settings_values(typed_mirror)
        new_mirror = _settings_mirror(typed)
        cls._set_settings_block(subdir_name, bin_hash, _settings_hash(new_mirror),
                                new_mirror, current=block)
        return _settings_values(typed)

    @classmethod
    def setSettings(cls, subdir_name, values):
        """整表覆盖写该实例的游戏设置，成功返回 True，失败 False（不抛异常）。

        **整表覆盖**：values 就是写入后 settings.bin 的全部内容，没有 patch 概念 ——
        没出现在 values 里的键视为删除。值只接受 bool/int/float/str/bytes，
        其余类型整次失败（不猜、不做字符串兜底）。

        类型码优先沿用镜像里已有的码（int 依旧 int、long 依旧 long，值太小也不会
        被降级成 int32 导致游戏端 getLong() 抛 ClassCastException）；只有新键才按
        值推断（超 int32 写 int64）。float 一律按 float32 量化。

        写入顺序：先原子写 settings.bin，再刷新 BML.json 的 mdtData 镜像。
        镜像那步失败不算写入失败（bin 已经是新内容了）：下次 getSettings 会看到
        binHash 对不上，自动把镜像重建出来。

        安全边界（调用方负责）：
            - 不备份、不回读校验、不回滚 —— 一次写坏即损坏，游戏侧的
              settings_backup.bin 只能救回「上一次游戏保存」的版本；
            - 不要趁游戏运行时写：游戏下一次保存会整表重写，静默覆盖本次改动
              （届时 BML.json 也被 mdtLocker 握着只读句柄，镜像那步会失败）；
            - 同一实例不提供互斥，并发调用由调用方串行化。
        """
        if not subdir_name or not isinstance(values, dict):
            return False
        path = cls._settings_file(subdir_name, for_write=True)
        if not path:
            return False
        block = cls._settings_block(subdir_name)
        prior = None
        if block and isinstance(block.get("data"), dict):
            try:
                # 沿用镜像里的类型码：值很小的 long 键不会被写回 int32
                prior = _settings_typed_from_mirror(block["data"])
            except (TypeError, ValueError):
                prior = None
        try:
            typed = _settings_values_to_typed(values, prior)
            raw = _settings_encode_typed(typed)
        except (ValueError, TypeError, struct.error) as exc:
            _log.warning(f"setSettings({subdir_name}) 拒绝写入: {exc}")
            return False
        # 幂等：与盘上内容一模一样就不写（避免白改 mtime 打穿别人的 mtime 缓存）
        current = None
        try:
            with open(path, "rb") as f:
                current = f.read()
        except OSError:
            current = None
        if current != raw and not cls._write_bytes_atomic(path, raw):
            return False
        try:
            mirror = _settings_mirror(typed)
            cls._set_settings_block(subdir_name, _settings_hash(raw),
                                    _settings_hash(mirror), mirror, current=block)
        except Exception as exc:
            # bin 已写成，镜像没刷成不是致命问题：下次 getSettings 会自愈
            _log.warning(f"setSettings({subdir_name}) 镜像刷新失败: {exc!r}")
        return True

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
        使用 (jar_mtime, png, png_mtime, png_size) 作为缓存键，避免重复读取 zip。

        缓存键**刻意不含 BML.json 的 mtime**：BML.json 里还存着设置的镜像
        （mdtData），游戏每改一次设置就会让它刷新；若拿 mtime 当键，每刷新一次
        都得重开几十 MB 的 mdt.jar 读 version.properties（实测 41~103 ms）。
        本方法的产物只受 icon_path 影响，而它已经体现在解析出来的 png 路径上。"""
        # 计算 png 路径与 mtime/size
        png = None
        png_mtime = 0
        png_size = 0
        bml_path = getPath(f"BML/.Mindustrys/{subdir_name}/BML.json")
        icon_path = None
        try:
            if os.path.isfile(bml_path):
                with open(bml_path, "r", encoding="utf-8") as f:
                    icon_path = (json.load(f) or {}).get("icon_path")
        except (OSError, ValueError, TypeError):
            pass
        # icon_path 为 null/空 → 写回默认图标
        if not icon_path:
            icon_path = cls.DEFAULT_ICON
            cls.setData(subdir_name, ["icon_path"], icon_path)
        # icon_path 指向的文件不存在或非有效图片 → 写回默认图标
        cand = getPath(icon_path) if not os.path.isabs(icon_path) else icon_path
        if os.path.isfile(cand) and cls._is_valid_image(cand):
            png = cand
        else:
            cls.setData(subdir_name, ["icon_path"], cls.DEFAULT_ICON)
            png = getPath(cls.DEFAULT_ICON)
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

        cache_key = (jar_mtime, png, png_mtime, png_size)
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
        - 图标来源（icon.png / icon_path 指向的文件）或 mdt.jar 变化 → 使缓存失效
        检测到变化时 emit on_game_changed({"type": "iconChanged", "game": ...})；
        QPixmaps 缓存的失效由主线程收到事件后处理（GUI 资源禁止跨线程操作）。"""
        for mdt in self.getMdts():
            bml_path = getPath(f"BML/.Mindustrys/{mdt}/BML.json")
            icon_path = None
            try:
                if os.path.isfile(bml_path):
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
            new_key = (jar_mtime, resolved, png_mtime, png_size)
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
            "javaPath": cls.FOLLOW
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
        if merged == file_data:
            return
        try:
            os.makedirs(os.path.dirname(data_path), exist_ok=True)
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, separators=(',', ':'), ensure_ascii=False)
        except Exception:
            pass


    @classmethod
    def pickJava(cls, javas):
        """从候选表里挑一个 Java：优先 17，其次最高版本；挑不出返回 None。

        候选表形如 [["C:/.../java.exe", "17.0.2"], ...]，有效性由探测方保证。
        实例解析、全局解析、Java 下载完成后的重选都走这一套口径。
        """
        best_path, best_major = None, -1
        for path, version in javas:
            try:
                major = int(str(version).split(".")[0])
            except ValueError:
                continue
            if major == 17:
                return path
            if major > best_major:
                best_path, best_major = path, major
        return best_path

    @classmethod
    def getMdtData(cls, subdir_name, settings):
        """返回指定子目录的 BML.json 内容，失败返回默认值。

        javaPath 取值语义：
            None           - 自动匹配（settings["javaPath"]=None 时占位，不写入 BML.json）
            "<:|follow|:>" - 跟随全局设置（写入 BML.json 的标识符）
            具体路径       - 已选定的 Java
        实例选定的具体路径失效（被卸载/移走）时改回 "<:|follow|:>" 写回，
        并立刻重扫一遍候选表再解析：Java 可能是用户中途装上的，沿用旧候选表
        会把“有 Java”当成“没有 Java”，白白多走一趟下载。
        """
        cls._retrieve_mdt_data(subdir_name)
        data_path = getPath(os.path.join(cls.base_dir, subdir_name, "BML.json"))
        data = {}
        if os.path.isfile(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        # 具体路径失效：改回 follow 写回，并重扫候选表（结果同步回全局 settings）
        java_path = data["javaPath"]
        if java_path and java_path != cls.FOLLOW and not javaManager.isJava(java_path):
            java_path = cls.FOLLOW
            cls.setData(subdir_name, ["javaPath"], cls.FOLLOW)
            javas = javaManager.getJavas()
            if javas:
                settings["javaPaths"] = javas

        # 解析 follow / None：全局选定的具体路径优先，否则在候选表里自动挑
        if java_path == cls.FOLLOW:
            java_path = settings["javaPath"]
        if java_path is None:
            java_path = cls.pickJava(settings["javaPaths"])

        if java_path and not javaManager.isJava(java_path):
            java_path = cls.FOLLOW
            cls.setData(subdir_name, ["javaPath"], cls.FOLLOW)
        data["javaPath"] = java_path
        return data

    @classmethod
    def getMdtRaw(cls, subdir_name):
        """读实例 BML.json 的原样字段，读不到返回 {}。

        与 getMdtData 的区别：getMdtData 会把 follow / None 解析成具体路径给启动用，
        这里要的是原始值——界面得知道用户当初选的是「跟随全局」还是某个具体 Java。
        """
        cls._retrieve_mdt_data(subdir_name)
        data_path = getPath(os.path.join(cls.base_dir, subdir_name, "BML.json"))
        if not os.path.isfile(data_path):
            return {}
        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ==================== 实例编辑 ====================

    def edit(self, name):
        """取某个实例的编辑入口：mdtManager.edit("原版-146").rename("我的原版")。

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
        不以点开头、不以点或空格结尾、不是 CON/COM1 之类保留设备名、长度不超 MAX_NAME_LEN。
        以点开头单独给 "dot"（下载页对它有专属文案），其余一律 "invalidName"。
        重名不在这里判——那要看目录与登记集合，用 name_conflict() / unique_name()。
        """
        name = str(name).strip()
        if not name or len(name) > cls.MAX_NAME_LEN:
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
        返回值一定不超 MAX_NAME_LEN：后缀要先占位，主体按剩余额度截断再拼，
        否则「32 字的名字已存在」会造出 35 字的目录名。
        """
        taken = self.taken_names() if existing is None else existing
        taken = {os.path.normcase(str(n)) for n in taken}
        name = str(name).strip()[:self.MAX_NAME_LEN]
        if os.path.normcase(name) not in taken:
            return name
        index = 1
        while True:
            suffix = "(%d)" % index
            candidate = name[:self.MAX_NAME_LEN - len(suffix)] + suffix
            if os.path.normcase(candidate) not in taken:
                return candidate
            index += 1

    class Editor:
        """单个实例的编辑接口（mdtManager.edit(name) 返回，勿直接构造）。

        读：exists()。写：set() / java() / icon() / rename() / group() / delete()，全部返回 self。

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
                return self.set("javaPath", self._scanner.FOLLOW)
            if not path or not javaManager.isJava(path):
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
            # 新名可能残着更早一次的缓存与图标检测基线（路径已失效），一并清掉
            self._scanner.invalidate_cache(new_name)
            self._sync_settings(old_name, new_name)
            self._scanner.on_game_changed.emit({"type": "nameChanged", "game": new_name, "old_name": old_name})
            return self._ok()

        def group(self, name=None):
            """把实例挪到分组：name 为空 → 默认分组。

            分组只活在 settings["gameList"] 这张表里（实例目录与 BML.json 都不记归属），
            所以这里改的只有它：先从旧组摘掉，再挂到目标组末尾。
            目标组是界面从这张表里选的，正常都在；万一不在就顺手建一个，
            免得实例从表里凭空消失（下一轮 checkGame 会把它当新游戏重报一次）。
            分组没变则原样返回，不动表也不发事件。
            成功后发 on_game_changed 的 groupChanged 事件，UI 侧按事件搬条目。
            """
            if not self.exists():
                return self._fail("notFound")
            name = name or self._scanner.DEFAULT_GROUP
            lists = self._scanner.settings["gameList"]
            old_name = ""
            for key, games in lists.items():
                if self.name in games:
                    old_name = key
                    break
            if old_name == name:
                return self._ok()
            for games in lists.values():
                while self.name in games:
                    games.remove(self.name)
            lists.setdefault(name, []).append(self.name)
            self._scanner.on_game_changed.emit({
                "type": "groupChanged", "game": self.name,
                "old_group": old_name, "group": name})
            return self._ok()

        def delete(self):
            """删除实例：连目录一起移除，并清掉 settings 里的兵记。

            三种「删不掉」各有自己的码：
                notFound    不是正式实例（目录没了，或只是下载中的半截目录）
                locked      实例正在运行（mdtLocker 握着目录句柄，系统拒绝删除）
                ioError     其它磁盘错误
            登记必须跟着清（gameList 各分组 + defaultGame 回退）：留着那笔登记，
            下一轮 checkGame 会把它当「目录不见了」再报一次 deleteGame。
            成功后发 on_game_changed 的 deleteGame 事件，UI 侧按事件移除条目。
            """
            if not self.exists():
                return self._fail("notFound")
            name = self.name
            try:
                shutil.rmtree(self.path)
            except PermissionError as exc:
                return self._fail("locked", exc)
            except OSError as exc:
                return self._fail("ioError", exc)
            self._scanner.invalidate_cache()
            self._scanner.invalidate_icon_pixmap(name)
            for games in self._scanner.settings["gameList"].values():
                while name in games:
                    games.remove(name)
            # defaultGame 指向它时回退到别的副本（副本列表缓存刚清过，重算就是实的）
            self._scanner.ensure_default_game()
            self._scanner.on_game_changed.emit({"type": "deleteGame", "game": name})
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
                # 目录名变了 → 图标来源路径跟着变，基线作废，下次检查静默重建
                self._icon_check_keys.pop(mdt, None)
                if mdt in setting:
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
            elif old_name is None:
                self.setData(mdt, ["name"], mdt)
                self._icon_check_keys.pop(mdt, None)
            # 2. 目录存在但不在 gameList → 新游戏
            if mdt not in setting:
                self.settings["gameList"].setdefault(self.DEFAULT_GROUP, []).append(mdt)
                self.on_game_changed.emit({"type": "newGame", "game": mdt})
            # 3. 图片检测：BML.json 的 icon_path 缺失或指向无效图片 → 写回默认并通知
            icon_path = data.get("icon_path", None)
            cand = getPath(icon_path) if icon_path and not os.path.isabs(icon_path) else icon_path
            if not (icon_path and os.path.isfile(cand) and self._is_valid_image(cand)):
                self.setData(mdt, ["icon_path"], self.DEFAULT_ICON)
                self._icon_check_keys.pop(mdt, None)   # 上面已发事件，别让下个周期重复报
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
            if self.settings["defaultGame"] is not None:
                self.settings["defaultGame"] = None
        elif self.settings["defaultGame"] not in mdts:
            self.settings["defaultGame"] = mdts[0]
        return self.settings["defaultGame"]