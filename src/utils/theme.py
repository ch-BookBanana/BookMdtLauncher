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

主题服务：当前深浅 + 调色板取值 + 切换广播，三件事收在一个对象里。

- light       当前主题（True 浅色），运行时唯一真相；settings["theme"] 只管持久化
- get(name)   取色，缺省按当前主题（palette 只认 (name, light)，不碰全局）
- changed     Qt Signal(bool)：apply_theme 刷完 qss 后由 set() 发出

QSS 仍由宿主加载，本模块不碰样式表；订阅者收到 changed 时新配色已经生效。
"""

from PySide6.QtCore import QObject, Signal

from . import palette


class ThemeService(QObject):
    """当前主题 + 调色板入口。宿主建一个，登记到 core/theme 给插件用。"""

    changed = Signal(bool)          # 宿主侧：True 浅色（lighting(light) 的入参）
    name_changed = Signal(str)      # 插件侧：主题标识 "dark" / "light" / 将来的 "pink"

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._settings = settings
        raw = settings["theme"] if settings is not None else False
        if isinstance(raw, str):
            self._name = raw
            self._light = raw == "light"    # 自定义主题的明暗归属以后再按主题文件定
        else:
            self._light = bool(raw)
            self._name = "light" if self._light else "dark"
        self._applied = False

    @property
    def light(self):
        return self._light

    @property
    def name(self):
        """主题标识：现在只有 dark / light，将来可以扩展成自定义主题名。"""
        return self._name

    @property
    def applied(self):
        """apply_theme 是否已经广播过一次（启动期控件据此决定要不要补首帧）。"""
        return self._applied

    def set(self, light, name=None):
        """切到某个主题并广播。重复设置同一个值也会广播 —— 重刷 qss 之后
        订阅者需要重新取色，静默跳过反而会让图标停在旧色上。

        name 省略时按 light 推成 dark / light；将来自定义主题（pink.qss 之类）
        由 apply_theme 把主题名传进来即可，不用再动订阅方。
        """
        self._light = bool(light)
        self._name = str(name) if name else ("light" if self._light else "dark")
        self._applied = True
        try:
            self.changed.emit(self._light)
            self.name_changed.emit(self._name)
        except Exception:
            pass

    def get(self, name, light=None):
        """取色；light 省略时用当前主题。"""
        return palette.get(name, self._light if light is None else bool(light))

    def names(self, light=None):
        return palette.names(self._light if light is None else bool(light))

    def table(self, light=None):
        return palette.table(self._light if light is None else bool(light))
