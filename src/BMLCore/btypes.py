# -*- coding: utf-8 -*-
"""注册中心 v3 原型：万物皆 BType。

    - BTypes    类型库（名字 ↔ 类）；内置 core/type / core/point / core/signal / core/value
    - BType     底座（像 QObject）：带操作自己存储库的函数
    - BPoint    注册点：内置收条目 / 按 key 取 / 变更通知 / 产物槽（point= 声明接受哪些条目类型）
    - BSignal   包一层 Qt Signal
    - BValue    包一个标量（string / int …）

    @BTypes.new("aaa")
    class Aaa(BTypes.get("core/type")):
        init = {"a": "core/signal", "b": "core/point"}   # 成员：构造时自动造好

    register("core/signals&on_start")     # 返回同一个 BSignal 实例（缓存复用）
    register("core/settings&theme")       # 返回同一个 BValue 实例
    BTypes.get("aaa")()                   # 拿类型 → 造实例

循环依赖：类型成员（init）之间成环、或类型自己引用自己，在 BTypes.new 时就拒绝；
运行期再兜一层「正在构造」的守卫。
"""

import re

from PySide6.QtCore import QObject, Signal

_MISSING = object()


# ─────────────────────────── 类型库 ───────────────────────────

class BTypes:
    """全局类型库：名字 → 类（所有 BType 子类都在这里）。"""

    _types = {}

    @classmethod
    def new(cls, name):
        """装饰器：登记一个类型。登记时就做循环依赖检查。"""
        name = str(name).strip()
        if not name:
            raise ValueError("BTypes.new 需要类型名")
        if "/" not in name:
            raise ValueError(f"类型名 {name!r} 要带命名空间，如 core/point / myplugin/storage")

        def deco(klass):
            if name in cls._types:
                raise ValueError(f"类型 {name!r} 已经登记过")
            if not (isinstance(klass, type) and issubclass(klass, BType)):
                raise TypeError(f"{name!r} 的类必须继承 BType")
            cls._types[name] = klass
            try:
                cls._check_members(klass, name)
                cls._check_cycle(name)
            except Exception:
                del cls._types[name]
                raise
            return klass
        return deco

    @classmethod
    def get(cls, name):
        """取类型类；找不到直接报错（调用方拿到的永远是活类）。"""
        try:
            return cls._types[name]
        except KeyError:
            raise KeyError(
                f"类型 {name!r} 不存在；已登记：{sorted(cls._types)}") from None

    @classmethod
    def names(cls):
        return sorted(cls._types)

    @classmethod
    def _reverse_name(cls, klass):
        """类 → 登记名（BType 实例打印/找自己名字用）。"""
        for name, k in cls._types.items():
            if k is klass:
                return name
        return klass.__name__

    # ── 成员与循环检查 ──

    @classmethod
    def _init_map(cls, klass):
        """合并 MRO 上的 init（子类覆盖父类同名成员）。"""
        merged = {}
        for base in reversed(klass.__mro__):
            merged.update(getattr(base, "init", {}) or {})
        return merged

    @classmethod
    def _check_members(cls, klass, name):
        for member, ref in cls._init_map(klass).items():
            if ref not in cls._types:
                raise KeyError(
                    f"{name!r} 的成员 {member!r} 引用类型 {ref!r}，但它还没登记"
                    f"（先 BTypes.new({ref!r})）")

    @classmethod
    def _check_cycle(cls, name, path=()):
        """DFS：类型成员图里成环 → 直接拒绝（a→aa→a 这种）。"""
        if name in path:
            chain = " → ".join(list(path) + [name])
            raise ValueError(f"类型成员循环依赖：{chain}")
        klass = cls._types.get(name)
        if klass is None:
            return
        for member, ref in cls._init_map(klass).items():
            cls._check_cycle(ref, path + (name,))


# ─────────────────────────── 底座 ───────────────────────────

class BType:
    """万物底座（像 QObject）：成员声明在类上的 init，实例化后收进 self.init。

        init = {"a": "core/signal", "b": "core/point"}   # 类上的声明（备份不动）

    构造时按 init 自动造好成员，落在实例自己的 `self.init[成员名]` 里：

        inst = BTypes.get("example/status")()
        inst.init["value"]      # BValue
        inst.init["changed"]    # BSignal

    类上的 `init` 是声明本身，实例不会覆盖它（`self.init` 是实例字典）。
    子类可以加字段与方法；下游用 BTypes.get(名) 拿到类。
    """

    init = {}            # 类上：成员声明（名字 → 类型名）；实例上：成员字典

    _building = set()    # 运行期守卫：同一类型递归构造 → 报循环

    def __init__(self, name=""):
        self.name = str(name or "")
        cls = type(self)
        tname = BTypes._reverse_name(cls)
        if tname in BType._building:
            raise RuntimeError(
                f"类型 {tname!r} 正在构造中又请求构造它（成员循环依赖）")
        # 备份类上的原始声明（self.init 即将变成实例字典，声明本身留在这儿可查）
        self._init_def = dict(BTypes._init_map(cls))
        self.init = {}
        BType._building.add(tname)
        try:
            for member, ref in self._init_def.items():
                self.init[member] = BTypes.get(ref)()
        finally:
            BType._building.discard(tname)

    def type_name(self):
        return BTypes._reverse_name(type(self))

    def member(self, name):
        """取一个成员（self.init[name] 的便捷写法）。"""
        try:
            return self.init[name]
        except KeyError:
            raise KeyError(
                f"{self.type_name()} 没有成员 {name!r}（init 里有：{sorted(self.init)}）") from None

    def __repr__(self):
        return "<%s %s init=%d>" % (self.type_name(), self.name, len(self.init))


# ─────────────────────────── 会话（加载期暂存 + 两阶段提交）──

_SESSION = None


def in_session():
    return _SESSION is not None


_ACTOR_STACK = []      # 显式上下文：插件构造/on_ready 调用期间，当前是谁


def _current_owner():
    """当前发起方：显式上下文 > 会话主人 > core。"""
    if _ACTOR_STACK:
        return _ACTOR_STACK[-1]
    return _SESSION["owner"] if _SESSION is not None else "core"


class actor_context:
    """with actor_context("example_x"): ... —— 期间 register() 认这个 owner。"""

    def __init__(self, owner):
        self.owner = str(owner)

    def __enter__(self):
        _ACTOR_STACK.append(self.owner)
        return self.owner

    def __exit__(self, *exc):
        _ACTOR_STACK.pop()
        return False


def _stage(op):
    _SESSION["ops"].append(op)


def begin(owner):
    """开一次加载会话：期间的 add/set/remove 先暂存，commit 才并进正表。"""
    global _SESSION
    if _SESSION is not None:
        raise RuntimeError(
            f"已经在加载会话里（{_SESSION['owner']!r}），不能嵌套")
    _SESSION = {"owner": str(owner), "token": object(), "ops": [], "staged": {}}
    return _SESSION["token"]


def _end_session(token=None, force=False):
    if _SESSION is None:
        return False
    if not force and token is not None and _SESSION["token"] is not token:
        raise RuntimeError("会话凭据不对：不是开这个会话的一方")
    return True


def commit(token=None, *, force=False):
    """把暂存区并进正表（先全量应用；中途炸掉由调用方 abort）。"""
    global _SESSION
    if not _end_session(token, force):
        return False
    s = _SESSION
    try:
        for op in s["ops"]:
            point = op["point"]
            if op["op"] == "remove":
                point.remove(op["key"], owner=op["owner"])
            elif op["op"] == "add":
                if point._top(op["key"]) is None:
                    point._push(op["key"], op["owner"], op["inst"])
            else:  # set
                point._push(op["key"], op["owner"], op["inst"])
    finally:
        _SESSION = None
    return True


def abort(token=None, *, force=False):
    """丢掉暂存区（加载失败回滚）。"""
    global _SESSION
    if not _end_session(token, force):
        return False
    _SESSION = None
    return True


# ─────────────────────────── 注册点 ───────────────────────────

class BPoint(BType):
    """注册点：接收条目（归属即桶 + 覆盖栈 + 契约 + 会话）。

    自带：
        条目表  add / get / set / update / remove / keys / entries
                 add(名字, type="core/point", title=…, icon=…) 就是「建一个带元数据的组」；
                 子类想改行为就覆写 add 并 super().add(…)
        归属    by=登记人；unload(owner) 整片摘掉它登记的
        覆盖栈  同一个 key 上多份按 by/seq 叠着，顶掉的不丢
        契约    declare_contract(fields=…, required=…, override=…, calling_mode=…)
        通知    watch(cb)；条目增删改时回调
        产物槽  bind / provide / unbind / built
        接受表  point —— 这个点允许收的条目类型（子类可覆盖）
    """

    point = ("core/value", "core/signal", "core/point",        # 接受的条目类型
             "core/log", "core/lang", "core/settings", "core/setting")
    _entry_type = "core/value"                            # 默认条目类型

    def __init__(self, name=""):
        super().__init__(name)
        self._layers = {}       # key -> [{"by": owner, "seq": n, "inst": BType}, ...]
        self._seq = 0
        self._watchers = []
        self._built = {}
        self._contract = None

    # ── 契约 ──

    def declare_contract(self, fields=(), required=(), built=(),
                         override=True, calling_mode=("class",), doc=""):
        self._contract = {
            "fields": tuple(fields), "required": tuple(required),
            "built": tuple(built), "override": bool(override),
            "calling_mode": tuple(calling_mode), "doc": doc,
        }
        return self._contract

    def contract(self):
        return self._contract

    def _check(self, fields, key, mode="add"):
        c = self._contract
        if c is None:
            return
        unknown = sorted(set(fields) - set(c["fields"]) - {"owner"})
        if unknown:
            raise KeyError(
                f"{self.name}#{key}: 未知字段 {unknown}；该接口只接受 {sorted(c['fields'])}")
        merged = {}
        if self._layers.get(key):
            merged.update(self._layers[key][-1]["inst"].__dict__)
        merged.update(fields)
        missing = [f for f in c["required"] if f not in merged]
        if missing:
            raise KeyError(f"{self.name}#{key}: 缺必填字段 {missing}")
        if "order" in fields and not isinstance(fields["order"], (int, float)):
            raise KeyError(f"{self.name}#{key}: order 必须是数字")
        if not c["override"] and self._layers.get(key) \
                and self._layers[key][-1]["by"] != _current_owner():
            raise KeyError(f"{self.name}#{key}: 这条不开放覆盖（override=false）")
        if not in_session() and "function" not in c["calling_mode"]:
            raise KeyError(
                f"{self.name}: 这个接口只接受加载期声明（calling_mode 不含 function）")

    # ── 条目表（覆盖栈） ──

    def add(self, key, type=None, entry=None, **fields):
        key = str(key)
        owner = fields.pop("owner", None) or _current_owner()
        if self._top(key) is not None or self._staged(key) is not None:
            return self._top(key) or self._staged(key)
        entry_type = type or self._entry_type
        if entry_type not in self.point:
            raise ValueError(
                f"{self.name or self.type_name()}: 不收 {entry_type!r} 类型的条目"
                f"（point={list(self.point)}）")
        self._check(fields, key)
        inst = BTypes.get(entry_type)(name=f"{self.name}.{key}".strip("."))
        inst.key = key        # 条目/子点记着自己的 key（对账、日志、界面都用得上）
        if entry is not None:
            # 子点：用 entry= 声明它收什么类型的条目
            BTypes.get(entry)
            inst._entry_type = entry
            inst.point = tuple(dict.fromkeys(tuple(inst.point) + (entry,)))
        for f, v in fields.items():
            setattr(inst, f, v)
        if in_session():
            _stage({"op": "add", "point": self, "key": key,
                    "owner": owner, "inst": inst})
            _SESSION["staged"][(id(self), key)] = inst
        else:
            self._push(key, owner, inst)
        return inst

    def get(self, key):
        key = str(key)
        inst = self._staged(key)
        if inst is None:
            inst = self._top(key)
        if inst is None:
            # 宿主（core）手下登记的点作为下属面板：插件自己的点上 get("core/tools") 也能拿到
            host = _OWNER_POINTS.get("core")
            if host is not None and host is not self and host.has(key):
                return host.get(key)
            raise KeyError(f"{self.name or self.type_name()} 下没有条目 {key!r}")
        return inst

    def has(self, key):
        key = str(key)
        return self._staged(key) is not None or self._top(key) is not None

    def set(self, key, type=None, **fields):
        """顶掉已有条目：新的一份压栈顶，旧的留着（顶的人走了自动还回）。"""
        key = str(key)
        owner = fields.pop("owner", None) or _current_owner()
        if self._top(key) is None and self._staged(key) is None:
            return self.add(key, type=type, owner=owner, **fields)
        self._check(fields, key, "set")
        entry_type = type or self._entry_type
        inst = BTypes.get(entry_type)(name=f"{self.name}.{key}".strip("."))
        inst.key = key        # 条目/子点记着自己的 key（对账、日志、界面都用得上）
        for f, v in fields.items():
            setattr(inst, f, v)
        if in_session():
            _stage({"op": "set", "point": self, "key": key,
                    "owner": owner, "inst": inst})
            _SESSION["staged"][(id(self), key)] = inst
        else:
            self._push(key, owner, inst)
        return inst

    def update(self, key, **fields):
        """改自己那一条的字段（不产生新层）。"""
        key = str(key)
        owner = fields.pop("owner", None) or _current_owner()
        layers = self._layers.get(key)
        top = self._staged(key) or self._top(key)
        if top is None:
            raise KeyError(f"{self.name}#{key}: 没有条目，无法 update")
        if layers and layers[-1]["by"] != owner and not in_session():
            raise KeyError(f"{self.name}#{key} 不是你登记的，不能 update")
        self._check(fields, key, "update")
        for f, v in fields.items():
            setattr(top, f, v)
        self._notify(key)
        return top

    def remove(self, key, owner=None):
        key = str(key)
        owner = owner or _current_owner()
        if in_session():
            _stage({"op": "remove", "point": self, "key": key, "owner": owner})
            return None
        layers = self._layers.get(key, [])
        kept = [l for l in layers if l["by"] != owner]
        if kept:
            self._layers[key] = kept
        else:
            self._layers.pop(key, None)
        if len(kept) != len(layers):
            self._notify(key)
        return None

    def unload(self, owner):
        """整片摘掉某个 owner 登记的条目（插件卸载时调）。"""
        removed = []
        for key in list(self._layers):
            kept = [l for l in self._layers[key] if l["by"] != owner]
            if kept:
                self._layers[key] = kept
            else:
                del self._layers[key]
                removed.append(key)
        for key in removed:
            self._built.pop(key, None)
            self._notify(key)
        return removed

    def owned(self, owner):
        return sorted(k for k, layers in self._layers.items()
                      if any(l["by"] == owner for l in layers))

    def keys(self):
        """登记顺序（不是字母序，也没有 order 权重）：先加的排在前面。"""
        return list(self._layers)

    def entries(self):
        return [self._top(k) for k in self.keys()]

    # ── 栈内工具 ──

    def _top(self, key):
        layers = self._layers.get(key)
        return layers[-1]["inst"] if layers else None

    def _staged(self, key):
        if not in_session():
            return None
        return _SESSION.get("staged", {}).get((id(self), key))

    def _push(self, key, owner, inst):
        self._seq += 1
        self._layers.setdefault(key, []).append(
            {"by": owner, "seq": self._seq, "inst": inst})
        self._built.setdefault(key, {})
        self._notify(key)

    # ── 通知 ──

    def watch(self, callback):
        self._watchers.append(callback)
        return callback

    def unwatch(self, callback):
        if callback in self._watchers:
            self._watchers.remove(callback)

    def _notify(self, key):
        for cb in list(self._watchers):
            try:
                cb(key)
            except Exception:
                pass

    # ── 产物槽 ──

    def bind(self, key, **built):
        self._built.setdefault(str(key), {}).update(built)
        return self._built[str(key)]

    def provide(self, key, obj):
        self.add(key)
        return self.bind(key, obj=obj)

    def unbind(self, key, *names):
        slot = self._built.get(str(key), {})
        for n in names:
            slot.pop(n, None)

    def built(self, key):
        return self._built.get(str(key), {})


# ─────────────────────────── 信号 / 值 ───────────────────────────

class _SigHolder(QObject):
    changed = Signal(object)


class BSignal(BType):
    """包一层 Qt Signal：emit / connect / disconnect。"""

    def __init__(self, name=""):
        super().__init__(name)
        self._holder = _SigHolder()

    def emit(self, *args):
        payload = args[0] if len(args) == 1 else (args if args else None)
        self._holder.changed.emit(payload)

    def connect(self, callback):
        self._holder.changed.connect(callback)
        return callback

    def disconnect(self, callback=None):
        if callback is None:
            self._holder.changed.disconnect()
        else:
            self._holder.changed.disconnect(callback)


class BEventSignal(BSignal):
    """把宿主 events 总线上的信号包成 v3 条目。

    和 BSignal 的区别：它不自带一个 Qt Signal，而是**转发**到 events 总线：

        @registrar("core/signals&on_game_start").connect()
        def on_start(*a): ...

        register("core/signals&on_game_start").emit(1, 2)   # → events.emit("on_game_start", 1, 2)

    订阅记在当前 owner 名下，卸载时自动摘。
    """

    def __init__(self, name="", events_name=None, bus=None):
        super().__init__(name)
        self.events_name = events_name or name
        self.bus = bus

    def _bus(self):
        if self.bus is not None:
            return self.bus
        from ..utils.events import events
        return events

    def emit(self, *args):
        self._bus().emit(self.events_name, *args)

    def connect(self, callback):
        self._bus().on(self.events_name, callback, owner=_current_owner())
        return callback

    def disconnect(self, callback=None):
        try:
            self._bus().off(self.events_name, callback)
        except Exception:
            pass


class BValue(BType):
    """包一个标量（string / int / 默认值），带 value_changed 信号。

        v = BValue(value=1)
        v.value_changed.connect(cb)    # 成员 自动就位（init）
        v.set(2)                        # 値变了会发 value_changed
    """

    init = {"value_changed": "core/signal"}

    def __init__(self, name="", value=None):
        super().__init__(name)
        self.value = value

    @property
    def value_changed(self):
        return self.init["value_changed"]

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        try:
            self.value_changed.emit(value)
        except Exception:
            pass
        return self


# ─────────────────────────── 启动器内置功能 ───────────────────────────

class BLog(BType):
    """包宿主日志器：register().get("core/log").get("main").info("…")。"""

    def __init__(self, name="", logger=None):
        super().__init__(name)
        self.logger = logger

    def _log(self, level, msg, **kw):
        target = self.logger
        if target is None:
            return
        getattr(target, level, target.info)(str(msg), **kw)

    def debug(self, msg, **kw):
        self._log("debug", msg, **kw)

    def info(self, msg, **kw):
        self._log("info", msg, **kw)

    def warning(self, msg, **kw):
        self._log("warning", msg, **kw)

    def error(self, msg, **kw):
        self._log("error", msg, **kw)


class BLang(BType):
    """包宿主翻译器：register().get("core/lang").get("main").get(键)。"""

    def __init__(self, name="", tr=None):
        super().__init__(name)
        self.tr = tr

    def get(self, key, *args):
        if self.tr is None:
            return key
        try:
            return self.tr(key, *args)
        except Exception:
            return key


class BSettings(BType):
    """包宿主设置：register().get("core/settings").get("main")。

        .get(键)                读 core 桶
        .set(键, 值)            写 core 桶
        .other(owner)           读别的桶（插件自己的命名空间）
    """

    def __init__(self, name="", settings=None):
        super().__init__(name)
        self.settings = settings

    def get(self, key, default=None):
        try:
            return self.settings[key]
        except Exception:
            return default

    def set(self, key, value):
        self.settings[key] = value
        return value

    def other(self, owner):
        return self.settings.bucket(owner)


# ─────────────────────────── 设置组点（覆写 add） ───────────────────────────

_MISSING_VALUE = object()


class BSettingPoint(BPoint):
    """设置组点：覆写 add。

    设置条目 = 「加一个控件」，元数据（标题/默认值）手动传；
    add 里先调 super().add 保留基础行为，再：
        - default=… 把初值写进条目（BValue.set）
        - build=fn 把控件构造器挂在条目上，界面取它建控件

        group = register("core/setting")          # BSettingPoint
        group.add("probe", default=True, build=lambda ctx: Widgets.Bool(ctx.parent, "开关"))
    """

    point = ("core/value", "core/signal", "core/point",
             "core/log", "core/lang", "core/settings", "core/setting")

    def add(self, key, type=None, entry=None, default=_MISSING_VALUE,
            build=None, **fields):
        item = super().add(key, type=type, entry=entry, **fields)
        if default is not _MISSING_VALUE:
            try:
                item.set(default)
            except Exception:
                pass
        if build is not None:
            item.build = build
        return item


# ─────────────────────────── 内置类型登记 ───────────────────────────

BTypes._types.update({
    "core/type": BType,
    "core/point": BPoint,
    "core/signal": BSignal,
    "core/eventsignal": BEventSignal,
    "core/value": BValue,
    "core/log": BLog,
    "core/lang": BLang,
    "core/settings": BSettings,
    "core/setting": BSettingPoint,
})


# ─────────────────────────── 取自己的注册点（register()）──
#
# register() 不带参数：当前 owner 自己的那个 BPoint。
#     - 插件加载期（会话主人 = 插件 id）→ 插件自己的点
#     - 宿主启动期（没有会话）→ core 的点
# 自己的子点/条目都往它上面 add；宿主（core）手下登记的点作为它的子项，
# 插件侧用 `register().get("core/tools")` 这样取 —— 名字是子项 key，
# 不是"某个空间"的字符串路径，语法上也就不存在"往任意空间写"这个口子。
_OWNER_POINTS = {}     # owner → 它自己的 BPoint


def _own_point():
    owner = _current_owner()
    point = _OWNER_POINTS.get(owner)
    if point is None:
        point = BTypes.get("core/point")(name=owner)
        _OWNER_POINTS[owner] = point
    return point


def register(path=None):
    """取注册点 / 条目。

        register()               → 当前 owner 自己的点
        register("core/log")     → 宿主点下的条目（直接拿到 BLog）
        register("parts")        → 自己点下的子点/条目

    先尝试整名（"core/log" 是一个 key），不行再逐段往下找；
    不存在就报 KeyError，不会静默造出来。
    """
    point = _own_point()
    if path is None or not str(path).strip():
        return point
    key = str(path).strip().strip("/")
    if point.has(key):
        return point.get(key)
    host = _OWNER_POINTS.get("core")
    if host is not None and host is not point and host.has(key):
        return host.get(key)
    node = point
    for seg in key.split("/"):
        node = node.get(seg)
    return node


def unload(owner):
    """整片摘掉某个 owner 的全部痕迹（插件卸载时调）。

    自己点上的条目、以及自己作为子点被挂到别处的那一份，全部摘掉；
    core 的点永远留着。
    """
    removed = []
    point = _OWNER_POINTS.get(owner)
    if point is not None:
        removed.extend(point.unload(owner))
        if owner != "core":
            for other in _OWNER_POINTS.values():
                if other is point:
                    continue
                other.remove(owner, owner=owner)
            _OWNER_POINTS.pop(owner, None)

    # 别处的点（尤其是宿主的 core/setting 这类）上也可能有他登记的条目：
    # 插件把设置项挂进宿主的分组子点，卸载时同样得摘掉，不然界面上留着一个
    # 连着已卸载实例的开关。
    for host_point in list(_OWNER_POINTS.values()):
        _unload_deep(host_point, owner, removed)
    return removed


def _unload_deep(point, owner, removed):
    """把一个点、以及它名下所有的子点，都摘一遍 owner 的条目。"""
    removed.extend(point.unload(owner))
    for key in point.keys():
        child = point._top(key)
        if isinstance(child, BPoint):
            _unload_deep(child, owner, removed)


# ─────────────────────────── registrar(path)：装饰器语法 ───────────────────────────
#
# 装饰器专用：
#     @registrar("settings$launcher$java$select_java.value_changed").connect()
#     def aaa(value=None): ...
#
# 路径分隔：`$` / `&` / `#` 都当链分隔；最后一段可以是「条目.属性」，
# 属性指向条目的成员（比如 BValue.value_changed → BSignal）。
# 不带 @ 时也能当普通取用：registrar("core/log").info("…")。

_CHAIN_SPLIT = re.compile(r"[$&#]")


def _resolve_dsl(path):
    """把 "a$b$c.x" 解析成 (条目实例, 属性名或 None)。"""
    text = str(path or "").strip().strip("/")
    if not text:
        raise ValueError("registrar(...) 需要一个路径")
    segs = [seg.strip() for seg in _CHAIN_SPLIT.split(text) if seg.strip()]
    if not segs:
        raise ValueError(f"registrar({path!r}) 解析不出来")
    node = register()
    for seg in segs:
        name, _, attr = seg.rpartition(".") if "." in seg else (seg, "", "")
        if attr:
            target = node.get(name)
            return getattr(target, attr), name
        node = node.get(seg)
    return node, None


class _Dsl:
    """registrar(path) 返回的作用域：connect / emit 是装饰器友好的。"""

    def __init__(self, path):
        self.path = str(path)

    # 装饰器形态：不带回调返回装饰器；带回调直接订（仍返回回调）
    def connect(self, callback=None):
        target, _name = _resolve_dsl(self.path)
        if callback is None:
            def deco(fn):
                target.connect(fn)
                return fn
            return deco
        target.connect(callback)
        return callback

    def emit(self, *args):
        target, _name = _resolve_dsl(self.path)
        target.emit(*args)
        return None

    def __getattr__(self, item):
        # 其余能力直接落到「解析出来的那个对象」上（info / get / set …）
        target, _name = _resolve_dsl(self.path)
        return getattr(target, item)


def registrar(path):
    """装饰器专用作用域；也支持 registrar("core/log").info(...) 这种直用。"""
    return _Dsl(path)


__all__ = ["BTypes", "BType", "BPoint", "BSignal", "BValue", "register",
           "begin", "commit", "abort", "in_session", "unload"]
