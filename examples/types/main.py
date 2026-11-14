# -*- coding: utf-8 -*-
"""自定义类型：类上的 init 声明成员，实例化后收进 self.init[名字]。

万物皆 BType（像 QObject）：
    core/type   底座
    core/point  注册点（收条目）
    core/signal 包一层 Qt Signal
    core/value  包一个标量

类上的 init 是**声明**（实例不会覆盖它）；实例的成员在 self.init 里，
声明本身备份在 self._init_def：

    inst = Counter(name="...")
    inst.init["value"]        # BValue
    inst.init["changed"]      # BSignal
"""

from BMLCore import BMLPlugin, BTypes, register


@BTypes.new("example/types/counter")
class Counter(BTypes.get("core/type")):
    """计数器：一个值 + 一个变更信号，成员由 init 自动造好。"""

    init = {
        "value": "core/value",
        "changed": "core/signal",
    }

    def add(self, n):
        self.init["value"].set(self.init["value"].get() + n)
        self.init["changed"].emit(self.init["value"].get())


# 循环依赖在「登记类型」时就被拒绝（照抄下面会报错）：
#
# @BTypes.new("example/types/selfloop")
# class SelfLoop(BTypes.get("core/type")):
#     init = {"me": "example/types/selfloop"}
# → ValueError: 类型成员循环依赖：example/types/selfloop → example/types/selfloop


class TypesDemo(BMLPlugin):
    id = "example_types"
    name = "类型示例"

    def __init__(self, host):
        super().__init__(host)

        # ① 直接造实例：成员自动就位（value 默认 None，先给初值）
        self.counter = Counter(name="example_types.counter")
        self.counter.init["value"].set(0)
        self.counter.init["changed"].connect(
            lambda v: self.log("counter 变成 %s" % v))
        self.counter.add(1)
        self.counter.add(2)

        # ② 注册表也能收自定义类型：挂一个「条目类型是 Counter」的子点
        counters = register().add(
            "counters", type="core/point", entry="example/types/counter")
        demo = counters.add("demo")
        demo.init["value"].set(10)
        self.log("注册表里的计数器：%s" % demo.init["value"].get())
