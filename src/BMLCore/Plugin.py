# -*- coding: utf-8 -*-
"""插件基类：两级 + 显式句柄。

    Plugin      最小：元信息 + 生命周期 + 注册动作
    BMLPlugin   再有：settings / data / workspace / lang 这些助手

工具在一个显式传进来的 host 上（`host.log` / `host.lang` / `host.settings` /
`host.path` / `host.events` / `host.registry`）。self 上那几个同名助手只是转发，
不是另一份状态 —— 用什么从哪儿来，看构造参数就够了。

生命周期（加载器按这个顺序调）：

    __init__(host)  构造就是初始化与登记：拿到 host，add 条目、订事件
    on_ready()      所有插件都加载完（界面还没建）
    on_close()      卸载：停线程、关文件。加载失败回滚时也会调一次
                     （构造可能只做了一半，所以这里要容忍残缺状态）

没有别的钩子：登记写在构造里（或装饰器上），收尾写在 on_close 里。
构造里抛异常 = 这个插件没加载起来，注册表的会话会整体回滚。
"""

from ..utils.events import events
from ..utils.registry import registry

API_VERSION = "1.0"


class Ctx:
    """构建函数收到的上下文：只有这四个，没有「任意字段都能取到」那一套。"""

    __slots__ = ("parent", "title", "items", "entry")

    def __init__(self, parent=None, title="", items=(), entry=None):
        self.parent = parent        # 挂到哪（当 Qt parent 用）
        self.title = title          # 登记时写的语言键
        self.items = items          # 只有 section：这一组容纳的条目
        self.entry = entry          # 注册表条目（要读别的字段时才用）

    def __repr__(self):
        return "<Ctx parent=%s title=%r items=%d>" % (
            type(self.parent).__name__, self.title, len(self.items))


class Service:
    """别的插件发布的东西的**活句柄**：取属性时才按 key 现查一遍。

    为什么不是直接把那个对象交出去：提供方会被卸载、重载，攥在手里的旧对象
    跟着失效（它的控件可能已经拆了）。活句柄把「什么时候取」推迟到真正用它的
    那一刻，于是存进 `self.xxx` 也安全 —— 提供方重载之后，这里拿到的自然是
    新那一份。

    取不到时抛注册表那条报错（会列出该扩展点现有的条目），不会给一个半死的对象。
    """

    __slots__ = ("_key", "_point")

    def __init__(self, key):
        self._key = key
        # 发布点按 key 推出来：<id>.api —— 见 Plugin.publish
        self._point = "%s.api" % key.rpartition(".")[0]

    @property
    def target(self):
        """当前那一份（要把它本身传给别的接口时用）。"""
        return registry.entry(self._point, self._key).obj

    def __getattr__(self, item):
        if item.startswith("_"):        # 自家属性查不到就是真没有，别绕回这里
            raise AttributeError(item)
        try:
            return getattr(self.target, item)
        except KeyError as e:
            # 取不到时抛的是注册表的 RegistryError，而它在语义上就是
            # 「这个名字现在没有」—— 包成 AttributeError，`hasattr` 与
            # `getattr(svc, "x", 默认)` 这两条最自然的探测写法才有效。
            raise AttributeError(
                f"{self._key} 现在取不到：{e}") from None

    def __call__(self, *args, **kwargs):
        """转发调用：发布出来的东西是工厂/函数时，`self.use(key)(…)` 直接可用。"""
        return self.target(*args, **kwargs)

    def __bool__(self):
        """当前取得到就是真 —— 用来判断「提供方还在不在」。"""
        try:
            self.target
            return True
        except Exception:
            return False

    def __repr__(self):
        try:
            return "<Service %s -> %r>" % (self._key, self.target)
        except Exception:
            return "<Service %s（当前取不到）>" % self._key


class Plugin:
    """最小插件：只登记条目的话，继承它就够。"""

    id = ""                 # 标识符（字母开头），建议带作者名：you_hello
    name = ""               # 显示名
    version = "0.0.0"
    api = "1.x"             # 兼容的宿主 API 范围

    def __init__(self, host=None):
        self.host = host

    # ── 生命周期 ──

    def on_ready(self):
        """所有插件都加载完之后（界面还没建）。"""

    def on_close(self):
        """卸载阶段：停线程、关文件、删临时目录。"""

    # ── 注册动作 ──

    def add(self, point, name, **fields):
        """往扩展点登记一项；key 自动加 `<id>.` 前缀，卸载时按前缀整片摘掉。"""
        return registry.add(point, f"{self.id}.{name}", **fields)

    def override(self, point, key, **fields):
        """顶掉**别家**已有的一条（内置条目、别的插件的条目都行）。

        自己的东西用 add：key 带 `<id>.` 前缀，卸载时整片摘掉。要换掉宿主那条
        内置的（比如关闭询问 core.closeAsk），key 挂不到自己名下，于是用这个 ——
        `by=self.id` 会把这条记在自己名下，并且把被顶掉的那条压进覆盖记录：

            self.override("core.overlays", "core.closeAsk",
                          init=lambda b: MyCloseAsk(b.parent),
                          order=30, title="example_x.close")

        卸载（或加载失败回滚）时，注册表自动把被顶掉的那条放回原位，界面回到
        上一个提供者的控件 —— 不需要自己记得 set 回来。
        """
        return registry.set(point, key, by=self.id, **fields)

    # ── 与别的插件互通 ──

    def publish(self, name, obj, *, doc=""):
        """把自己的一样东西发布出去（类、工厂、服务对象都行），别的插件按 key 取。

        发布出来的 key 是 `<id>.<name>`，落脚在自动声明的扩展点 `<id>.api` 上：

            # 提供方
            self.publish("widgets", Widgets())      # → example_more.widgets

            # 使用方（清单里先写 dependencies）
            api = self.use("example_more.widgets")
            api.Bool("标签", "red")

        为什么不让使用方 import 提供方的文件：那样拿到的是**模块级**的一份代码，
        对方重载之后这边永远冻在旧版本上，而且两个插件都叫 utils.py 就会撞。
        走注册表则跟着生命周期走：对方卸载，这条就不在了（取的时候明确报错）。
        """
        point = "%s.api" % self.id
        if not registry.declared(point):
            registry.declare(point, registrant=self.id,
                             fields=("init",), required=("init",), built=("obj",),
                             doc=doc or "%s 发布的东西" % self.id)
        return registry.provide(point, "%s.%s" % (self.id, name), obj)

    def use(self, key):
        """取别的插件发布的东西，返回活句柄（每次用的时候才现查）。

        key 是 `<提供方 id>.<名字>`。取不到时用它取属性会抛 AttributeError
        （`hasattr` / `getattr(..., 默认)` 因此能正常工作），消息里带着现有的条目。
        """
        if not isinstance(key, str) or "." not in key:
            raise ValueError(
                f"发布 key 要写成 <提供方 id>.<名字>（如 example_more.widgets），收到 {key!r}")
        return Service(key)

    def add_setting(self, name, cls, *, title, section="core.setting.plugins",
                    order=900, **fields):
        """往设置页加一项（控件类的构造签名是 (parent, title)）。"""
        from ..utils.registry import simple
        return self.add("core.setting.items", name, init=simple(cls),
                        section=section, order=order, title=title, **fields)

    def add_qss(self, css, *, theme=None, order=100):
        """往全局样式表末尾追加 css；theme 为 None/True/False = 两套/浅色/深色。"""
        return self.add("core.qss", "qss", qss=css, theme=theme, order=order)

    def add_tray(self, name, *, title, callback, order=100):
        """往托盘右键菜单加一项；title 是语言键，切语言时托盘自己重刷。"""
        from PySide6.QtGui import QAction

        def _init(b):
            act = QAction(b.title, b.parent)
            act.triggered.connect(lambda *_: callback())
            return act

        return self.add("core.tray.menu", name, init=_init, title=title, order=order)

    # ── 事件 ──

    def on(self, event, callback):
        """订阅事件（宿主的事件、别的插件的事件都能订）。

        订阅记在自己名下（owner = 插件 id）：卸载时连**订别人的**那些事件一起摘，
        否则卸载之后回调还在被叫（那会儿控件已经销毁），而且每重载一次多挂一份。
        """
        return events.on(event, callback, owner=self.id)

    def emit(self, event, *args):
        """广播自己的事件，名字自动加 `<id>.` 前缀。"""
        events.emit(f"{self.id}.{event}", *args)

    # ── 只读助手（转发 host）──

    @property
    def logger(self):
        return self.host.logger if self.host is not None else events.logger

    @property
    def lang(self):
        return self.host.lang if self.host is not None else events.lang

    def log(self, msg, level="info"):
        """带 `[id]` 前缀的日志；level 可为 debug / info / warning / error。"""
        target = self.logger
        getattr(target, level, target.info)(f"[{self.id}] {msg}")

    def path(self, rel=""):
        """取自己目录里的文件（绝对路径）。加载期外仍然可用。"""
        if self.host is None:
            raise RuntimeError("没有 host：这个插件不是被加载器加载起来的")
        return self.host.path(rel)


class BMLPlugin(Plugin):
    """再带上设置、私有数据与私有目录 —— 大多数插件继承它。"""

    settings_defaults = {}

    _settings_view = None
    _data = None

    @property
    def settings(self):
        """自己那一格设置（默认值来自 settings_defaults）。"""
        if self._settings_view is None:
            from ..utils.pluginSettings import PluginSettings
            # 拷贝一份默认值：settings_defaults 是类属性，视图不该跟着它变。
            # （但**别去改那个类属性本身** —— 改了是所有实例一起变。）
            self._settings_view = PluginSettings(self.id, dict(self.settings_defaults))
        return self._settings_view

    @property
    def data(self):
        """私有数据：一个 dict，改了调 save_data() 落盘。

        文件坏掉（半截 JSON、被手改成数组）时**不当成空数据继续跑**：原件留一份
        `.bad` 备份、记一条 error，然后给一个空 dict —— 否则插件照常干活，下次
        save_data() 就把用户原来的数据覆盖掉了。
        """
        if self._data is None:
            self._data = self._load_data()
        return self._data

    def _load_data(self):
        import json
        import os
        if self.host is None:
            return {}
        path = os.path.join(self.host.data_dir, "data.json")
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"顶层不是对象（是 {type(data).__name__}）")
            return data
        except Exception as e:
            self._backup_data(path, e)
            return {}

    def _backup_data(self, path, why):
        """把读不了的 data.json 留一份 .bad，别让下一次存盘把它覆盖掉。"""
        import os
        try:
            os.replace(path, path + ".bad")
            self.log("私有数据读不了（%s），原件已备份为 data.json.bad" % why,
                     level="error")
        except Exception as e:
            self.log("私有数据读不了（%s），备份也失败了：%s" % (why, e), level="error")

    def save_data(self):
        """把 data 写回私有目录（临时文件 + 原子替换）。

        写的是 `self.data` 那份（没读过就先读进来），不是「内存里那份、没有就
        当空」—— 否则在 on_close 里无条件存一次，就会把上次的数据抹成 {}。
        原子替换是为了写一半被杀（或断电）时不留下半截文件：那份文件下次读
        会进 `_load_data` 的坏文件分支。
        """
        import json
        import os
        if self.host is None:
            return
        data = self.data
        os.makedirs(self.host.data_dir, exist_ok=True)
        path = os.path.join(self.host.data_dir, "data.json")
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception as e:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            self.log("私有数据存不下去：%s" % e, level="error")

    _config_watchers = None

    def get_config(self, key, default=None):
        """读设置：没存过时看 settings_defaults，再退到 default。"""
        try:
            return self.settings[key]
        except KeyError:
            return default

    def set_config(self, key, value):
        """写设置并通知 watch_config 的回调（直接写 self.settings 不会通知）。

        派发时对回调表取**副本**：回调里再 `watch_config` 同一个键时，新加的那条
        不该在这一次派发里就被叫到（那会自我放大，同键上就是死循环）。
        """
        self.settings[key] = value
        for cb in list((self._config_watchers or {}).get(key, ())):
            try:
                cb(value)
            except Exception as e:
                self.log("配置回调抛异常（%s）：%s" % (key, e), level="error")

    def watch_config(self, key, callback):
        """盯一个设置键：走 set_config 改它时回调。"""
        if self._config_watchers is None:
            self._config_watchers = {}
        self._config_watchers.setdefault(key, []).append(callback)
        return callback

    @property
    def workspace(self):
        """自己的目录（`BML/pluginData/<id>/`，不存在就建）。"""
        if self.host is None:
            raise RuntimeError("没有 host：这个插件不是被加载器加载起来的")
        return self.host.workspace()
