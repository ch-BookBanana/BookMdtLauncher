# -*- coding: utf-8 -*-
"""一页看懂 BPoint：注册点自带四件套。

    条目表   add / get / set / remove / keys
    归属     by=登记人；unload(owner) 整片摘掉
    通知     watch(cb)：条目增删改时回调
    产物槽   bind / built：把活对象挂在条目上

`set` 是压栈，不是覆盖：顶掉的那份留着，顶的人卸载时自动还回。
所有登记都在加载会话里暂存，插件加载成功才提交（失败自动回滚）。
"""

from BMLCore import BMLPlugin, register


class PointDemo(BMLPlugin):
    id = "example_point"
    name = "点示例"

    def __init__(self, host):
        super().__init__(host)

        me = register()

        # ① 自己的子点：条目是普通值
        self.point = me.add("log", type="core/point", entry="core/value")

        # ② 条目：add 一次，之后按 key 取到同一个对象
        self.point.add("count", value=0)
        self.point.get("count").set(1)
        self.point.get("count").set(2)

        # ③ 通知：条目有任何增删改都会回调 key
        self.point.watch(lambda key: self.log("条目变了：%s" % key))
        self.point.add("mode", value="auto")

        # ④ 产物槽：把活对象挂到条目上，别的插件按 key 取回
        self.point.add("service")
        self.point.bind("service", obj=self)
        assert self.point.built("service")["obj"] is self

        # ⑤ 嵌套：子点上再挂子点（都是点对象，不是字符串路径）
        nested = me.add("settings", type="core/point", entry="core/value")
        nested.add("java").set(1)
        self.log("嵌套值：%s" % nested.get("java").get())

    def on_ready(self):
        """加载会话已经提交，这时演示覆盖栈/归属。"""
        # 别人顶掉 count：新的一份压栈顶，旧值还在
        self.point.set("count", value=99, owner="another_plugin")
        self.log("被顶掉后：%s" % self.point.get("count").value)

        # 顶的人卸载：自动还回原来那份
        self.point.unload("another_plugin")
        self.log("别人卸载后：%s" % self.point.get("count").value)
