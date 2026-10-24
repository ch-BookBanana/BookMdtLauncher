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

插件设置：每个插件一格，顶层分桶。

存哪儿
------
settings.json 顶层分两样：宿主的设置在 "core" 桶里，每个插件各占一格，
键就是插件 id：

    {
        "core":       {"language": "zh-CN", "theme": 0, ...},
        "example_hello": {"volume": 30}
    }

宿主代码仍按老写法 `settings["language"]` 读（见 utils/settings.py 的分流），
插件侧则一律走 self.settings 这个视图：它只认自己那一格的键。

为什么给视图而不是裸 dict
-------------------------
PluginSettings 是 MutableMapping 视图，本体是 settings["<id>"] 那一格：
  * **未声明的键写不进去**：写一个没 declare 过的键直接报错，防的是
    拼错键名（"voluem"）悄悄存下来、读的时候永远回默认值那类 bug；
  * 读不到就回默认值（默认值由插件 declare / settings_defaults 声明）；
  * 卸载时按 id 整格摘掉，不留残渣（见 forget）；
  * 读别人的桶走显式路径（other("core")），不把宿主配置混进自己的键空间。

跨桶读
------
插件可以读宿主（或别的插件）的桶，但要写成 `self.settings.other("core")`，
路径摆明面上；读不到就是空 dict，不会半路给个半死的对象。写别人的桶
同样允许（覆盖许可：防君子不防小人），但 core 桶的键仍由 schema 兜着。
"""

from collections.abc import MutableMapping

# 宿主自己的那桶（和 settings.py 的 CORE 是同一个名字）
CORE = "core"


class PluginSettings(MutableMapping):
    """一个插件自己的设置格子：settings["<id>"]。

        s = PluginSettings("example_hello", {"volume": 50})
        s["volume"]            # 50（没存过就是默认值）
        s["volume"] = 30       # 写值顺手存盘
        s["voluem"] = 10       # 未声明的键 → 直接报错
        s.declare("runs", 0)   # 声明一个新键（带默认值），之后才可写
        s.get("nope", "x")     # "x"
    """

    def __init__(self, pid, defaults=None, store=None):
        self.pid = pid
        self.defaults = dict(defaults or {})
        # store 是宿主 settings 本体，注入只为测试；平时走 events.settings
        self._store = store

    # ── 取自己那一格 ──

    @property
    def _settings(self):
        if self._store is not None:
            return self._store
        from .events import events
        return events.settings

    def _bucket(self, create=False):
        """settings["<id>"] 那一格；create=False 用于纯读路径。"""
        settings = self._settings
        bucket = getattr(settings, "bucket", None)
        if bucket is not None:
            return bucket(self.pid, create=create)
        # 兜底：注进来的 store 是不带桶的普通 dict（老测试写的形状）
        cell = settings.get(self.pid) if hasattr(settings, "get") else None
        if create and isinstance(settings, dict):
            if not isinstance(cell, dict):
                cell = settings[self.pid] = {}
        return cell if isinstance(cell, dict) else {}

    def other(self, owner):
        """另一个 owner 的桶（读宿主配置 / 别的插件的发布设置时用）。

            self.settings.other("core")["theme"]     # 只看不改
            self.settings.other("example_more")["volume"]

        桶名必须存在（"core" 或某个插件 id），否则抛 KeyError —— 拼错桶名
        不会被兜成空 dict 悄悄吞掉。
        """
        settings = self._settings
        if owner == CORE:
            if hasattr(settings, "core"):
                return settings.core
            cell = settings.get(CORE) if hasattr(settings, "get") else None
            if isinstance(cell, dict):
                return cell
            if isinstance(settings, dict):
                return settings.setdefault(CORE, {})
            raise KeyError(f"没有 {CORE!r} 桶：宿主 settings 还没建起来就取？")
        bucket = getattr(settings, "bucket", None)
        cell = bucket(owner, create=False) if bucket is not None else (
            settings.get(owner) if hasattr(settings, "get") else None)
        if not cell:
            raise KeyError(f"没有 {owner!r} 桶：这个插件没存过设置，或名字拼错了")
        return cell

    # ── 声明 ──

    def declare(self, key, default=None):
        """声明一个设置键（带默认值）：之后 s[key] 才能写。

        settings_defaults 里的键在视图构造时就自动声明过了；运行中要加新键，
        在这里声明一次即可（值只是默认值，不会立刻写进格子里）。
        """
        self.defaults.setdefault(key, default)
        return key

    def declared(self, key):
        return key in self.defaults

    # ── MutableMapping ──

    def __getitem__(self, key):
        cell = self._bucket(create=False)
        if key in cell:
            return cell[key]
        if key in self.defaults:
            return self.defaults[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key not in self.defaults:
            raise KeyError(
                f"插件 {self.pid!r} 没声明设置键 {key!r}：先在 "
                f"settings_defaults 里写默认值，或 self.settings.declare({key!r}, 默认值)")
        self._bucket(create=True)[key] = value
        self.save()

    def __delitem__(self, key):
        """删一个键：已存过的从格子里删，只在默认值里的从默认值里删。"""
        cell = self._bucket(create=False)
        if key in cell:
            del cell[key]
            self.save()
            return
        if key in self.defaults:
            del self.defaults[key]
            self.save()
            return
        raise KeyError(key)

    def clear(self):
        """清空这一格：已存值全删、默认值也清掉。"""
        cell = self._bucket(create=False)
        if cell:
            cell.clear()
        self.defaults.clear()
        self.save()

    def __iter__(self):
        # 默认值在前、后来加的键在后，同一批键的顺序在两次遍历间稳定
        seen = list(self.defaults)
        for key in self._bucket(create=False):
            if key not in self.defaults:
                seen.append(key)
        return iter(seen)

    def __len__(self):
        return len(list(iter(self)))

    def __repr__(self):
        return "<PluginSettings %s %r>" % (self.pid, self.as_dict())

    # ── 便捷动作 ──

    def as_dict(self):
        """默认值 + 已存值合并后的普通 dict（调试、写日志用）。"""
        out = dict(self.defaults)
        out.update(self._bucket(create=False))
        return out

    def pop(self, key, *default):
        """删键并返回值。"""
        try:
            value = self[key]
        except KeyError:
            if default:
                return default[0]
            raise
        del self[key]
        return value

    def save(self):
        """立刻存盘。写值时会自动调；想攒一批再写就手动控制。"""
        try:
            from .events import events
            events.saveSettings()
        except Exception:
            # 存盘失败不该把插件正在做的事一起弄崩：退出时宿主还会整体存一次
            pass

    def forget(self):
        """整格删掉本插件的设置（重置 / 彻底卸载时用）。"""
        settings = self._settings
        drop = getattr(settings, "drop_bucket", None)
        if drop is not None:
            drop(self.pid)
        else:
            cell = self.pid in settings if hasattr(settings, "__contains__") else False
            if cell and hasattr(settings, "__delitem__"):
                del settings[self.pid]
        self.save()


def view(pid, defaults=None):
    """建一个插件设置视图。"""
    return PluginSettings(pid, defaults)


def forget(pid):
    """按 id 删掉某插件的整格设置。

    注意加载器的 unload **不**调它：卸载/停用插件时设置该留着，
    再启用回来配置还在。只有「彻底不要这个插件了」才摘。
    """
    PluginSettings(pid).forget()
