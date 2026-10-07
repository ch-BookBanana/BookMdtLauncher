# -*- coding: utf-8 -*-
"""注册装饰器族 —— 照 NcatBot 的 registrar：往哪儿登记写在方法上，参数写在自己那行。

    from BMLCore import BMLPlugin, registrar

    class Hello(BMLPlugin):
        id = "example_hello"

        @registrar.setting(title="hello.greet")          # 默认进设置页「插件」那一组
        def build_greet(self, ctx):
            return Widgets.Bool(ctx.parent, ctx.title)

        @registrar.page(title="hello.page", order=50)
        def build_page(self, ctx):
            return MyPage(ctx.parent)

        @registrar.tray(title="hello.about")
        def about(self):
            self.log("点了「关于」")

        @registrar.on("start_gameChanged")
        def on_game(self, data):
            self.log("切了游戏：%s" % (data,))

        @registrar.on_ready()
        def ready(self):
            self.log("所有插件都加载完了")

        styles = registrar.qss("QLabel#helloTitle { font-weight: bold; }", theme=None)

装饰器只做标记；真正登记发生在加载器 `registrar.apply(plugin)` 那一步 —— 也就是
插件构造之后、任何界面构建之前。构建函数收到的 `ctx` 是个 `Ctx`，里面只有 `parent`
（挂哪）和 `title`（登记时的语言键）；容器那类还会多一个 `items`（它容纳的条目）。
不玩「任意字段都能从 ctx 上取到」那一套。
"""

from .Plugin import Ctx

# 标记挂在函数对象上：{kind: [meta, …]}
# 每个 kind 底下是**列表**：一个方法挂两个 @registrar.on("a") / ("b") 时两条都要
# 生效（以前是字典单值，后写的静默盖掉先写的，插件作者只看到「有一条没登记」）。
_MARK = "__bml_registrar__"


def _unwrap(attr):
    """取出被 staticmethod / classmethod / property 包住的那个真函数。"""
    if isinstance(attr, (staticmethod, classmethod)):
        return attr.__func__
    if isinstance(attr, property):
        return attr.fget
    return attr


def _mark(kind, meta):
    def deco(fn):
        target = _unwrap(fn)
        if target is None or not callable(target):
            raise TypeError(
                f"registrar.{kind} 只能写在普通方法上，收到 {type(fn).__name__}"
                f"（property 之类不支持：登记发生在构造之后，取值语义对不上）")
        marks = {k: list(v) for k, v in getattr(target, _MARK, {}).items()}
        marks.setdefault(kind, []).append(meta)
        setattr(target, _MARK, marks)
        return fn
    return deco


# ─────────────────────────── 界面登记 ───────────────────────────

def page(title, *, icon=None, order=100):
    """主窗口左栏的一个页面：函数返回一个 QWidget（参数是 ctx）。"""
    return _mark("page", {"title": title, "icon": icon, "order": order})


def overlay(title, *, order=100):
    """叠加层页面（带遮罩居中）：函数返回一个 QWidget。"""
    return _mark("page_overlay", {"title": title, "order": order})


def stack(title, *, order=100):
    """整页浮层栈的页面：函数返回一个 QWidget。"""
    return _mark("page_stack", {"title": title, "order": order})


def section(title, *, order=200):
    """设置页里的一个分组容器：函数返回一个 QWidget（`ctx.items` 是这组容纳的条目）。"""
    return _mark("section", {"title": title, "order": order})


def setting(title, *, section="core.setting.plugins", order=900):
    """设置页里的一项：函数返回一个 QWidget。"""
    return _mark("setting", {"title": title, "section": section, "order": order})


def game_page(title, *, icon=None, order=100):
    """游戏管理浮层左栏的一个功能页：函数返回一个 QWidget。"""
    return _mark("game_page", {"title": title, "icon": icon, "order": order})


def tray(title, *, order=100):
    """托盘右键菜单的一项：函数无参，点了就调用它。"""
    return _mark("tray", {"title": title, "order": order})


def _qss_value(css, theme, order):
    class _Qss:
        def __init__(self):
            self.fields = {"qss": css, "theme": theme, "order": order}

        def __repr__(self):
            return "<registrar.qss theme=%r %d 字节>" % (theme, len(css))
    return _Qss()


def qss(css, *, theme=None, order=100):
    """往全局样式表追加一段 css。当成**类属性**用：

        styles = registrar.qss("QLabel#x { color: red; }", theme=True)

    theme：None = 两套主题都加，True = 只浅色，False = 只深色。
    """
    return _qss_value(css, theme, order)


# ─────────────────────────── 事件与就绪 ───────────────────────────

def on(event):
    """订阅事件：函数收到的参数就是 emit 来的那些。"""
    return _mark("on", {"event": event})


def on_ready():
    """所有插件加载完、界面构建之前调一次（依赖者与被依赖者都已就位）。"""
    return _mark("ready", {})


# ─────────────────────────── 收集与落地 ───────────────────────────

def collect(cls):
    """按 MRO 收集一个插件类上的全部标记，子类覆盖父类同名方法时以子类为准。

    返回 [(kind, name, meta, fn)]，name 是方法名（用来去重）。
    """
    out = []
    seen = set()
    used_fns = set()
    for base in cls.__mro__:
        for name, attr in vars(base).items():
            if name in seen:
                continue
            seen.add(name)
            fn = _unwrap(attr)
            marks = getattr(fn, _MARK, None)
            if not marks:
                continue
            if isinstance(attr, property):
                raise TypeError(
                    f"{cls.__name__}.{name}：带 registrar 标记的方法被 property 包住了，"
                    f"这样登记不到（取值语义对不上）。把 property 去掉，或换个方法名")
            # 同一个函数挂两个名字（`h1 = h2 = marked`）只登记一次 ——
            # 否则同一个 bound method 会被订两遍，emit 一次回调跑两次。
            if id(fn) in used_fns:
                continue
            used_fns.add(id(fn))
            for kind, metas in marks.items():
                for meta in metas:
                    out.append((kind, name, meta, fn))
    return out


def apply(plugin):
    """把收集到的标记真正登记出去。加载器在构造完插件之后调一次。"""
    made = []
    for kind, name, meta, fn in collect(type(plugin)):
        if kind == "page":
            made.append(plugin.add("core.pages", name,
                                   init=_builder(plugin, fn, meta),
                                   title=meta["title"], icon=meta["icon"],
                                   order=meta["order"]))
        elif kind in ("page_overlay", "page_stack"):
            made.append(plugin.add(
                "core.overlays" if kind == "page_overlay" else "core.stacks", name,
                init=_builder(plugin, fn, meta),
                title=meta["title"], order=meta["order"]))
        elif kind == "section":
            made.append(plugin.add("core.setting.sections", name,
                                   init=_builder(plugin, fn, meta, with_items=True),
                                   title=meta["title"], order=meta["order"]))
        elif kind == "setting":
            made.append(plugin.add("core.setting.items", name,
                                   init=_builder(plugin, fn, meta),
                                   title=meta["title"], section=meta["section"],
                                   order=meta["order"]))
        elif kind == "game_page":
            made.append(plugin.add("core.gameManager.pages", name,
                                   init=_builder(plugin, fn, meta),
                                   title=meta["title"], icon=meta["icon"],
                                   order=meta["order"]))
        elif kind == "tray":
            made.append(plugin.add_tray(name, title=meta["title"],
                                        callback=getattr(plugin, name),
                                        order=meta["order"]))
        elif kind == "on":
            plugin.on(meta["event"], getattr(plugin, name))
        elif kind == "ready":
            _READY.setdefault(plugin.id, []).append(getattr(plugin, name))
    # 类属性形式声明的 qss（也扫实例：写在 __init__ 里的那些以前静默不生效）
    for name, attr in _class_attrs(type(plugin)):
        made.append(plugin.add("core.qss", name, **attr.fields))
    for name, attr in vars(plugin).items():
        if getattr(attr, "fields", None) and type(attr).__name__ == "_Qss":
            made.append(plugin.add("core.qss", name, **attr.fields))
    return made


_READY = {}


def ready(plugin_id):
    """取（并清掉）某个插件的 on_ready 回调。加载器在全部加载完之后调。"""
    return _READY.pop(plugin_id, [])


def discard(plugin_id):
    """丢掉某个插件攒下的 on_ready 回调（加载失败回滚时调）。

    这批回调不在注册表里，注册表会话的 abort 滚不到它们：一个 id 加载失败、
    修好后重新加载时，上一次那批还留在表里，会被 `ready()` 连着**已经回滚掉的
    旧实例**一起取出来调一遍。
    """
    _READY.pop(plugin_id, None)


def _class_attrs(cls):
    """收集类属性里用 registrar.qss(...) 声明的东西（子类覆盖同名）。"""
    seen = set()
    out = []
    for base in cls.__mro__:
        for name, attr in vars(base).items():
            if name in seen:
                continue
            seen.add(name)
            if getattr(attr, "fields", None) and type(attr).__name__ == "_Qss":
                out.append((name, attr))
    return out


def _builder(plugin, fn, meta, with_items=False):
    """把「方法 → init 工厂」包一层：宿主调 init(Ctx)，这里转交给插件的方法。"""
    method = getattr(plugin, fn.__name__)

    def init(box):
        ctx = Ctx(parent=getattr(box, "parent", None),
                   title=meta.get("title", ""),
                   items=getattr(box, "items", ()) if with_items else (),
                   entry=getattr(box, "entry", None))
        return method(ctx)

    return init
