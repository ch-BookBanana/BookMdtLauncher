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

插件基类与 API 版本号。
"""

from ..utils.events import events
from ..utils.registry import registry

# 宿主 API 版本。落在 BMLCore 上的名字/签名保证向后兼容到同一个大版本内；
# 破坏性改动必须抬这个号，加载器再按插件声明的 api 范围决定收不收。
API_VERSION = "1.0"


class Plugin:
    """插件基类：声明元信息，实现 setup() / teardown()。

    加载器（还没写）会负责：实例化 → 调 setup() → 构建界面 → 卸载时按 id
    摘掉注册项与事件 → 调 teardown()。这里只把常用动作包一层，
    省得插件到处去写 registry.add / events.on。

    最小插件：

        from BMLCore import Plugin

        class Hello(Plugin):
            id = "com.example.hello"
            name = "Hello"

            def setup(self):
                self.add("core.setting.items", "greet", init=make_item,
                         section="core.setting.plugins", title="hello.greet")
    """

    # ── 元信息：子类覆盖 ──
    id = ""                 # 反向域名（com.example.hello），同时是注册表命名空间
    name = ""               # 显示名（插件管理界面用）
    version = "0.0.0"
    api = "1.x"             # 兼容的宿主 API 范围，加载器据此决定收不收

    # ── 生命周期：子类按需覆盖 ──

    def setup(self):
        """登记阶段：往扩展点里 add。

        此时**不要碰 Qt**：界面还没建，而且插件是在宿主启动期被加载的，
        构造到一半抛异常会很难定位（登记期的错误要能明说「哪个插件的哪一条」）。
        """

    def teardown(self):
        """卸载阶段。

        注册项与事件由加载器按 id 摘掉，这里只做它管不到的清理：
        停掉自己起的线程、关掉文件、删临时目录。
        """

    # ── 便捷动作 ──

    def add(self, point, name, **fields):
        """往扩展点登记一项，key 自动加本插件前缀。

            self.add("core.setting.items", "greet", init=..., section=..., title=...)
            # → registry.add("core.setting.items", "com.example.hello.greet", ...)

        前缀不只是防重名：卸载时按 'com.example.hello' 一趟前缀扫描就能把
        这个插件登记的全部条目摘干净。
        """
        return registry.add(point, f"{self.id}.{name}", **fields)

    def add_setting(self, name, cls, *, title, section="core.setting.plugins",
                    order=900, **fields):
        """往设置页加一项：给控件类就行，构造参数由宿主拼。

            from BMLCore import Plugin, Widgets

            class Hello(Plugin):
                id = "com.example.hello"
                def setup(self):
                    self.add_setting("greet", Widgets.Bool, title="hello.greet")

        section 默认 'core.setting.plugins'：设置页那个「插件」分组（装了插件就往
        那组里放）。想自己开一组，先登记一条容器再让条目指过去：

            self.add("core.setting.sections", "mine",
                     init=lambda b: Widgets.Section(b.parent, b.title, b.items),
                     order=200, title="hello.section")
            self.add_setting("greet", Widgets.Bool,
                             section="com.example.hello.mine", title="hello.greet")

        要更自由的构造（复合控件、带初值/信号绑定）就用 self.add(...) 自己给 init。
        """
        from ..utils.registry import simple
        return self.add("core.setting.items", name, init=simple(cls),
                        section=section, order=order, title=title, **fields)

    def add_qss(self, css, *, theme=None, order=100):
        """往全局样式表末尾追加一段 css。

            self.add_qss("QLabel#myTitle { color: #7aa2f7; }")

        theme：None = 两套主题都加，False = 只在深色，True = 只在浅色。
        片段排在主题文件之后，所以同名选择器以它为准 —— 能盖内置样式，
        但不必去改主题文件。换主题时会重新收一遍，不用自己监听。
        """
        return self.add("core.qss", "qss", qss=css, theme=theme, order=order)

    def add_tray(self, name, *, title, callback, order=100):
        """往系统托盘右键菜单里加一项，点了调 callback()。

            self.add_tray("about", title="hello.about", callback=self._about)

        title 是语言键：语言切换时托盘会照它重设文案，插件不用自己管。
        """
        from PySide6.QtGui import QAction

        def _init(b):
            act = QAction(b.title, b.parent)
            act.triggered.connect(lambda *_: callback())
            return act

        return self.add("core.tray.menu", name, init=_init, title=title, order=order)

    def on(self, event, callback):
        """订阅事件。名字原样传 —— 宿主的事件和别的插件的事件都这么订。"""
        return events.on(event, callback)

    def emit(self, event, *args):
        """广播自己的事件，名字自动加前缀，卸载时能整片摘掉。"""
        events.emit(f"{self.id}.{event}", *args)

    # ── 只读工具（取用宿主已挂载的全局工具）──

    # 本插件设置的默认值：子类覆盖。读不到的键回落到这里，不必到处兜 None。
    settings_defaults = {}

    @property
    def logger(self):
        """日志（自己加 '[插件id]' 前缀，便于在宿主日志里过滤）。"""
        return events.logger

    @property
    def settings(self):
        """本插件自己的设置格子（settings["plugins"][id]）。

            class Hello(Plugin):
                id = "com.example.hello"
                settings_defaults = {"volume": 50}

                def setup(self):
                    self.settings["volume"]                 # 50（没存过就是默认值）
                    self.settings["volume"] = 30            # 写值顺手存盘
                    self.settings.get("nope", "x")          # "x"

        给的是视图不是宿主 settings 本体：够不着别的键（不然插件把键名写错
        一个字就能改掉 language/theme），插件卸载时也按 id 摘得干净。
        存的位置见 utils/pluginSettings.py。
        """
        # 不用 __init__ 里初始化：插件子类不一定会调 super().__init__()
        view = getattr(self, "_settings_view", None)
        if view is None:
            from ..utils.pluginSettings import PluginSettings
            view = PluginSettings(self.id, self.settings_defaults)
            self._settings_view = view
        return view

    @property
    def lang(self):
        """翻译服务。"""
        return events.lang

    def log(self, msg, level="info"):
        """带插件名前缀的日志。"""
        getattr(events.logger, level, events.logger.info)(f"[{self.id}] {msg}")
