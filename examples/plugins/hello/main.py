# -*- coding: utf-8 -*-
"""最小插件示例。

放进 BML/plugins/hello/ 就能被加载（BML/ 在 exe 旁边）。
插件只能 import BMLCore —— import src.* 或 main 会被加载器当场拦下。
"""

from BMLCore import Plugin, Widgets


class Hello(Plugin):
    # 元信息也可以只写在 plugin.json 里；两处都写时以清单为准。
    id = "com.example.hello"
    name = "Hello"
    version = "1.0.0"
    api = "1.x"

    def setup(self):
        """登记阶段：往扩展点里加东西。这里不要碰 Qt —— 界面还没建。"""

        # 往设置页加一项：给控件类就行，构造参数由宿主拼。
        # group 默认 'plugins'，设置页会把它单独归到末尾，不和内置项混排。
        self.add_setting("greet", Widgets.Bool, title="Hello（插件示例）", order=900)

        # 订阅事件。名字原样 —— 宿主的事件和别的插件的事件都这么订。
        # （宿主目前还没有 pagesReady 这个事件，这里只是示范写法；
        #   发一个不存在的事件名不会报错，只是没人收到。）
        self.on("com.example.hello.ping", self._on_ping)

        self.log("已登记 1 个设置项")

    def teardown(self):
        """卸载阶段：注册项与事件由加载器按 id 摘掉，这里只做它管不到的清理。"""
        self.log("已卸载")

    def _on_ping(self, *args):
        self.log(f"收到 ping: {args}")
