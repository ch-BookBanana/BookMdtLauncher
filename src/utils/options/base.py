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

设置项控件的统一接口
====================
一个设置项控件对外只有三件事，其它（长什么样、说什么语言、深色浅色）都是外观：

    value()         界面上现在的值
    set_value(v)    把值摆到界面上 —— **静音**：不发 push，不然回写会绕回来
    refresh()       从数据源重新读一次；默认实现 = set_value(source.get())

    push            Signal —— 只在「用户真的动了界面」时发

数据源也当成一个接口：get() / set(v)，最好还能通知变化（三选一即可）

    watch(fn)            宿主设置（settings.Settings）
    value_changed.connect(fn)   v3 设置条目（BValue）
    都是字典就用 MappingSource 包一层

两边用 bind(widget, source) 接起来：灌初值、双向同步、外部改动走 refresh()。
这样「设置项控件」和「它背后的存储」互不认识，任何实现这三个方法的控件都能用，
任何能读能写的对象都能当源 —— 加一种控件、换一种存储都不用改另一边。
"""


class SettingItem:
    """值型设置项控件的接口（Bool / Slider / Combo 都实现它）。

    子类只需要写 value() / set_value()；refresh() 这里给默认实现。
    注意 set_value 必须是静音的 —— 它就是「把外部值摆上来」这条路，
    自己再发一次 push 会让「外部改动 → refresh → push → 回写」绕成环。
    """

    source = None          # bind() 时挂上的数据源

    def value(self):
        """界面上现在的值。"""
        raise NotImplementedError

    def set_value(self, value):
        """把值摆到界面上，不发 push。"""
        raise NotImplementedError

    def refresh(self):
        """从数据源重新读一次。没有源时什么都不做（返回 None）。"""
        source = self.source
        if source is None:
            return None
        return self.set_value(source.get())


class MappingSource:
    """把 dict / Settings 包成数据源。

        bind(Widgets.Bool(page, "core.setting.xxx"), MappingSource(events.settings, "theme"))

    mapping 自带 watch(fn) 时顺手接上（settings.Settings 就有），
    这样别处改了值，界面会自己 refresh。
    """

    def __init__(self, mapping, key, watch=None):
        self.mapping = mapping
        self.key = key
        self._watch = watch if watch is not None else getattr(mapping, "watch", None)

    def get(self):
        return self.mapping[self.key]

    def set(self, value):
        self.mapping[self.key] = value

    def watch(self, fn):
        if callable(self._watch):
            self._watch(fn)
        return fn


def bind(widget, source):
    """把设置项控件接到数据源上，返回这个控件。

    做三件事：灌初值（静音）、把用户的改动写回源、源变了让界面 refresh。
    控件侧的约定只有 value() / set_value() / refresh() 和 push —— 不认具体类；
    源侧的约定只有 get() / set()，外加 watch() 或 value_changed 任选其一。
    """
    widget.source = source
    widget.refresh()
    push = getattr(widget, "push", None)
    if push is not None:
        def _write(value):
            source.set(value)
            # 条目可以声明 on_change：写完值再干点别的（切语言、落盘、通知）
            hook = getattr(source, "on_change", None)
            if callable(hook):
                hook(value)

        push.connect(_write)
    changed = getattr(source, "value_changed", None)      # v3 条目（BSignal）
    if changed is not None and hasattr(changed, "connect"):
        changed.connect(lambda *_: widget.refresh())
    watch = getattr(source, "watch", None)                # 宿主设置（Settings）
    if callable(watch):
        watch(lambda *_: widget.refresh())
    return widget
