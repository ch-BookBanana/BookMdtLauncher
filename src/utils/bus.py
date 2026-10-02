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
控件在自己的 __init__ 里调 bus.bind(self)，带 lighting / langing 的控件即自动连上。
每个钩子都过一层订阅垫片（_Sub）：垫片挂在控件下做子对象，替控件兜异常、
也替控件担生命周期——控件一销毁，垫片跟着销毁、连接随之断开，主题/语言再变化
也不会打到已经不存在的控件上（那正是 lighting failed + AttributeError 刷屏的根源）。
"""

import logging

from PySide6.QtCore import QObject, Signal
from shiboken6 import isValid

_log = logging.getLogger("bus")


class _Sub(QObject):
    """订阅垫片：替控件兜异常，也替控件担生命周期。

    不能把闭包直接连上总线：Qt 只认 QObject 的生死，控件（C++ 对象）被销毁后连接
    还在，主题/语言一切换就会打到已经没了的控件上——那时它的子控件属性早没了，
    报出来就是 AttributeError（比如 btn_close）。垫片挂在控件下做子对象，控件销毁时
    跟着销毁、连接随之断开；万一还有漏网的连接，isValid 那一关也拦得住。
    """

    def __init__(self, widget, name, fn):
        super().__init__(widget)
        self._widget = widget
        self._label = f"{type(widget).__qualname__}.{name}"
        self._fn = fn

    def fire(self, *args, **kwargs):
        try:
            if not isValid(self._widget):
                return
            return self._fn(*args, **kwargs)
        except Exception:
            _log.error(f"{self._label} failed", exc_info=True)


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
                getattr(self, signal).connect(self._sub(widget, name).fire)
                bound.add(name)
        # 后创建的控件补一次主题，避免图标停在默认色
        if self.light is not None and "lighting" in bound:
            self._sub(widget, "lighting").fire(self.light)
        return widget

    def _sub(self, widget, name):
        """给控件的一个钩子配个垫片；强引用挂在控件自己身上，随控件一起走。"""
        sub = _Sub(widget, name, getattr(widget, name))
        widget.__dict__.setdefault("_bus_subs", []).append(sub)
        return sub


bus = _Bus()
