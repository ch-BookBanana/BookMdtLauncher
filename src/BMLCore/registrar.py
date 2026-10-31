# -*- coding: utf-8 -*-
"""注册 DSL —— 所有登记只有一个出口：`registrar("命名空间")` / `register("命名空间")`。

    from BMLCore import BMLPlugin, registrar, register

    class Hello(BMLPlugin):
        id = "example_hello"

        # ① 方法上挂（装饰器）：先记标记，加载器 apply(plugin) 时真正登记
        @registrar("core/pages").new(title="hello.page")
        def page(self, ctx):
            return MyPage(ctx.parent)

        # ② 类属性里挂（不带函数）：标记对象，同样在 apply 时落地
        css = registrar("core/qss").new("helloCss", qss="QLabel#x{color:red}", theme=None)
        hello = registrar("signals#hello").new()      # 自己的信号（<id>.hello）

        # ③ 类体里声明设置（apply 时落到插件自己名下）
        volume = registrar("settings").new("volume", 50)

运行期（已经拿到插件实例）写在方法里，走 self.register(...)：

    def on_ready(self):
        self.register("settings").new("runs", 0)       # 声明
        self.register("settings").set("runs", 1)       # 写（= set_config，会触发回调）
        self.register("settings").get("runs")          # 读
        self.register("core/settings&theme").get()     # 跨桶读（显式路径）
        self.register("signals#progress").emit(0.5)    # 发自己的信号
        self.register("signals#progress").connect(self._on_progress)   # 订
        self.register("core/signals&on_game_start").emit()             # 发宿主信号
        self.register("core/tools&mdtManager").get()   # 取宿主工具（活对象）

路径语法：`/` 只分隔 owner 与 ns；条目用 `&` / `#` 接在 ns 后面
------------------------------------------------------------
    <owner>/<ns>[&seg|#seg]…

`/` 只出现一次（分开 owner 和 ns，不是目录分隔符）；条目链由 `&` / `#`
接替目录的职责，同时携带归属语义：

    "main/a&b"      条目 b 归 **接口 owner**（main） → key = main/b
    "main/a#b"      条目 b 归 **自己**（当前插件）   → key = <id>/b
    "main/a&b&c"    c 归上一段（b 的归属 main）      → key = main/b/c
    "signals#p"     自己的信号：总线名 <id>.p
    "signals&p"     接口 owner 的信号：总线名就是 p（宿主信号）
    "core/settings&launcher&java"  读 core 桶里 launcher/java 这个嵌套键

条目即子注册点：条目链也可以是一段**已声明的子接口**
    register("core/tools&mdtManager").contract(fields=("obj",), built=("obj",))
        → 把 core/tools/mdtManager 声明成接口；之后
    register("core/tools&mdtManager").new("x", …) / .list() / .contract()
        都作用在子接口上（键不再加 owner 前缀）

九个动词，每个命名空间都认同一套：

    new      登记一项（装饰器 / 标记 / 运行期都行）
    set      写值 / 顶掉已有条目 / 发信号（signals 上 emit 的别名）
    update   改自己那一条的字段 / 写设置值
    remove   摘掉自己的一条 / 删一个键
    get      读一条（条目 / 设置值 / 工具对象）
    list     列出来（接口里的条目 / 设置键 / 自己的信号名）
    owned    我名下登记的一切（按命名空间过滤）
    contract 声明 / 查看接口契约（字段表、必填、是否可覆盖）
    watch    盯变更（注册表变更 / 设置键 / 事件名）

signals 命名空间额外两个动词（它们的别名是上面的 set / watch）：

    emit    发信号：register("core/signals&on_game_start").emit(...)
    connect 订信号：@registrar("core/signals&on_game_start").connect()
            def on_start(self, ...): ...

命名空间解析（owner 段可省 = 当前插件）：

    "settings"        → 自己那一桶设置（settings.json 里 <id> 那一格）
    "core/settings"   → 宿主设置桶（跨桶读走这条显式路径）
    "signals"         → 全局事件总线（信号全走它；不再自定义 Signals 类）
    "core/tools"      → 宿主工具（mdtManager / launcher / githubAPI …）
    "core/pages"      → 普通扩展点，owner = core

装饰器与标记的落地时机统一在 `registrar.apply(plugin)`（加载器在插件构造之后
调一次）：先记标记、后登记，构造里抛异常时整场登记一起回滚。
"""

import re

from ..utils.events import events
from ..utils.registry import registry

# 动词表：所有命名空间共用同一套名字（signals 另有 emit / connect）
VERBS = ("new", "set", "update", "remove", "get", "list", "owned", "contract", "watch")

_MARK = "__bml_registrar__"

# 条目链的切分：& / # 是链符号（同时是归属符），/ 只属于 owner/ns 的第一段
_CHAIN_RE = re.compile(r"([#&])")


def _unwrap(attr):
    """取出被 staticmethod / classmethod / property 包住的那个真函数。"""
    if isinstance(attr, (staticmethod, classmethod)):
        return attr.__func__
    if isinstance(attr, property):
        return attr.fget
    return attr


def _split(path):
    """命名空间 → (owner, ns, 条目链)。

        "core/pages"             → ("core", "pages", [])
        "signals"                → (None, "signals", [])
        "signals#progress"       → (None, "signals", [("#", "progress")])
        "core/settings&theme"    → ("core", "settings", [("&", "theme")])
        "core/settings&launcher&java"
                                 → ("core", "settings", [("&", "launcher"),
                                                          ("&", "java")])
    """
    path = (path or "").strip().strip("/")
    if not path:
        raise ValueError("registrar(...) 需要一个命名空间，比如 core/pages / settings")
    # 1) 切条目链：& / # 把后面的段串起来
    parts = _CHAIN_RE.split(path)
    base = parts[0]
    chain = []
    for i in range(1, len(parts), 2):
        mode, seg = parts[i], parts[i + 1].strip("/")
        if not seg:
            raise ValueError(f"命名空间 {path!r} 的 {mode!r} 后面要跟一段名字")
        chain.append((mode, seg))
    if "/" in base:
        owner, _, ns = base.partition("/")
        if not owner or not ns:
            raise ValueError(f"命名空间 {path!r} 不合法：要写成 <owner>/<ns>")
        return owner, ns, chain
    return None, base, chain


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
    """一个命名空间的注册作用域：方法名 = 动词。"""

    __slots__ = ("path", "owner", "name", "entries", "plugin")

    def __init__(self, path, plugin=None):
        self.path = str(path or "").strip()
        self.owner, self.name, self.entries = _split(self.path)
        self.plugin = plugin        # 绑了插件实例时，运行期调用当场执行

    # ── 九个动词 ──

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
        if self.entries and name is not None and not isinstance(name, str):
            args = (name,) + args
            name = None
        if args:
            fields["value"] = args[0]
            fields["args"] = args
        return self._run_mark("set", name, fields)

    def update(self, name=None, *args, **fields):
        if callable(name) and not isinstance(name, str):
            return _Mark(self, "update", name.__name__, fields)(name)
        if self.entries and name is not None and not isinstance(name, str):
            args = (name,) + args
            name = None
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
        if self.plugin is not None or registry._session_owner is None:
            return self._exec("contract", None, fields, None)
        return _Mark(self, "contract", None, fields)

    def watch(self, name=None, callback=None, **kw):
        if callable(name) and callback is None:
            callback, name = name, None
        return self._run_mark("watch", name, dict(kw, callback=callback))

    # signals 专用：emit / connect（set / watch 是它们的别名）
    def emit(self, *args):
        return self._run_mark("emit", None, {"args": args})

    def connect(self, callback=None):
        return self._run_mark("connect", None, {"callback": callback})

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

    def _base_point(self, actor):
        """接口路径（"core/pages"）；owner 省略时算当前插件。"""
        return f"{self.owner}/{self.name}" if self.owner else f"{actor}/{self.name}"

    def _chain(self, actor):
        """条目链 → [(owner, seg)]：& 接上一段的 owner，# 回到自己。"""
        out = []
        cur = self.owner or actor
        for mode, seg in self.entries:
            out.append((cur, seg))
            cur = cur if mode == "&" else actor
        return out

    def _key(self, actor):
        chain = self._chain(actor)
        if not chain:
            return None
        first = chain[0][0]
        return "/".join([first] + [seg for _o, seg in chain])

    def _sub_point(self, actor):
        """条目链对应的子接口路径（"core/tools/mdtManager"）；没声明就是 None。"""
        if not self.entries:
            return None
        sub = f"{self.owner or actor}/{self.name}/" + "/".join(
            seg for _m, seg in self.entries)
        try:
            return sub if registry.declared(sub) else None
        except Exception:
            return None

    def _exec(self, verb, name, fields, fn):
        actor = self._actor()
        if self.name == "settings":
            return self._settings(verb, name, fields, actor, fn)
        if self.name == "signals":
            return self._signals(verb, name, fields, actor, fn)
        if self.name == "tools":
            return self._tools(verb, name, fields, actor, fn)
        return self._registry(verb, name, fields, fn, actor)

    def _settings(self, verb, name, fields, actor, fn=None):
        chain = self._chain(actor)
        owner = chain[0][0] if chain else (self.owner or actor)
        paths = [seg for _o, seg in chain]
        if verb == "contract":
            if not paths:
                raise ValueError(
                    "settings 的 contract 要写在具体点上，如 core/settings&launcher")
            _require_settings_points(owner, paths[:-1], where=self.path)
            _declare_settings_point(owner, paths)
            return {"point": _settings_point_path(owner, paths)}
        if self.plugin is None:
            raise RuntimeError(
                "设置动词要在绑定了插件的 register(...) 上调用（self.register）")
        view = self.plugin.settings
        key = "/".join(seg for _o, seg in chain) if chain else fields.get("name") or name
        sec = view if owner == actor else self.plugin.settings.other(owner)
        # 链式/& 路径（core/settings&…）允许写宿主桶：这是「按路径登记界面项」的正路
        explicit_host = bool(self.entries and self.entries[0][0] == "&")

        def _walk_get(path):
            node = sec
            for seg in path.split("/"):
                if not isinstance(node, dict):
                    return None
                node = node.get(seg)
            return node

        def _walk_set(path, value):
            segs = path.split("/")
            node = sec
            for seg in segs[:-1]:
                node = node.setdefault(seg, {})
            node[segs[-1]] = value

        def _walk_del(path):
            segs = path.split("/")
            node = sec
            for seg in segs[:-1]:
                node = node.get(seg)
                if not isinstance(node, dict):
                    raise KeyError(path)
            del node[segs[-1]]

        nested = "/" in (key or "")
        paths = [seg for _o, seg in chain]
        if paths:
            # 注册项/值的祖先点必须先注册
            need = paths if fn is not None else paths[:-1]
            _require_settings_points(owner, need, where=self.path)
        if verb == "new":
            if fn is not None:
                # 装饰器形态：声明设置键 + 登记设置页控件（section 自动分配）
                return self._settings_item(name, fields, actor, key, nested, owner,
                                           sec, _walk_get, _walk_set, fn)
            if nested and not explicit_host:
                raise KeyError(f"不能声明别人的桶 / 嵌套键：{self.path!r}")
            if nested:
                if _walk_get(key) is None and fields.get("default") is not None:
                    _walk_set(key, fields.get("default"))
                return key
            if owner != actor:
                raise KeyError(f"不能声明别人的桶：{self.path!r}")
            return view.declare(key, fields.get("default"))
        if verb in ("set", "update"):
            if owner != actor and not explicit_host:
                raise KeyError(f"别的桶不给写（覆盖许可只到自己的键）：{owner!r}")
            if nested:
                _walk_set(key, fields.get("value"))
                return None
            self.plugin.set_config(key, fields.get("value"))
            return None
        if verb == "remove":
            if owner != actor or nested:
                return None
            try:
                del view[key]
            except KeyError:
                pass
            view.defaults.pop(key, None)
            return None
        if verb == "get":
            if nested:
                return _walk_get(key)
            return sec.get(key)
        if verb == "list":
            return list(sec)
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
            return self.plugin.watch_config(key, cb)
        raise ValueError(f"settings 不支持动词 {verb!r}")

    def _settings_item(self, name, fields, actor, key, nested, owner, sec,
                       walk_get, walk_set, fn):
        """装饰器形态的 settings 项：声明设置键 + 登记设置页控件（section 自动分配）。

            @registrar("core/settings&launcher&java").new(name="probeaaa", title="…")
            def probe(self, ctx):
                return Widgets.Bool(ctx.parent, ctx.title)

        值的地址 = 同一命名空间再 & 上名字：
            register("core/settings&launcher&java&probeaaa").get() / .set(...)

        section：按链路径自动找内置分组（launcher/java → 「全局java」组
        core.setting.java），找不到就落到插件组 core.setting.plugins。
        """
        name = fields.get("name") or name or (key or "").split("/")[-1]
        if not name:
            raise ValueError("settings 的 new 需要 name=（设置键名）")
        title = fields.get("title")
        if not title:
            raise ValueError(f"settings 项 {name!r} 需要 title=（语言键）")

        path = f"{key}/{name}" if key else name
        try:
            exists = walk_get(path) is not None
        except Exception:
            exists = False
        if not exists and fields.get("default") is not None:
            walk_set(path, fields.get("default"))

        # section 自动分配：链里的分组名 → core.setting.<分组>；没有就进插件组
        segs = [seg for _m, seg in self.entries]
        group = segs[-1] if segs else ""
        section = "core.setting.plugins"
        if group:
            norm = f"core/setting/{group}"
            dotted = f"core.setting.{group}"
            for e in registry.entries("core/setting/sections"):
                if e.key in (norm, dotted):
                    section = dotted
                    break

        init = _builder(self.plugin, fn, dict(fields))

        return registry.add("core/setting/items", f"{actor}/{name}",
                            init=init, section=section,
                            title=title)

    # 信号：全局总线
    def _signals(self, verb, name, fields, actor, fn=None):
        chain = self._chain(actor)
        owner = chain[0][0] if chain else actor
        key = "/".join(seg for _o, seg in chain) if chain else name
        if key and (key.startswith(f"{owner}.") or key.startswith("core.")):
            bus = key
        elif key:
            bus = key if owner == "core" else f"{owner}.{key}"
        else:
            bus = ""

        if verb == "new":
            events.register(bus)
            return bus
        if verb in ("emit", "set"):
            events.emit(bus, *fields.get("args", ()))
            return None
        if verb in ("connect", "watch"):
            cb = fields.get("callback")
            if cb is None and fn is not None:
                cb = getattr(self.plugin, fn.__name__) if self.plugin is not None \
                    else getattr(fn, "__func__", fn)
            if cb is None:
                raise ValueError("connect 需要一个回调")
            events.on(bus, cb, owner=actor)
            return cb
        if verb == "update":
            raise ValueError("signals 不支持 update（换签名请重新 new）")
        if verb == "remove":
            raise ValueError("signals 不支持 remove")
        if verb == "get":
            holder = events._holders.get(bus)
            return holder.signal if holder is not None else None
        if verb == "list":
            return sorted(n for n in events.names() if n.startswith(f"{actor}."))
        if verb == "owned":
            return sorted(n for n in events.names() if n.startswith(f"{actor}."))
        if verb == "contract":
            return {"namespace": "signals", "prefix": f"{actor}."}
        raise ValueError(f"signals 不支持动词 {verb!r}")

    # 工具：宿主把 mdtManager / launcher / githubAPI … 登记到 core/tools
    def _tools(self, verb, name, fields, actor, fn=None):
        point = self._base_point(actor)
        sub = self._sub_point(actor)
        if sub is not None and verb not in ("contract",):
            point = sub
        key = self._key(actor)
        if verb == "get":
            entry = registry.entry(point, key) if key else None
            return entry.obj if entry is not None else None
        if verb == "list":
            return [e.key for e in registry.entries(point)]
        if verb == "owned":
            return [e.key for e in registry.entries(point)
                    if e.key.startswith(f"{actor}/")]
        if verb == "contract":
            if self.entries:
                return registry.declare(sub, registrant=actor, **fields)
            return registry.declare(point, registrant=actor, **fields)
        if verb == "new":
            return registry.add(point, key, **fields)
        if verb == "set":
            return registry.set(point, key, by=actor, **fields)
        if verb == "update":
            return registry.update(point, key, **fields)
        if verb == "remove":
            return registry.remove(point, key)
        raise ValueError(f"tools 不支持动词 {verb!r}")

    # 普通扩展点：registry 那套（条目链若已声明成子接口，就按接口操作）
    def _registry(self, verb, name, fields, fn, actor):
        point = self._base_point(actor)
        key = self._key(actor)
        sub = self._sub_point(actor)
        if sub is not None and verb not in ("contract",):
            point, key = sub, None
        if verb == "contract":
            if self.entries:
                return registry.declare(sub, registrant=actor, **fields)
            return registry.declare(point, registrant=actor, **fields)
        if key is None and name:
            key = f"{actor}/{name}"
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


_SETTINGS_POINTS = set()


def _settings_point_path(owner, segs):
    return f"{owner}/settings" + "".join(f"&{seg}" for seg in segs)


def _declare_settings_point(owner, segs):
    _SETTINGS_POINTS.add((owner, tuple(segs)))


def _require_settings_points(owner, segs, where):
    """每一级祖先都必须已注册；报错里直接给出该敲的那句。"""
    for i in range(1, len(segs) + 1):
        if (owner, tuple(segs[:i])) in _SETTINGS_POINTS:
            continue
        pre = _settings_point_path(owner, segs[:i])
        raise KeyError(
            f"{where!r}: 设置点 {pre!r} 还没注册"
            f"（先 register({pre!r}).contract()，再往下注册/登记）")


def settings_points():
    """已注册的设置点（排查用）。"""
    return sorted(_settings_point_path(o, s) for o, s in _SETTINGS_POINTS)


def ready(plugin_id):
    """（保留位）就绪钩子现在是 Plugin.on_ready 方法，不再走注册标记。"""
    return list(_READY.pop(plugin_id, ()))


def discard(plugin_id):
    """丢掉某个插件攒下的就绪回调（加载失败回滚时调）。"""
    _READY.pop(plugin_id, None)
