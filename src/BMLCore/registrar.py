# -*- coding: utf-8 -*-
"""注册 DSL —— 所有登记只有一个出口：`registrar("命名空间")` / `register("命名空间")`。

    from BMLCore import BMLPlugin, registrar, register

    class Hello(BMLPlugin):
        id = "example_hello"

        # ① 方法上挂（装饰器）：先记标记，加载器 apply(plugin) 时真正登记
        @registrar("core/pages").new(title="hello.page", order=50)
        def page(self, ctx):
            return MyPage(ctx.parent)

        # ② 类属性里挂（不带函数）：标记对象，同样在 apply 时落地
        css = registrar("core/qss").new("hello.css", css="QLabel#x{color:red}", theme=None)

        # ③ 类体里声明设置 / 信号（apply 时落到插件自己名下）
        settings_ = registrar("settings").new("volume", 50)

运行期（已经拿到插件实例）写在方法里，走 self.register(...)：

    def on_ready(self):
        self.register("settings").new("runs", 0)       # 声明
        self.register("settings").set("runs", 1)       # 写
        self.register("settings").get("runs")          # 读
        self.register("core/settings").get("theme")    # 跨桶读（显式路径）
        self.register("signals").new("progress")       # 声明自己的信号
        self.register("signals").set("progress", 0.5)  # 发（自动加 "<id>." 前缀）
        self.register("signals").watch("progress", self._on_progress)   # 订

九个动词，每个命名空间都认同一套：

    new      登记一项（装饰器 / 标记 / 运行期都行）
    set      写值 / 顶掉已有条目 / 发信号
    update   改自己那一条的字段 / 合并字典型设置
    remove   摘掉自己的一条 / 删一个键
    get      读一条（条目 / 设置值 / 信号持有者）
    list     列出来（接口里的条目 / 设置键 / 自己的信号名）
    owned    我名下登记的一切（按命名空间过滤）
    contract 声明 / 查看接口契约（字段表、必填、是否可覆盖）
    watch    盯变更（注册表变更 / 设置键 / 事件名）

命名空间解析（owner 段可省 = 当前插件）：

    "settings"        → 当前插件的设置桶（settings.json 里自己那一格）
    "core/settings"   → 宿主设置桶（跨桶读走这条显式路径）
    "signals"         → 全局事件总线（信号全走它；不再自定义 Signals 类）
    "core/pages"      → 普通扩展点，owner = core
    "example_hello/parts" → 自己的扩展点（显式写 owner 也行）

装饰器与标记的落地时机统一在 `registrar.apply(plugin)`（加载器在插件构造之后
调一次）：先记标记、后登记，构造里抛异常时整场登记一起回滚。
"""

from ..utils.events import events
from ..utils.registry import registry

# 九个动词：所有命名空间共用同一套名字
VERBS = ("new", "set", "update", "remove", "get", "list", "owned", "contract", "watch")

# 标记挂在函数上（列表，允许一个方法挂多条）：
#   [ (Scope, verb, name, fields), ... ]
_MARK = "__bml_registrar__"


def _unwrap(attr):
    """取出被 staticmethod / classmethod / property 包住的那个真函数。"""
    if isinstance(attr, (staticmethod, classmethod)):
        return attr.__func__
    if isinstance(attr, property):
        return attr.fget
    return attr


def _split(path):
    """命名空间 → (owner, 名字)。owner 为 None = 当前插件。"""
    path = (path or "").strip().strip("/")
    if not path:
        raise ValueError("registrar(...) 需要一个命名空间，比如 core/pages / settings")
    if "/" in path:
        owner, _, name = path.partition("/")
        if not owner or not name:
            raise ValueError(f"命名空间 {path!r} 不合法：要写成 <owner>/<名字>")
        return owner, name
    return None, path


class _Mark:
    """一条登记声明：可以包方法（装饰器），也可以留在类属性里（标记对象）。"""

    __slots__ = ("scope", "verb", "name", "fields")

    def __init__(self, scope, verb, name, fields):
        self.scope = scope      # Scope
        self.verb = verb
        self.name = name
        self.fields = dict(fields)

    def __call__(self, fn):
        """装饰器：标记记在函数上，方法名作为条目名（name 为空时）。"""
        target = _unwrap(fn)
        if target is None or not callable(target):
            raise TypeError(
                f"registrar({self.scope.path!r}).{self.verb} 只能挂在普通方法上，"
                f"收到 {type(fn).__name__}")
        mark = _Mark(self.scope, self.verb, self.name if self.name else fn.__name__,
                     self.fields)
        marks = list(getattr(target, _MARK, ()))
        marks.append(mark)
        setattr(target, _MARK, marks)
        return fn

    def __repr__(self):
        return "<registrar %r.%s %r>" % (self.scope.path, self.verb, self.name)


class Scope:
    """一个命名空间的注册作用域：方法名 = 九动词。"""

    __slots__ = ("path", "owner", "name", "plugin")

    def __init__(self, path, plugin=None):
        self.path = str(path or "").strip()
        self.owner, self.name = _split(self.path)
        self.plugin = plugin        # 绑了插件实例时，运行期调用当场执行

    # ── 九动词 ──

    def new(self, name=None, *args, **fields):
        """登记一项。

        - 给函数（装饰器用法）：立刻把标记挂上去，apply() 时落地；
        - 没绑实例（registrar("ns")）：返回标记对象（类属性用）；
        - 绑了实例（self.register(...)）：当场执行（运行期声明）。
        `new("音量", 50)` 这种第二个位置参数是默认值 / 值。
        """
        if callable(name) and not isinstance(name, str):
            return _Mark(self, "new", name.__name__, fields)(name)
        if args:
            fields.setdefault("default", args[0])
        if self.plugin is not None:
            return self._exec("new", name, fields, None)
        return _Mark(self, "new", name, fields)

    def set(self, name=None, *args, **fields):
        if callable(name) and not isinstance(name, str):
            return _Mark(self, "set", name.__name__, fields)(name)
        if args:
            fields["value"] = args[0]
            fields["args"] = args
        return self._run_mark("set", name, fields)

    def update(self, name=None, *args, **fields):
        if callable(name) and not isinstance(name, str):
            return _Mark(self, "update", name.__name__, fields)(name)
        if args:
            fields.setdefault("value", args[0])
        return self._run_mark("update", name, fields)

    def remove(self, name=None, *args, **fields):
        if callable(name) and not isinstance(name, str):
            return _Mark(self, "remove", name.__name__, fields)(name)
        return self._run_mark("remove", name, fields)

    def get(self, name=None):
        return self._run_mark("get", name, {})

    def list(self, **kw):
        return self._run_mark("list", None, kw)

    def owned(self, **kw):
        return self._run_mark("owned", None, kw)

    def contract(self, **fields):
        return self._run_mark("contract", None, fields)

    def watch(self, name=None, callback=None, **kw):
        if callable(name) and callback is None:
            callback, name = name, None
        return self._run_mark("watch", name, dict(kw, callback=callback))

    # ── 运行期 / 标记 ──

    def _run_mark(self, verb, name, fields):
        if self.plugin is None:
            return _Mark(self, verb, name, fields)
        return self._exec(verb, name, fields, None)

    # ── 内部：解析与落地 ──

    def _actor(self):
        if self.plugin is not None:
            return self.plugin.id
        return registry._session_owner or registry._current_owner()

    def _exec(self, verb, name, fields, fn):
        actor = self._actor()
        if self.name == "settings":
            return self._settings(verb, name, fields, actor, fn)
        if self.name == "signals":
            return self._signals(verb, name, fields, actor, fn)
        return self._registry(verb, name, fields, fn, actor)

    # 设置：自己那一桶（self.plugin.settings）；core/settings 走 other()
    def _settings(self, verb, name, fields, actor, fn=None):
        if self.plugin is None:
            raise RuntimeError(
                "设置动词要在绑定了插件的 register(...) 上调用（self.register）")
        view = self.plugin.settings
        owner = self.owner or actor
        if verb == "new":
            if owner != actor:
                raise KeyError(f"不能给 {owner!r} 的桶声明设置键（跨桶只读）")
            return view.declare(name, fields.get("default"))
        if verb == "set":
            if owner != actor:
                raise KeyError(f"别的桶不给写（覆盖许可只到自己的键）：{owner!r}")
            # 与 set_config 同路：写值并通知 watch_config 的回调
            self.plugin.set_config(name, fields.get("value"))
            return None
        if verb == "update":
            if owner != actor:
                raise KeyError(f"别的桶不给写：{owner!r}")
            self.plugin.set_config(name, fields.get("value"))
            return None
        if verb == "remove":
            if owner == actor:
                try:
                    del view[name]
                except KeyError:
                    pass
                # 运行期声明过的键：连声明一起摘（否则删了还剩个默认值）
                view.defaults.pop(name, None)
            return None
        if verb == "get":
            return view.get(name) if owner == actor else self.plugin.settings.other(owner).get(name)
        if verb == "list":
            return list(view) if owner == actor else list(self.plugin.settings.other(owner))
        if verb == "owned":
            return sorted(view)
        if verb == "contract":
            return dict(view.defaults)
        if verb == "watch":
            cb = fields.get("callback")
            if cb is None and fn is not None:
                cb = getattr(self.plugin, fn.__name__)
            if cb is None:
                raise ValueError("watch 需要一个回调")
            return self.plugin.watch_config(name, cb)
        raise ValueError(f"settings 不支持动词 {verb!r}")

    # 信号：全局总线，名字自动加 "<id>." 前缀
    def _signals(self, verb, name, fields, actor, fn=None):
        def bus_name(n):
            n = str(n or "")
            return n if n.startswith(f"{actor}.") or n.startswith("core.") else f"{actor}.{n}"

        if verb == "new":
            bus = bus_name(name)
            events.register(bus)
            return bus
        if verb == "set":
            events.emit(bus_name(name), *fields.get("args", ()))
            return None
        if verb == "update":
            raise ValueError("signals 不支持 update（换签名请重新 new）")
        if verb == "remove":
            raise ValueError("signals 不支持 remove")
        if verb == "get":
            holder = events._holders.get(bus_name(name))
            return holder.signal if holder is not None else None
        if verb == "list":
            return sorted(n for n in events.names() if n.startswith(f"{actor}."))
        if verb == "owned":
            return sorted(n for n in events.names() if n.startswith(f"{actor}."))
        if verb == "contract":
            return {"namespace": "signals", "prefix": f"{actor}."}
        if verb == "watch":
            cb = fields.get("callback")
            if cb is None and fn is not None:
                cb = getattr(self.plugin, fn.__name__) if self.plugin is not None \
                    else getattr(fn, "__func__", fn)
            if cb is None:
                raise ValueError("watch 需要一个回调")
            events.on(bus_name(name), cb, owner=actor)
            return cb
        raise ValueError(f"signals 不支持动词 {verb!r}")

    # 普通扩展点：registry 那套
    def _registry(self, verb, name, fields, fn, actor):
        point = self.path if self.owner else f"{actor}/{self.name}"
        key = f"{actor}/{name}" if name else None
        if verb == "new" and fn is not None:
            fields = dict(fields)
            fields["init"] = _builder(self.plugin, fn, fields)
        if verb == "new":
            return registry.add(point, key, **fields)
        if verb == "set":
            return registry.set(point, key, by=actor, **fields)
        if verb == "update":
            return registry.update(point, key, **fields)
        if verb == "remove":
            return registry.remove(point, key)
        if verb == "get":
            return registry.entry(point, key)
        if verb == "list":
            return [e.key for e in registry.entries(point)]
        if verb == "owned":
            return registry.owned(actor)
        if verb == "contract":
            return registry.declare(point, registrant=actor, **fields)
        if verb == "watch":
            cb = fields.get("callback")
            if cb is None:
                raise ValueError("watch 需要一个回调")
            return registry.watch(cb)
        raise ValueError(f"不支持动词 {verb!r}")


def registrar(path):
    """工厂：`registrar("命名空间")` / `register("命名空间")` 都指向这里。"""
    return Scope(path)


def _builder(plugin, fn, fields):
    """把「方法 → init 工厂」包一层：宿主调 init(Ctx)，这里转交给插件的方法。"""
    from .Plugin import Ctx

    method = getattr(plugin, fn.__name__)

    def init(box):
        ctx = Ctx(parent=getattr(box, "parent", None),
                   title=fields.get("title", ""),
                   items=getattr(box, "items", ()),
                   entry=getattr(box, "entry", None))
        return method(ctx)

    return init


# ─────────────────────────── 收集与落地 ───────────────────────────

def collect(cls):
    """按 MRO 收集一个插件类上的全部标记（函数标记 + 类属性标记）。

    返回 [(scope, verb, name, fields, fn)]；fn 可能为 None（类属性声明）。
    """
    out = []
    seen = set()
    used_fns = set()
    for base in cls.__mro__:
        for name, attr in vars(base).items():
            if name in seen:
                continue
            seen.add(name)
            if isinstance(attr, _Mark):
                out.append((attr.scope, attr.verb, attr.name, attr.fields, None))
                continue
            fn = _unwrap(attr)
            marks = getattr(fn, _MARK, None)
            if not marks:
                continue
            if isinstance(attr, property):
                raise TypeError(
                    f"{cls.__name__}.{name}：带 registrar 标记的方法被 property 包住了，"
                    f"这样登记不到（取值语义对不上）。把 property 去掉，或换个方法名")
            if id(fn) in used_fns:
                continue
            used_fns.add(id(fn))
            for mark in marks:
                out.append((mark.scope, mark.verb, mark.name, mark.fields, fn))
    return out


def apply(plugin):
    """把收集到的标记真正登记出去（加载器在插件构造之后调一次）。"""
    made = []
    for scope, verb, name, fields, fn in collect(type(plugin)):
        sc = Scope(scope.path, plugin)
        made.append(sc._exec(verb, name, fields, fn))
    # 实例上临时挂的标记（写在 __init__ 里的那种）也扫一遍
    for attr in list(vars(plugin).values()):
        if isinstance(attr, _Mark):
            sc = Scope(attr.scope.path, plugin)
            made.append(sc._exec(attr.verb, attr.name, attr.fields, None))
    return made


_READY = {}


def ready(plugin_id):
    """（保留位）就绪钩子现在是 Plugin.on_ready 方法，不再走注册标记。"""
    return list(_READY.pop(plugin_id, ()))


def discard(plugin_id):
    """丢掉某个插件攒下的就绪回调（加载失败回滚时调）。"""
    _READY.pop(plugin_id, None)
