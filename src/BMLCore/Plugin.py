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
                self.add("core.setting.items", "greet", init=make_item, group="plugins",
                         title="hello.greet")
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

            self.add("core.setting.items", "greet", init=..., group=..., title=...)
            # → registry.add("core.setting.items", "com.example.hello.greet", ...)

        前缀不只是防重名：卸载时按 'com.example.hello' 一趟前缀扫描就能把
        这个插件登记的全部条目摘干净。
        """
        return registry.add(point, f"{self.id}.{name}", **fields)

    def add_setting(self, name, cls, *, title, group="plugins", order=900, **fields):
        """往设置页加一项：给控件类就行，构造参数由宿主拼。

            from BMLCore import Plugin, Widgets

            class Hello(Plugin):
                id = "com.example.hello"
                def setup(self):
                    self.add_setting("greet", Widgets.Bool, title="hello.greet")

        group 默认 'plugins'：设置页会把它单独归到末尾，不和内置项混排。
        要更自由的构造（复合控件、带初值/信号绑定）就用 self.add(...) 自己给 init。
        """
        from ..utils.registry import simple
        return self.add("core.setting.items", name, init=simple(cls),
                        group=group, order=order, title=title, **fields)

    def on(self, event, callback):
        """订阅事件。名字原样传 —— 宿主的事件和别的插件的事件都这么订。"""
        return events.on(event, callback)

    def emit(self, event, *args):
        """广播自己的事件，名字自动加前缀，卸载时能整片摘掉。"""
        events.emit(f"{self.id}.{event}", *args)

    # ── 只读工具（取用宿主已挂载的全局工具）──

    @property
    def logger(self):
        """日志（自己加 '[插件id]' 前缀，便于在宿主日志里过滤）。"""
        return events.logger

    @property
    def settings(self):
        """设置读取：settings["plugins"][id][...] 还没铺，先别依赖写。"""
        return events.settings

    @property
    def lang(self):
        """翻译服务。"""
        return events.lang

    def log(self, msg, level="info"):
        """带插件名前缀的日志。"""
        getattr(events.logger, level, events.logger.info)(f"[{self.id}] {msg}")
