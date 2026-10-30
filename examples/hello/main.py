# -*- coding: utf-8 -*-
"""最小插件：register() 拿到自己的点，往里挂子点、写值、发信号。

读这个文件只需要记住三件事：

    register()                          当前 owner 自己的注册点（插件加载期=你）
    point.add(名字, type="core/point",  在自己的点下挂子点；entry= 声明它收什么类型
              entry="core/value")
    sub.add("名字")                     子点上加条目（同一个名字永远是同一个对象）

宿主（core）手下登记的点，用 `register().get("core/tools")` 这样取 ——
名字是子项 key，不存在"往别的空间写"这种字符串口子。
"""

from BMLCore import BMLPlugin, register


class Hello(BMLPlugin):
    id = "example_hello"
    name = "你好世界"

    def __init__(self, host):
        super().__init__(host)

        me = register()                       # ① 自己的点

        # 启动器内置功能：register("名字") 直接拿到包装好的服务
        self.host_log = register("core/log")
        self.host_lang = register("core/lang")
        self.host_conf = register("core/settings")

        parts = me.add("parts", type="core/point", entry="core/value")
        parts.add("greeting").set("你好")

        bus = me.add("signals", type="core/point", entry="core/signal")
        bus.add("welcome").connect(self._on_welcome)

        self.host_log.info("greeting = %s" % me.get("parts").get("greeting").get())
        self.host_log.info("宿主主题 = %s" % self.host_conf.get("theme"))

    def _on_welcome(self, who):
        self.host_log.info("欢迎 %s" % who)

    def on_ready(self):
        register().get("signals").get("welcome").emit("Mindustry 玩家")
