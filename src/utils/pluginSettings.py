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

插件设置：存放位置与给插件看的那一格视图。

存哪儿
------
就存在宿主 settings.json 的 "plugins" 里，一格一个插件：

    "plugins": {
        "com.example.hello": {"volume": 30}
    }

为什么不给每个插件单独一个 settings.json：宿主的设置读取、合并、损坏备份
（badSettings）、退出保存都只认这一个文件，插件设置另开一套就得把这些
逻辑再写一遍；而且「设置在哪」会变成插件作者要关心的第二件事。

settings.json 的合并规则只收默认值里已有的键（用来淘汰已删掉的设置项），
所以 "plugins" 的默认值是**空 dict** —— 见 main.py 的 _merge_settings：
空 dict 默认值按开放映射处理，里面的键宿主不认识也整片收下。

为什么给视图而不是原生 dict
--------------------------
PluginSettings 是 MutableMapping 视图，本体是 settings["plugins"][id]：
  * 插件够不着别的键 —— 否则一个插件把键名写错一个字就能改掉 language/theme；
  * 卸载时按 id 一格摘掉，不留残渣（见 forget）；
  * 默认值由插件声明，读不到就回默认值，不必到处兜 None。
"""

from collections.abc import MutableMapping

# 宿主 settings 里放插件设置的那一格
NAMESPACE = "plugins"


class PluginSettings(MutableMapping):
    """一个插件自己的设置格子：settings["plugins"][<id>]。

        s = PluginSettings("com.example.hello", {"volume": 50})
        s["volume"]            # 50（没存过就是默认值）
        s["volume"] = 30       # 写值顺手存盘
        s.get("nope", "x")     # "x"
    """

    def __init__(self, pid, defaults=None, store=None):
        self.pid = pid
        self.defaults = dict(defaults or {})
        # store 是宿主 settings 本体，注入只为测试；平时走 events.settings
        # （events 是随时可用的模块级单例，取它不需要宿主已经建好窗口）。
        self._store = store

    # ── 取自己那一格 ──

    @property
    def _settings(self):
        if self._store is not None:
            return self._store
        from .events import events
        return events.settings

    def _cell(self, create=True):
        """settings["plugins"][pid]，必要时补出来。

        create=False 用于纯读路径：读一个不存在的插件设置不该改宿主 settings。
        文件被手改坏时（plugins 不是 dict）也走同一条兜底，不让插件崩在读取上。
        """
        settings = self._settings
        plugins = settings.get(NAMESPACE)
        if not isinstance(plugins, dict):
            if not create:
                return {}
            plugins = settings[NAMESPACE] = {}
        cell = plugins.get(self.pid)
        if not isinstance(cell, dict):
            if not create:
                return {}
            cell = plugins[self.pid] = {}
        return cell

    # ── MutableMapping ──

    def __getitem__(self, key):
        cell = self._cell(create=False)
        if key in cell:
            return cell[key]
        if key in self.defaults:
            return self.defaults[key]
        raise KeyError(key)

    def __setitem__(self, key, value):
        self._cell()[key] = value
        self.save()

    def __delitem__(self, key):
        cell = self._cell(create=False)
        if key not in cell:
            raise KeyError(key)
        del cell[key]
        self.save()

    def __iter__(self):
        # 默认值在前、后来加的键在后，同一批键的顺序在两次遍历间稳定
        seen = list(self.defaults)
        for key in self._cell(create=False):
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
        out.update(self._cell(create=False))
        return out

    def save(self):
        """立刻存盘。

        写值时会自动调；想攒一批再写就手动控制（写值那次已经存过了，
        这里重复调只是多写一次文件，不会写坏）。
        """
        try:
            from .events import events
            events.saveSettings()
        except Exception:
            # 存盘失败不该把插件正在做的事一起弄崩：宿主的 saveSettings
            # 自己记日志，这里连 events 都取不到（还没 bind）时也无所谓 ——
            # 退出时宿主还会整体存一次。
            pass

    def forget(self):
        """删掉本插件的整格设置（重置 / 彻底卸载时用）。"""
        settings = self._settings
        plugins = settings.get(NAMESPACE)
        if isinstance(plugins, dict) and self.pid in plugins:
            del plugins[self.pid]
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
