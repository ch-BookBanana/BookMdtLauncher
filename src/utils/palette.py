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

调色板：颜色写在两份主题 qss 顶部的 <colors> 块里，这里只负责读出来。

为什么颜色写在 qss 里
--------------------
颜色本来就该跟规则放在一起看：改深色面板的人打开 dark.qss，改色和改边框
是同一屏事。所以不另开 palette.json / .py 一份表，也不在 qss 里造变量语法
（Qt 的 QSS 不支持变量，替换器会让文件不再合法 CSS）。

这块只给 Python 侧取色
----------------------
QSS 规则继续写字面量，Qt 保持 100% 合法；表服务的是 QColor 要用的地方：
图标涂色（change_color）、自绘（DropHint）、内联状态字（"color: %s"）。
两边会各有一份字面量，这是这套方案的已知代价 —— 用 test_palette 卡住
「表里的值必须真的出现在同一个文件的规则里」，防止表悄悄跑偏。

值格式
------
`rgb(r, g, b)`、`#rrggbb`、`#aarrggbb`（alpha 在前，Qt 的顺序；不是 CSS 的
#rrggbbaa）。QColor 不认 rgb()，所以解析后统一成小写 hex；8 位原样交给
QColor，不自己拆 alpha 位。块坏了不内置第二份调色板：warn 一次、整表填
中性灰，界面明显不对劲但不崩，真值只存在 qss 里。
"""

import logging
import re
import threading

from .path_utils import getPath

_log = logging.getLogger("palette")

# 主题 → 样式表（解析器只从这里读颜色块）
STYLE = {False: "src/resources/styles/dark.qss",
         True: "src/resources/styles/light.qss"}

# 角色名（语义，不是颜色名）；两份 qss 的键集必须完全一致
KEYS = ("brand", "panel", "panel_alt", "text", "text_dim", "line",
        "danger", "warn", "ok", "icon", "icon_strong", "scrim")

# 解析失败时的兜底色：一眼能看出「调色板没读进来」，又不至于看不见字
NEUTRAL = "#808080"

_BLOCK = re.compile(r"/\*\s*<colors>(?P<body>.*?)</colors>\s*\*/", re.S)
_PAIR = re.compile(
    r"^\s*([a-z][a-z0-9_]*)\s*:\s*"
    r"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}"
    r"|rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\))\s*$")
_RGB = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)")
_HEX = re.compile(r"^#[0-9a-f]{6}(?:[0-9a-f]{2})?$")

_cache = {}
_lock = threading.Lock()


def _norm(value):
    """一行颜色字面量 → 小写 hex；认不出就抛 ValueError（不猜、不 clamp）。"""
    text = value.strip()
    m = _RGB.fullmatch(text)
    if m:
        rgb = tuple(int(x) for x in m.groups())
        if max(rgb) > 255:
            raise ValueError("rgb 分量超出 0–255：%r" % value)
        return "#%02x%02x%02x" % rgb
    text = text.lower()
    if not _HEX.fullmatch(text):
        raise ValueError("不是 qss 颜色字面量：%r" % value)
    return text


def _parse(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise ValueError("读不到 %s：%s" % (path, e))
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        raise ValueError("%s 里应当恰好一个 <colors> 块，实际 %d 个"
                         % (path, len(blocks)))
    table = {}
    for lineno, line in enumerate(blocks[0].splitlines(), 1):
        if not line.strip():
            continue
        m = _PAIR.match(line)
        if m is None:
            raise ValueError("%s 的 <colors> 第 %d 行不是 key: 颜色（%r）"
                             % (path, lineno, line.strip()))
        name, value = m.group(1), _norm(m.group(2))
        if name in table:
            raise ValueError("%s 的 <colors> 第 %d 行重复键 %r"
                             % (path, lineno, name))
        table[name] = value
    missing = [k for k in KEYS if k not in table]
    if missing:
        raise ValueError("%s 的 <colors> 缺键：%s" % (path, ", ".join(missing)))
    return table


def _neutral():
    return {k: NEUTRAL for k in KEYS}


def load(light):
    """某个主题的颜色表（按主题缓存；解析失败 warn 一次、退回中性灰）。"""
    light = bool(light)
    with _lock:
        table = _cache.get(light)
        if table is not None:
            return table
        try:
            table = _parse(getPath(STYLE[light]))
        except ValueError as e:
            _log.warning("调色板解析失败，颜色退回中性灰：%s", e)
            table = _neutral()
        _cache[light] = table
        return table


def get(name, light):
    """取一个角色色值（小写 hex）。未知角色直接 KeyError —— 这些是代码常量。"""
    table = load(light)
    if name not in table:
        raise KeyError("调色板没有角色 %r（可用的：%s）"
                       % (name, ", ".join(sorted(table))))
    return table[name]


def qcolor(name, light):
    """同 get，但直接给 QColor（change_color / QPainter 用）。"""
    from PySide6.QtGui import QColor
    return QColor(get(name, light))


def names(light):
    return tuple(sorted(load(light)))


def table(light):
    """整张表（副本）：测试与将来的只读视图用。"""
    return dict(load(light))


def reload():
    """丢掉缓存（改完 qss 不重启时用；测试也靠它复位）。"""
    with _lock:
        _cache.clear()
