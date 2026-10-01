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

全局总线：主题/语言变化时由各控件自己订阅刷新，主逻辑不再逐层下发。
控件在自己的 __init__ 里调 bus.bind(self)，带 lighting / langing 的控件即自动连上；
Qt 的连接绑定接收者生命周期，控件销毁时自动断开，不必手动清理。
"""

import logging

from PySide6.QtCore import QObject, Signal

_log = logging.getLogger("bus")


class _Bus(QObject):
    theme_changed = Signal(bool)   # 主题切换：light=True 浅色 / False 深色
    lang_changed = Signal()        # 语言切换

    HOOKS = {"lighting": "theme_changed", "langing": "lang_changed"}

    def __init__(self):
        super().__init__()
        self.light = None          # 最后一次主题状态，控件接上总线时立即对齐

    def set_theme(self, light):
        self.light = light
        self.theme_changed.emit(light)

    def set_lang(self):
        self.lang_changed.emit()

    def bind(self, widget):
        """把 widget 的 lighting / langing 接到总线；重复调用只连一次。"""
        bound = widget.__dict__.setdefault("_bus_bound", set())
        for cls in type(widget).__mro__:
            for name, attr in vars(cls).items():
                signal = self.HOOKS.get(name)
                if not signal or name in bound or not callable(attr):
                    continue
                getattr(self, signal).connect(self._guard(widget, name, getattr(widget, name)))
                bound.add(name)
        # 后创建的控件补一次主题，避免图标停在默认色
        if self.light is not None and "lighting" in bound:
            self._guard(widget, "lighting", widget.lighting)(self.light)
        return widget

    def _guard(self, widget, name, fn):
        """包一层兜底：单个控件刷新失败只记日志，不影响其它控件。"""
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                _log.error(f"{type(widget).__qualname__}.{name} failed", exc_info=True)
        return wrapper


bus = _Bus()
