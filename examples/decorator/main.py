# -*- coding: utf-8 -*-
"""装饰器语法：用 @registrar(...).connect() 订阅「某个值变化」。

路径用 `$` 串下去（`&` / `#` 也行），最后一段可以是「条目.属性」：

    settings$a$b$c.value_changed
    ↑ 点链（自己的子点）    ↑ 条目的 value_changed 信号成员

被装饰的函数就是回调；不需要手动 connect，也不用管 BSignal 在哪。
"""

from BMLCore import BMLPlugin, register, registrar


class Decor(BMLPlugin):
    id = "example_decorator"
    name = "装饰器示例"

    def __init__(self, host):
        super().__init__(host)

        # 搭一条 settings → launcher → java 的点链
        me = register()
        settings = me.add("settings", type="core/point", entry="core/point")
        launcher = settings.add("launcher", type="core/point", entry="core/point")
        java = launcher.add("java", type="core/point", entry="core/value")
        self.select_java = java.add("select_java", type="core/value")

        # 值变化 → 回调（装饰器订阅）
        @registrar("settings$launcher$java$select_java.value_changed").connect()
        def on_select_java(value=None):
            self.log("select_java 变成 %s" % value)

    def on_ready(self):
        self.select_java.set("jdk17")     # 触发上面的回调
        register("core/log").info("decorator 示例就绪：%s" % self.select_java.get())
