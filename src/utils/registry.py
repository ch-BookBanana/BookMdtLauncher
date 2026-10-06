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
3. **加载顺序与界面创建解耦**。插件加载完 ≠ 界面已构建（GameSettings 就是点开才建），
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

            "core.start": {
                "cls": Start, "title": ..., "order": 10,     # ← add()  登记
                "__built__": {"main": <Start 实例>,           # ← bind() 回填
                              "btn":  <左栏导航按钮>},
            },
            "com.example.hello.main": {"cls": HelloPage, "order": 100},
        },
    }

* 保留键一律 `__xxx__`；条目 key 一律 `<namespace>.<name>` 且不得以 `__` 开头，
  两组键因此永不打架（add() 会挡住越界的 key）。
* 条目内的 `__built__` 专放**构建产物**：add 进来的是「谁登记谁提供」的声明，
  bind 填进去的是「谁构建谁回填」的实例。两者分开，`__fields__` 校验才不会
  把 main/btn 当成未知字段。产物用 e.main / e.btn 直读（查找顺序：登记字段 → 产物）。
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

__all__ = ["RegistryError", "Entry", "Box", "Registry", "registry", "page",
           "simple", "DEFAULT_ORDER"]

# 条目没写 order 时排在这里：够小，自定义项默认落在内置项之后
DEFAULT_ORDER = 100

# 扩展点块里的保留键（扩展点自身的元信息，不是条目）
_RESERVED = ("__registrant__", "__kind__", "__fields__", "__required__",
             "__built_fields__", "__doc__")

# 条目里的保留键：构建产物回填处。
# 必须与登记字段分区 —— 否则 bind() 填进来的 main/btn 会被 __fields__ 判成
# 「未知字段」，validate() 也分不清「登记时写错了」和「构建时填进来的」。
_BUILT = "__built__"


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
    """一个登记项：key 拆出来的身份 + 登记字段 + 构建产物。

    字段既可以用 e.cls 直读，也可以用 e.get("cls", 默认值)；
    查找顺序是「登记字段 → 构建产物」，所以页面装配好之后
    e.main / e.btn 也能直接读（那两个是 bind() 的产物，不是登记字段）。
    """

    __slots__ = ("key", "namespace", "name", "fields", "built", "built_fields",
                 "_point", "_registrant")

    def __init__(self, point, key, registrant, raw_fields, built_fields=()):
        self._point = point
        self._registrant = registrant
        self.key = key
        # 登记字段与构建产物在这里分开：fields 只留 add() 时登记的，built 只留 bind() 填的
        self.fields = {k: v for k, v in raw_fields.items() if k != _BUILT}
        self.built = dict(raw_fields.get(_BUILT) or {})
        self.built_fields = tuple(built_fields)
        ns, _, name = key.rpartition(".")
        self.namespace = ns or registrant
        self.name = name or key

    def __getattr__(self, item):
        # __slots__ 里的字段正常查找就命中了，走不到这里；能走到说明是在要扩展字段。
        try:
            fields = object.__getattribute__(self, "fields")
        except AttributeError:
            raise AttributeError(item) from None
        if item in fields:
            return fields[item]
        built = object.__getattribute__(self, "built")
        if item in built:
            return built[item]
        slots = object.__getattribute__(self, "built_fields")
        if item in slots:
            raise AttributeError(
                f"{self._point} 的条目 {self.key!r} 声明了产物槽位 {item!r}，"
                f"但还没有 bind() 回填"
            )
        avail = (sorted(fields)
                 + [f"{k}(产物)" for k in sorted(built)]
                 + [f"{k}(槽位)" for k in sorted(slots) if k not in built])
        raise AttributeError(
            f"{self._point} 的条目 {self.key!r} 没有字段 {item!r}"
            f"（可用：{', '.join(avail) or '无'}）"
        )

    def get(self, item, default=None):
        """先查登记字段，再查构建产物。"""
        if item in self.fields:
            return self.fields[item]
        return self.built.get(item, default)

    def is_built(self):
        """构建产物是否已回填（比如页面装配完成、main/btn 就位）。"""
        return bool(self.built)

    def __repr__(self):
        mark = f" +built{sorted(self.built)}" if self.built else ""
        return f"<Entry {self.key} fields={sorted(self.fields)}{mark}>"


class Box:
    """构建一个条目时交给 init 的「匣子」。

    装配方只负责「备好容器与配套产物 → 调 e.init(box)」，不再需要知道每个条目
    类的构造签名 —— 那本来就是**注册方**（写下那个类的人）才知道的事。
    签名不一致、需要额外参数、甚至是几个控件拼出来的复合控件，都由 init 自己解决。

    box.parent  该条目该挂到哪个容器
    （原先还有个 root —— 「把宿主整个递进去」的旧做法，已去掉：
     组件要什么从 events 取，构造只要容器与自己的元信息）
    box.entry   条目自身，可读 title / icon / order / name / key 等
    box.btn     配套按钮（扩展点声明了 btn 产物槽位时才有，否则为 None）

    b.title 这类读取直接代理到条目，省得每次都写 b.entry.title。

    本次上下文
    ----------
    关键词参数就是上下文：Box(parent=…, entry=…, game="<:|default|:>")，
    init 里 b.game 就取得到。用在「只有构建这一刻才知道」的东西上 ——
    比如开游戏管理浮层时才知道要管**哪个实例**：

        self.add("core.overlays", "x", init=lambda b: Mgr(b.game, b.parent))

    静态元信息（title/icon/order…）该写在条目字段里；上下文只放一次性的。
    两者重名时以本次上下文为准。没给又去读，会当场抛 AttributeError
    并把可用的上下文列出来 —— 好过默默给个 None 让上层隔很远才炸。
    """

    __slots__ = ("parent", "entry", "btn", "_ctx")

    def __init__(self, parent=None, entry=None, btn=None, **ctx):
        self.parent = parent
        self.entry = entry
        self.btn = btn
        self._ctx = ctx

    def __getattr__(self, item):
        # 正常查找失败才走到这里：先看本次上下文，再看条目字段。
        # 条目自己的报错带着扩展点名与可用字段清单，比在这里再包一层有用，
        # 所以原样放它出去。
        try:
            ctx = object.__getattribute__(self, "_ctx")
        except AttributeError:
            ctx = {}
        if item in ctx:
            return ctx[item]
        try:
            entry = object.__getattribute__(self, "entry")
        except AttributeError:
            raise AttributeError(item) from None
        return getattr(entry, item)

    def __repr__(self):
        key = getattr(self.entry, "key", None)
        return f"<Box {key}>"


def simple(cls, **extra):
    """便捷 init：控件构造签名正好是 (parent, root, title, **extra) 时用它。

    这只是**注册方**替自己省事 —— 注册方知道自己的类长什么样；
    装配方不必知道，它只管调 init。
    """
    return lambda b: cls(b.parent, b.title, **extra)


class Registry:
    """扩展点登记中心。实例只有一个（模块底部 registry），但类可单独实例化便于测试。

    加载会话（begin / commit / abort）
    ---------------------------------
    插件 setup 跑到一半抛异常时，它之前登记的东西不能留在正表里 —— 界面会冒出
    半截条目（点下去还可能炸），重试也会撞「已存在条目」。所以插件登记做成
    **全有或全无**：

        registry.begin()   开一个会话，之后插件写的都进暂存区
        registry.commit()  跑完了，把暂存区并进正表
        registry.abort()   没跑完，整块丢掉（连它本次 declare 的扩展点一起）

    为什么不是「失败了按命名空间擦」：擦不干净（插件自己 declare 出来的扩展点
    擦不掉），而且每条失败路径都得记得擦一次 —— 靠记性的事迟早漏。

    会话期间**读**看到的是两张表之和：插件在 setup 里要读宿主的扩展点、
    要读依赖交出来的服务（依赖已经 commit 过了，在正表里），这些必须照常可见。
    所以只把「写」导向暂存区，读是合并视图。
    """

    RESERVED = _RESERVED

    def __init__(self):
        self.data = {}
        # 会话中的暂存区（形状与 data 一样：{point: block}）。
        # 同一个扩展点可能两边都有块：正表那块带 schema（以及已提交的条目），
        # 暂存区那块装本次会话新加的条目。查询要合起来看。
        self._stage = None

    # ─────────────────────────── 加载会话 ───────────────────────────

    def in_session(self):
        """当前是否在加载会话里。"""
        return self._stage is not None

    def begin(self):
        """开一个加载会话。已经在会话里就报错 —— 嵌套说明调用方搞错了。"""
        if self._stage is not None:
            raise RegistryError("已经在加载会话里，不能嵌套（插件 setup 里别再开一个）")
        self._stage = {}
        return self

    def commit(self):
        """把会话登记的并进正表：先声明新扩展点，再落条目。返回并进去的条数。"""
        stage, self._stage = self._stage, None
        if not stage:
            return 0
        n = 0
        for point, block in stage.items():
            res = {k: v for k, v in block.items() if k in self.RESERVED}
            if res:
                # 本次会话声明的新扩展点，连 schema 一起并过去。
                # 正表已有同名点时 declare 是幂等的（schema 一样就返回）。
                self.declare(point,
                             registrant=res["__registrant__"],
                             fields=res["__fields__"],
                             required=res["__required__"],
                             built=res.get("__built_fields__", ()),
                             kind=res.get("__kind__", "class"),
                             doc=res.get("__doc__", ""))
            for key, fields in block.items():
                if key in self.RESERVED:
                    continue
                # 直接写进正表，不走 add()：会话里 set 过的可能正是正表已有的
                # 同名条目，add 会撞「已存在条目」—— 而 set 的语义就是顶掉它。
                # 产物（__built__）就在 fields 里，整条照抄即可。
                self.data.setdefault(point, {})[key] = dict(fields)
                n += 1
        return n

    def abort(self):
        """丢掉这次会话的全部登记。返回丢掉的条数（新扩展点不算条数）。"""
        stage, self._stage = self._stage, None
        if not stage:
            return 0
        return sum(1 for block in stage.values()
                   for key in block if key not in self.RESERVED)

    def _blocks_of(self, point):
        """这个扩展点上「有条目」的块，按 [正表, 暂存区] 给（暂存区可能没有）。"""
        out = []
        real = self.data.get(point)
        if real is not None:
            out.append(real)
        if self._stage is not None:
            stage = self._stage.get(point)
            if stage is not None:
                out.append(stage)
        return out

    def _write_block(self, point):
        """写条目该落到哪块：会话中落暂存区（正表那块只读着用），否则落正表。"""
        if self._stage is None:
            return self.data.setdefault(point, {})
        return self._stage.setdefault(point, {})

    def _find_entry(self, point, key):
        """取条目**本身**（暂存区优先，它更新）。没有就返回 None。

        注意返回的是 block[key] 而不是 block —— 调用方（bind / entry / add 查重）
        要的都是那条目的字段。
        """
        for block in reversed(self._blocks_of(point)):
            if key not in self.RESERVED and key in block:
                return block[key]
        return None

    # ─────────────────────────── 声明扩展点 ───────────────────────────

    def declare(self, point, *, registrant=None, fields=(), required=(),
                built=(), kind="class", doc=""):
        """声明一个扩展点，并钉死它能接受哪些字段。

        fields    允许出现的字段名（不在表里的字段，add() 会当场报错）
        required  其中必须提供的字段
        built     构建产物的**槽位名**（如页面条的 main/btn）。声明了槽位，
                  bind() 填别的名字就会报错，读的时候也知道「这个条目本该有产物」。
        registrant 谁声明了这个扩展点；缺省取 point 的前缀（"core.pages" → "core"）

        重复声明且 schema 一致时视为幂等（模块可能被多次 import），
        schema 不同则报错 —— 那说明两处对同一个扩展点的约定已经打架了。
        """
        if not isinstance(point, str) or not point or point.startswith("__"):
            raise RegistryError(f"扩展点名不合法：{point!r}")

        fields = tuple(fields)
        required = tuple(required)
        built = tuple(built)
        stray = [f for f in required if f not in fields]
        if stray:
            raise RegistryError(f"{point}: __required__ 里的 {stray} 不在 __fields__ 中")
        overlap = [f for f in built if f in fields]
        if overlap:
            raise RegistryError(
                f"{point}: {overlap} 同时出现在 __fields__ 和产物槽位里；"
                f"登记字段与构建产物必须分开"
            )

        block = {
            "__registrant__": registrant or _namespace_of(point) or point,
            "__kind__": kind,
            "__fields__": fields,
            "__required__": required,
            "__built_fields__": built,
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

        # 会话中声明的新点先落暂存区：abort 时它要跟着一起消失
        #（否则会留下一个没人用的空扩展点，重试时还撞「已声明」）。
        target = self._stage if self._stage is not None else self.data
        if point in target:
            diff = [k for k, v in block.items() if target[point].get(k) != v]
            if diff:
                raise RegistryError(
                    f"扩展点 {point!r} 已声明且 schema 不同（{', '.join(diff)}）"
                )
            return point
        target[point] = block
        return point

    def declared(self, point):
        return point in self.data or (
            self._stage is not None and point in self._stage)

    def points(self):
        """所有已声明的扩展点名（含会话中新声明的）。"""
        return sorted(set(self.data) | set(self._stage or ()))

    def meta(self, point):
        """扩展点自身的元信息（副本，改它不影响注册表）。"""
        return {k: v for k, v in self._block(point).items() if k in self.RESERVED}

    # ─────────────────────────── 登记条目 ───────────────────────────

    def add(self, point, key, **fields):
        """往扩展点里登记一个条目，返回 Entry。

        未声明就先报错，而不是顺手新建一个 —— 那样会把「扩展点名拼错」
        变成「多出一个没人读的空扩展点」，最难查。

        撞上同名 key 直接报错（不允许静默覆盖）：要顶掉已有那条，用 set()。
        """
        block = self._block(point)
        self._check_key(point, key)
        # 查重要看两张表：正表里已有的、以及本次会话里刚加的
        if self._find_entry(point, key) is not None:
            raise RegistryError(f"{point} 里已存在条目 {key!r}（要顶掉它用 set）")
        self._check_fields(point, key, block, fields)
        self._write_block(point)[key] = dict(fields)
        return Entry(point, key, block["__registrant__"], dict(fields),
                     block.get("__built_fields__", ()))

    def set(self, point, key, **fields):
        """写一条条目：已有就**顶掉**，没有就新建。返回 Entry。

        与 add() 的分工：add 是「登记」（撞名报错，防手滑、也防两条内置条目
        悄悄互相顶掉），set 是「就这么定」（同名一律顶掉）。它的用处是留出
        **可替换的位子**：想换掉内置的某一条（比如关闭询问 core.closeAsk），
        按同名 set 一下就行 —— 打开它的地方只认 key，一行都不用改。

        会话里（插件加载期）同样成立：写进暂存区把正表那条盖住，abort 就什么
        都没发生，commit 才真落到正表。

        谁 set 谁负责：插件顶掉宿主的内置条目之后，卸载时要把宿主那条 set 回来
        （卸载按命名空间摘，而 `core.*` 这种 key 挂不到插件名下）。
        """
        block = self._block(point)
        self._check_key(point, key)
        self._check_fields(point, key, block, fields)
        self._write_block(point)[key] = dict(fields)
        return Entry(point, key, block["__registrant__"], dict(fields),
                     block.get("__built_fields__", ()))

    def _check_key(self, point, key):
        if not _is_entry_key(key):
            raise RegistryError(
                f"{point}: 条目 key {key!r} 不合法，必须是 <namespace>.<name>"
                f"（如 core.start / com.example.hello.main）"
            )

    def _check_fields(self, point, key, block, fields):
        """字段校验（add 与 set 共用）：认得的字段、必填的字段。"""
        allowed = set(block["__fields__"])
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise RegistryError(
                f"{point}.{key}: 未知字段 {unknown}；该扩展点只接受 {sorted(allowed)}"
            )
        missing = sorted(set(block["__required__"]) - set(fields))
        if missing:
            raise RegistryError(f"{point}.{key}: 缺必填字段 {missing}")

    def provide(self, point, key, obj, **meta):
        """登记一个**已经存在**的对象，登记完立刻可查。

        宿主体（三栏页容器）这类「本来就只有一个实例、而且先于使用者就建好」的
        东西用它。与 add() 的分工：add 登记「怎么造」（构建期才调 init），
        provide 登记「就是这个」（对象已经在手上）。
        需要该扩展点先 declare(built=("obj",)) 声明好产物槽位。
        """
        self.add(point, key, init=lambda b: obj, **meta)
        return self.bind(point, key, obj=obj)

    def bind(self, point, key, **built):
        """回填构建产物（页面实例 main、导航按钮 btn…），返回带产物的 Entry。

        单独一个方法而不是并进 add()：add 是「谁登记谁提供」，bind 是「谁构建谁回填」，
        责任人不同、时机也不同 —— 插件可以在启动早期就登记完，而界面要等宿主建好
        才开始构建。产物走 __built__，不参与 __fields__ 校验。
        """
        block = self._block(point)
        raw = self._find_entry(point, key)
        if not isinstance(raw, dict) or key in self.RESERVED:
            raise RegistryError(f"{point} 里没有条目 {key!r}，无法回填构建产物")
        slots = block.get("__built_fields__") or ()
        unknown = sorted(set(built) - set(slots))
        if unknown:
            raise RegistryError(
                f"{point}.{key}: 未声明的产物 {unknown}；"
                f"该扩展点声明的产物槽位是 {list(slots) or '（无）'}"
            )
        raw.setdefault(_BUILT, {}).update(built)
        return Entry(point, key, block["__registrant__"], raw, slots)

    def unbind(self, point, key, *names):
        """摘掉构建产物（界面重建 / 卸载前）。不带 names 则清空该条目的全部产物。"""
        block = self._block(point)
        raw = self._find_entry(point, key)
        if not isinstance(raw, dict) or key in self.RESERVED:
            raise RegistryError(f"{point} 里没有条目 {key!r}，无法摘除构建产物")
        slot = raw.get(_BUILT)
        if not slot:
            return 0
        if not names:
            n = len(slot)
            raw[_BUILT] = {}
            return n
        n = 0
        for name in names:
            if name in slot:
                del slot[name]
                n += 1
        return n

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
        seen = set()
        # 暂存区在前、正表在后：会话里 set 过的以暂存区为准（同 key 只出面一次，
        # 出的就是新那份）。
        for src in reversed(self._blocks_of(point)):
            for key, fields in src.items():
                if key in self.RESERVED or key in seen:
                    continue
                seen.add(key)
                e = Entry(point, key, block["__registrant__"], dict(fields),
                          block.get("__built_fields__", ()))
                if where and any(e.fields.get(k) != v for k, v in where.items()):
                    continue
                out.append(e)
        if order_by:
            out.sort(key=lambda e: (e.fields.get(order_by, DEFAULT_ORDER), e.key))
        return out

    def entry(self, point, key):
        """取单个条目；不存在时给出「这个扩展点有哪些条目」的提示。"""
        block = self._block(point)
        fields = self._find_entry(point, key)
        if not isinstance(fields, dict) or key in self.RESERVED:
            have = sorted(k for src in self._blocks_of(point)
                          for k in src if k not in self.RESERVED)
            raise RegistryError(f"{point} 里没有条目 {key!r}；现有：{have or '（空）'}")
        return Entry(point, key, block["__registrant__"], dict(fields),
                     block.get("__built_fields__", ()))

    # ─────────────────────────── 校验 / 维护 ───────────────────────────

    def validate(self):
        """全表扫一遍，返回问题清单（空列表 = 通过）。

        与 add() 的即时校验互补：这里是「构建前再确认一次」，把问题一次报全，
        而不是让界面构建到第 3 个条目才炸。
        """
        problems = []
        for point in self.points():
            block = self._block(point)
            allowed = set(block.get("__fields__", ()))
            required = set(block.get("__required__", ()))
            entries = {}
            for src in self._blocks_of(point):
                entries.update({k: v for k, v in src.items() if k not in self.RESERVED})
            for key, fields in entries.items():
                if not _is_entry_key(key):
                    problems.append(f"{point}: 条目 key {key!r} 不是 <namespace>.<name> 形式")
                if not isinstance(fields, dict):
                    problems.append(f"{point}.{key}: 条目内容不是 dict")
                    continue
                unknown = sorted(set(fields) - allowed - {_BUILT})
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
        for table in (self.data, self._stage or {}):
            for point, block in table.items():
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
        # schema 优先看正表：正表有这块说明这个点早就声明过；正表没有才看暂存区
        # （本次会话刚 declare 的新点）。暂存区里为「正表已有的点」建的块只装
        # 新条目、不带 RESERVED，所以不能拿它当 schema 用。
        block = self.data.get(point)
        if block is None and self._stage is not None:
            block = self._stage.get(point)
        if block is None:
            known = ", ".join(sorted(set(self.data) | set(self._stage or ()))) \
                or "（尚未声明任何扩展点）"
            raise RegistryError(
                f"扩展点 {point!r} 尚未声明，请先 registry.declare(...)；已声明：{known}"
            )
        return block


# 全局单例：与 src/utils/bus.py 的 bus 同一风格
registry = Registry()


def page(key, *, point="core.pages", **meta):
    """把一个 Page 子类登记进扩展点（装饰器）。

        @page("core.start")
        class Start(Page):
            name    = "core.wid.pages.start"
            icon    = BTN_START
            order   = 10
            default = True

    元信息从**类属性**读，装饰器只补 key —— 「我是谁」和实现待在一起，
    而不是散在另一处的 add(...) 里。构造只传 btn：参数全在类上，
    装配方不必知道这个类怎么造；插件写一个页面也就是一个类的事。

    point 可以指向同类扩展点（core.setting.pages / core.gameManager.pages…），
    它们要的字段一样（init / title / icon / order / …），只是声明在不同地方。
    default 只有声明了它的扩展点才带上（core.pages 有，别处没有）。
    """
    def deco(cls):
        fields = registry.meta(point).get("__fields__", ())
        kw = dict(meta)          # 额外字段原样带上，也可以覆盖下面几项
        kw.setdefault("init", lambda b: cls(btn=getattr(b, "btn", None)))
        kw.setdefault("title", cls.name)
        if "icon" in fields:
            kw.setdefault("icon", cls.icon)
        kw.setdefault("order", getattr(cls, "order", 100))
        if "default" in fields:
            kw.setdefault("default", getattr(cls, "default", False))
        registry.add(point, key, **kw)
        return cls
    return deco
