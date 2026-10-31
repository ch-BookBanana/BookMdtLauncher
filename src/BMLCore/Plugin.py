# -*- coding: utf-8 -*-
"""插件基类：两级 + 显式句柄。

    Plugin      最小：元信息 + 生命周期 + 注册动作
    BMLPlugin   再有：settings / workspace / lang 这些助手

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

API_VERSION = "2.0.0"


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
    name = ""               # 显示名（清单没填时兜底；版本/API 范围只认清单）

    def __init__(self, host=None):
        self.host = host
        # 宿主替你收拾的东西：计时器 / 后台线程 / 下载器（cleanup() 统一收尾）
        self._timers = []
        self._threads = []
        self._downloads = []

    # ── 生命周期 ──

    def on_ready(self):
        """所有插件都加载完之后（界面还没建）。"""

    def on_close(self):
        """卸载阶段：停线程、关文件、删临时目录。"""

    # ── 注册动作 ──

    settings_defaults = {}
    _settings_view = None

    @property
    def settings(self):
        """自己那一格设置（settings["<id>"]；默认值来自 settings_defaults）。

        只有声明过的键能写（settings_defaults，或 settings.declare）；
        读别人的桶走显式路径 `self.settings.other("core")`。
        """
        if self._settings_view is None:
            from ..utils.pluginSettings import PluginSettings
            self._settings_view = PluginSettings(self.id, dict(self.settings_defaults))
        return self._settings_view

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

    def register(self, path):
        """注册作用域：self.register("settings") / self.register("core/pages") 那套。

        九个动词（new/set/update/remove/get/list/owned/contract/watch）都从
        这个作用域走；没绑实例时 `registrar("...")` 是同一件事。
        """
        from .registrar import Scope
        return Scope(path, plugin=self)

    def add(self, point, name, **fields):
        """往扩展点登记一项；key 自动加 `<id>/` 前缀，卸载时按前缀整片摘掉。"""
        return registry.add(point, f"{self.id}.{name}", **fields)

    def override(self, point, key, **fields):
        """顶掉**别家**已有的一条（内置条目、别的插件的条目都行）。

        自己的东西用 add：key 带 `<id>.` 前缀，卸载时整片摘掉。要换掉宿主那条
        内置的（比如关闭询问 core.closeAsk），key 挂不到自己名下，于是用这个 ——
        `by=self.id` 会把这条记在自己名下，并且把被顶掉的那条压进覆盖记录：

            self.override("core.overlays", "core.closeAsk",
                          init=lambda b: MyCloseAsk(b.parent), title="example_x.close")

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

    def add_setting(self, name, cls=None, *, title, section="plugins", build=None, **fields):
        """往设置页加一项：值存插件自己的设置桶，界面自动双向同步。

            self.add_setting("greet", Widgets.Bool, title="问候开关")

        控件类的构造签名是 (parent, title)，必须实现设置项接口（value /
        set_value / refresh，见 options/base.py）：本方法用 Widgets.control 把它
        和设置键 `name` 接起来 —— 拨动写回设置，设置被别处改了控件自己刷新。

        要自己画控件、自己接线就给 build：
            self.add_setting("greet", title="…", build=lambda ctx: MyWidget(ctx.parent))
        这时 build 返回什么就摆什么，线由你自己接。

        条目落在 core/setting 的分组子点上（默认 "plugins" 组；插件想自己开一组
        就往 core/setting 下 add 一个 type="core/setting" 的子点，再把 section 写它）。
        """
        from .btypes import register as register_point
        from ..utils.options.base import bind

        plugin = self

        class _ConfigSource:
            """插件设置桶当设置源：get / set / watch 三件套。"""

            def get(self):
                return plugin.get_config(name)

            def set(self, value):
                plugin.set_config(name, value)

            def watch(self, callback):
                plugin.watch_config(name, lambda *_: callback())

        if build is None:
            def build(ctx):
                return bind(cls(ctx.parent, ctx.title), _ConfigSource())

        group = register_point("core/setting")
        # 分组可以写全名（core.setting.java）也可以只写末段（java）
        for key in (section, f"core.setting.{section}"):
            if group.has(key):
                point = group.get(key)
                break
        else:
            raise KeyError(f"设置分组 {section!r} 不存在"
                           f"（先 register(\"core/setting\").add({section!r}, "
                           f"type=\"core/setting\")）")
        return point.add(f"{self.id}/{name}", title=title,
                         build=build, **fields)

    def add_qss(self, css, *, theme=None):
        """往全局样式表末尾追加 css；theme 为 None/True/False = 两套/浅色/深色。"""
        return self.add("core.qss", "qss", qss=css, theme=theme)

    def add_tray(self, name, *, title, callback):
        """往托盘右键菜单加一项；title 是语言键，切语言时托盘自己重刷。"""
        from PySide6.QtGui import QAction

        def _init(b):
            act = QAction(b.title, b.parent)
            act.triggered.connect(lambda *_: callback())
            return act

        return self.add("core.tray.menu", name, init=_init, title=title)

    # ── 能力句柄：宿主替你收拾 ──

    def every(self, interval, callback, *, immediate=False):
        """周期回调（毫秒）。卸载时自动停，不用自己记着销毁。

            self.every(1000, self._tick)        # 每秒 tick 一次
        """
        from ..utils.QThTimer import QThTimer
        timer = QThTimer(interval, owner=self.id)
        timer.timeout.connect(callback)
        if immediate:
            callback()
        timer.start()
        self._timers.append(timer)
        return timer

    def task(self, interval, job, *, events=None, result_callback=None):
        """子线程任务（QThTimer.task）：job(event) 在共享线程里跑，卸载时 destroy。

        job 里可以轮询 `timer.cancel_event.is_set()` 及时收手；返回值就是那个
        QThTimer（setInterval / stop / cancel 都在它上面）。
        """
        from ..utils.QThTimer import QThTimer
        timer = QThTimer.task(interval, job, events=events,
                              result_callback=result_callback, owner=self.id)
        self._timers.append(timer)
        return timer

    def download(self, url=None, dest_path=None, **kw):
        """自己发起的下载（宿主同一套 QDownloader）：

        - 默认参数与宿主下载一致，出现在宿主的下载列表里（进度/取消都通）；
        - 卸载时宿主替你 cancel 并最多等 5 秒（线程退出要时间）。
        """
        from ..utils.QDownloader import QDownloader
        dl = QDownloader(url=url, dest_path=dest_path, owner=self.id, **kw)
        self._downloads.append(dl)
        dl.start()
        return dl

    def thread(self, job, *, name=""):
        """一次性后台线程：卸载时 join（最多 5 秒）。

        线程里跑长任务时自己盯 `self._closed`；更推荐 QThTimer 那套
        （cancel_event 有明确的收手信号）。
        """
        import threading
        t = threading.Thread(target=job, name=name or f"{self.id}.job", daemon=True)
        t.start()
        self._threads.append(t)
        return t

    def cleanup(self):
        """宿主在 on_close 之后调：计时器停、下载取消并等 5 秒、线程 join 5 秒。

        插件作者正常写 on_close 就够了（关文件、存数据）；这里收的是「宿主替你
        发起的资源」，双保险，不必在 on_close 里重复一遍。
        """
        timers, self._timers = self._timers, []
        for timer in timers:
            try:
                timer.cancel()
            except Exception:
                pass
        downloads, self._downloads = self._downloads, []
        for dl in downloads:
            try:
                dl.cancel()
                dl.wait_thread(5)
            except Exception:
                pass
        threads, self._threads = self._threads, []
        for t in threads:
            try:
                t.join(5)
            except Exception:
                pass

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
    """再带上私有目录 —— 大多数插件继承它。

    settings / settings_defaults / get_config / set_config / watch_config 都在
    Plugin 上就有（DSL 的 settings 命名空间要用）；这一层只多一个 workspace。
    """

    @property
    def workspace(self):
        """自己的目录（`BML/pluginData/<id>/`，不存在就建）。"""
        if self.host is None:
            raise RuntimeError("没有 host：这个插件不是被加载器加载起来的")
        return self.host.workspace()

