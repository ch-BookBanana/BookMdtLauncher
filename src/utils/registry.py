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

扩展点注册中心：**先登记，后构建**。

为什么要有它
------------
界面此前各自造了一套注册方法，签名互不相同：有的收类、有的收实例、有的连参数
顺序都不一样（Download.Main.add_page / Setting.Main.add_page / FloatingStack.add_page…）。
结果是「加一个页面 / 一个下载源 / 一个设置项」每次都要去改那个界面的源码。这里把
登记这件事收成一处，界面只负责 declare 自己的扩展点、再从里面取条目自己构造。

为什么分两个阶段
----------------
1. **登记期不碰 Qt**。重复 key、字段拼错、缺必填，这些都能在没有窗口的时候查出来，
   报的是「哪个扩展点的哪个条目错了」，而不是构造到一半的 AttributeError。
2. **构建期顺序显式**。谁先被 import、谁先 new 都不再决定顺序，order 说了算。
3. **加载顺序与界面创建解耦**。插件加载完 ≠ 界面已构建（GameManage 就是点开才建），
   登记只要全部完成于构建之前即可。

数据结构
--------
    {
        "core.pages": {
            "__registrant__": "core",
            "__kind__":       "class",
            "__fields__":     ("cls", "title", "icon", "order", "default"),
            "__required__":   ("cls", "title"),
            "__doc__":        "主窗口左栏导航页",

            "core.start":    {"cls": Start, "title": ..., "order": 10},
            "com.example.hello.main": {"cls": HelloPage, "order": 100},
        },
    }

* 保留键一律 `__xxx__`；条目 key 一律 `<namespace>.<name>` 且不得以 `__` 开头，
  两组键因此永不打架（add() 会挡住越界的 key）。
* 条目的 namespace 既是「谁登记的」，也是卸载/回滚时的摘除依据；
  **不要用 key.split(".")[0] 求它** —— `core.download.sources` 的条目
  `core.origin` 属于 `core`，而插件的 `com.example.hello.main` 属于
  `com.example.hello`，只有按最后一段切才对。

边界
----
本模块只做「登记 / 校验 / 查询」，**不含任何 Qt 代码、不负责构造控件**。
谁来 new、传什么参数，是拥有该扩展点的界面自己的事；否则这里会变成第二个
「什么都知道」的上帝对象。
"""

__all__ = ["RegistryError", "Entry", "Registry", "registry", "DEFAULT_ORDER"]

# 条目没写 order 时排在这里：够小，自定义项默认落在内置项之后
DEFAULT_ORDER = 100

# 扩展点块里的保留键（扩展点自身的元信息，不是条目）
_RESERVED = ("__registrant__", "__kind__", "__fields__", "__required__", "__doc__")


class RegistryError(Exception):
    """注册表用法错误：扩展点未声明、字段越界、key 重复或格式不对。"""


def _namespace_of(key):
    """条目 key → 命名空间（最后一段之前的部分）。"""
    return key.rpartition(".")[0]


def _is_entry_key(key):
    """条目 key 必须是 <namespace>.<name>：两段以上、各段非空、不以 __ 开头。"""
    if not isinstance(key, str) or key.startswith("__"):
        return False
    parts = key.split(".")
    return len(parts) >= 2 and all(parts)


class Entry:
    """一个登记项：key 拆出来的身份 + 该扩展点 schema 下的字段。

    字段既可以用 e.cls 直读（拼错会给出「有哪些字段」的提示），
    也可以用 e.get("cls", 默认值)。
    """

    __slots__ = ("key", "namespace", "name", "fields", "_point", "_registrant")

    def __init__(self, point, key, registrant, fields):
        self._point = point
        self._registrant = registrant
        self.key = key
        self.fields = fields
        ns, _, name = key.rpartition(".")
        self.namespace = ns or registrant
        self.name = name or key

    def __getattr__(self, item):
        # __slots__ 里的字段正常查找就命中了，走不到这里；能走到说明是在要扩展字段。
        try:
            fields = object.__getattribute__(self, "fields")
        except AttributeError:
            raise AttributeError(item) from None
        try:
            return fields[item]
        except KeyError:
            raise AttributeError(
                f"{self._point} 的条目 {self.key!r} 没有字段 {item!r}"
                f"（可用：{', '.join(sorted(fields)) or '无'}）"
            ) from None

    def get(self, item, default=None):
        return self.fields.get(item, default)

    def __repr__(self):
        return f"<Entry {self.key} fields={sorted(self.fields)}>"


class Registry:
    """扩展点登记中心。实例只有一个（模块底部 registry），但类可单独实例化便于测试。"""

    RESERVED = _RESERVED

    def __init__(self):
        self.data = {}

    # ─────────────────────────── 声明扩展点 ───────────────────────────

    def declare(self, point, *, registrant=None, fields=(), required=(),
                kind="class", doc=""):
        """声明一个扩展点，并钉死它能接受哪些字段。

        fields    允许出现的字段名（不在表里的字段，add() 会当场报错）
        required  其中必须提供的字段
        registrant 谁声明了这个扩展点；缺省取 point 的前缀（"core.pages" → "core"）

        重复声明且 schema 一致时视为幂等（模块可能被多次 import），
        schema 不同则报错 —— 那说明两处对同一个扩展点的约定已经打架了。
        """
        if not isinstance(point, str) or not point or point.startswith("__"):
            raise RegistryError(f"扩展点名不合法：{point!r}")

        fields = tuple(fields)
        required = tuple(required)
        stray = [f for f in required if f not in fields]
        if stray:
            raise RegistryError(f"{point}: __required__ 里的 {stray} 不在 __fields__ 中")

        block = {
            "__registrant__": registrant or _namespace_of(point) or point,
            "__kind__": kind,
            "__fields__": fields,
            "__required__": required,
            "__doc__": doc,
        }

        cur = self.data.get(point)
        if cur is not None:
            diff = [k for k, v in block.items() if cur.get(k) != v]
            if diff:
                raise RegistryError(
                    f"扩展点 {point!r} 已声明且 schema 不同（{', '.join(diff)}）"
                )
            return point

        self.data[point] = block
        return point

    def declared(self, point):
        return point in self.data

    def points(self):
        """所有已声明的扩展点名。"""
        return list(self.data)

    def meta(self, point):
        """扩展点自身的元信息（副本，改它不影响注册表）。"""
        return {k: v for k, v in self._block(point).items() if k in self.RESERVED}

    # ─────────────────────────── 登记条目 ───────────────────────────

    def add(self, point, key, **fields):
        """往扩展点里登记一个条目，返回 Entry。

        未声明就先报错，而不是顺手新建一个 —— 那样会把「扩展点名拼错」
        变成「多出一个没人读的空扩展点」，最难查。
        """
        block = self._block(point)

        if not _is_entry_key(key):
            raise RegistryError(
                f"{point}: 条目 key {key!r} 不合法，必须是 <namespace>.<name>"
                f"（如 core.start / com.example.hello.main）"
            )
        if key in block:
            raise RegistryError(f"{point} 里已存在条目 {key!r}（不允许静默覆盖）")

        allowed = set(block["__fields__"])
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise RegistryError(
                f"{point}.{key}: 未知字段 {unknown}；该扩展点只接受 {sorted(allowed)}"
            )
        missing = sorted(set(block["__required__"]) - set(fields))
        if missing:
            raise RegistryError(f"{point}.{key}: 缺必填字段 {missing}")

        block[key] = dict(fields)
        return Entry(point, key, block["__registrant__"], block[key])

    # ─────────────────────────── 查询 ───────────────────────────

    def entries(self, point, *, where=None, order_by="order"):
        """按 order 取条目；where 做等值筛选（如 where={"group": "preferences"}）。

        排序键是 (order, key)：同一 order 下按 key 定序，保证每次构建顺序一致 ——
        界面元素顺序随字典迭代顺序漂移，是最难复现的那类问题。

        返回的 Entry 是**只读视图**（字段为副本）：界面拿着它构造控件即可，
        要改登记内容请走 add()/remove_namespace()，别改快照。
        """
        block = self._block(point)
        out = []
        for key, fields in block.items():
            if key in self.RESERVED:
                continue
            e = Entry(point, key, block["__registrant__"], dict(fields))
            if where and any(e.fields.get(k) != v for k, v in where.items()):
                continue
            out.append(e)
        if order_by:
            out.sort(key=lambda e: (e.fields.get(order_by, DEFAULT_ORDER), e.key))
        return out

    def entry(self, point, key):
        """取单个条目；不存在时给出「这个扩展点有哪些条目」的提示。"""
        block = self._block(point)
        fields = block.get(key)
        if not isinstance(fields, dict) or key in self.RESERVED:
            have = sorted(k for k in block if k not in self.RESERVED)
            raise RegistryError(f"{point} 里没有条目 {key!r}；现有：{have or '（空）'}")
        return Entry(point, key, block["__registrant__"], dict(fields))

    # ─────────────────────────── 校验 / 维护 ───────────────────────────

    def validate(self):
        """全表扫一遍，返回问题清单（空列表 = 通过）。

        与 add() 的即时校验互补：这里是「构建前再确认一次」，把问题一次报全，
        而不是让界面构建到第 3 个条目才炸。
        """
        problems = []
        for point, block in self.data.items():
            allowed = set(block.get("__fields__", ()))
            required = set(block.get("__required__", ()))
            for key, fields in block.items():
                if key in self.RESERVED:
                    continue
                if not _is_entry_key(key):
                    problems.append(f"{point}: 条目 key {key!r} 不是 <namespace>.<name> 形式")
                if not isinstance(fields, dict):
                    problems.append(f"{point}.{key}: 条目内容不是 dict")
                    continue
                unknown = sorted(set(fields) - allowed)
                if unknown:
                    problems.append(f"{point}.{key}: 未知字段 {unknown}")
                missing = sorted(required - set(fields))
                if missing:
                    problems.append(f"{point}.{key}: 缺必填字段 {missing}")
        return problems

    def remove_namespace(self, ns):
        """按命名空间摘掉条目（插件禁用 / 加载失败回滚），返回摘掉的条数。

        只摘条目，不动扩展点本身的声明 —— 扩展点归声明者，不该被插件带走。
        """
        removed = 0
        for point, block in self.data.items():
            doomed = [k for k in block
                      if k not in self.RESERVED and _namespace_of(k) == ns]
            for k in doomed:
                del block[k]
                removed += 1
        return removed

    def clear(self):
        """清空整表（测试隔离用）。"""
        self.data.clear()

    def dump(self):
        """当前结构的快照，供排查时直接打印。

        条目也复制一层：dump 出来的东西要是能被随手改坏注册表，
        那它就不是快照而是后门了。
        """
        out = {}
        for point, block in self.data.items():
            out[point] = {
                k: (dict(v) if isinstance(v, dict) else v)
                for k, v in block.items()
            }
        return out

    # ─────────────────────────── 内部 ───────────────────────────

    def _block(self, point):
        block = self.data.get(point)
        if block is None:
            known = ", ".join(sorted(self.data)) or "（尚未声明任何扩展点）"
            raise RegistryError(
                f"扩展点 {point!r} 尚未声明，请先 registry.declare(...)；已声明：{known}"
            )
        return block


# 全局单例：与 src/utils/bus.py 的 bus 同一风格
registry = Registry()
