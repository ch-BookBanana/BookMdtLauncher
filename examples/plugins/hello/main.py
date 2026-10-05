# -*- coding: utf-8 -*-
"""最小插件示例。

放进 BML/plugins/hello/（或打包成 hello.zip 丢进 BML/plugins/）就能被加载。
插件只能 import BMLCore —— import src.* 或 main 会被加载器当场拦下。
"""

from BMLCore import Plugin, Widgets, getPath


class Hello(Plugin):
    # 元信息也可以只写在 plugin.json 里；两处都写时以清单为准。
    id = "com.example.hello"
    name = "Hello"
    version = "1.0.0"
    api = "1.x"

    # 本插件设置的默认值：读不到的键回落到这里，不必到处兜 None。
    # 真正存的位置是宿主 settings.json 的 "plugins" 里自己那一格。
    settings_defaults = {"greet": True}

    def setup(self):
        """登记阶段：往扩展点里加东西。这里不要碰 Qt —— 界面还没建。"""

        # 文案来自本插件自己的语言包 langs/zh-CN.json；
        # 插件语言包还能盖掉内置的键（想改宿主某句文案，直接写那个键就行）。
        self.add_setting("greet", Widgets.Bool, title="hello.greet", order=900)

        # 自己的资源用 ${plugin}/ 取：不写死自己叫什么、也不写死装在哪儿，
        # 换成 zip 分发、换个 id、换个安装目录都不用改代码。
        # 取到的是绝对路径 —— ${plugin} 只在加载期间有效，
        # 运行期才要用的资源必须在这里先取好。
        self._icon = getPath("${plugin}/assets/icon.png")

        # 自己的设置：够不着宿主的键（写 "language" 也只是写在插件自己那格里），
        # 写值顺手存盘。视图是 MutableMapping，get/items/del 都能用。
        if self.settings.get("greet"):
            self.settings["seen"] = self.settings.get("seen", 0) + 1

        self.on("com.example.hello.ping", self._on_ping)
        self.log(f"已登记 1 个设置项（第 {self.settings['seen']} 次启动）")

    def teardown(self):
        """卸载阶段：注册项与事件由加载器按 id 摘掉，这里只做它管不到的清理。"""
        self.log("已卸载")

    def _on_ping(self, *args):
        self.log(f"收到 ping: {args}")
