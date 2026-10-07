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

事件总线：按名字注册的信号，宿主与插件都靠它通信。

为什么提成模块级单例
--------------------
它原先挂在 Main 上（root.signals）。组件想发一个事件，得先拿到 root —— 而
root 上挂着十七八个隐式属性，把它递给插件等于把现有的债复制 N 份。
提成模块级单例后，宿主与插件都只写一行：

    from ..events import events
    events.on("overlayRequested", self._show)      # 订阅
    events.emit("pageRequested", "core.download")  # 通知

适用边界（写插件前务必分清）
----------------------------
  * 通知 / 命令（单向）→ 走事件 ✓   切页、弹浮层、提示、状态广播
  * 查询（要返回值）  → 不走事件 ✗   取翻译、读设置，用具名服务直接调

Qt 信号是单向广播：硬拿它做请求-响应，调用方会挂在一个永远不返回的 emit 上。
emit 一个没人订阅的名字是**静默跳过**（广播方不该关心有没有听众），
所以信号名写错不会报错，只会表现成「点了没反应」—— 调试时优先怀疑这里。
"""

from PySide6.QtCore import QCoreApplication, QObject, Signal

from .registry import registry

__all__ = ["EventBus", "events"]


class EventBus(QObject):
    """动态信号管理器 —— 每个名字背后都是一个真正的 PySide6 Signal。

        events.register("dataReady", Signal(str, int))   # 声明签名（可省）
        events.on("dataReady", lambda s, i: print(s, i))
        events.emit("dataReady", "hello", 42)
        events.off("dataReady", callback)
        events.cancel("dataReady")                       # 连信号一起移除
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # name → holder 实例（holder 是个只带一个 signal 属性的 QObject 子类）
        self._holders = {}
        # name → [(owner, callback)]：订阅**自己记一份**。
        # 为什么不用 Qt 的 connections()：摘订阅时要知道「这条是谁订的」，
        # 而 Qt 只认 callback 本身 —— 插件订了宿主的事件名（plugins_changed 之类）
        # 时，按名字前缀根本摘不掉它，卸载之后它的回调还在被叫。
        self._subs = {}
        # 「没声明就自动补的无参信号」的名字：真签名到来时要换成真签名
        self._implicit = set()
        self._root = None       # 宿主，由 bind() 交进来一次

    # ─────────────────────── 宿主工具 ───────────────────────
    # 日志、设置、翻译、宿主体这些东西本来就是全局引用的。与其让每个组件攥着
    # Main 那一大坨隐式属性，不如统一从这里取：events.logger / events.settings /
    # events.lang / events.shell。
    #
    # 一律用 property 转发、而不是 bind 时取快照 —— 宿主换掉 self.settings 时
    # 这里要跟着走，挂快照会留下一个过期的旧对象。

    def bind(self, root):
        """宿主启动时把自己交进来（Main.__init__ 调一次）。

        组件在 bind 之前不该被构造 —— 那时 events.logger 还是空的。
        """
        self._root = root
        return self

    @property
    def logger(self):
        return self._root.logger

    @property
    def settings(self):
        return self._root.settings

    @property
    def lang(self):
        """翻译服务（就是宿主的 Langer）。"""
        return self._root.langer

    @property
    def shell(self):
        """宿主体（三栏页容器）：从注册表取，不另存一份。"""
        return registry.entry("core.shell", "core.shell.workspace").obj

    def __getattr__(self, item):
        """兜底：上面没显式列出的名字，转发到宿主。

        mdtManager / launcher / githubAPI / winreg / tray 这些工具本来就是全局
        引用的，与其让每个组件攥着 Main，不如从这里统一取：events.mdtManager。
        显式列出的那几个（logger / settings / lang / shell）优先走它们，因为
        它们要的是**转发**而不是快照。

        注意：这是过渡期的兜底，不是鼓励用。组件的动作该发事件（events.emit），
        查询该用具名工具；通过这里去摸宿主的内部结构（比如 events.window.main）
        等于把耦合藏得更深了。
        """
        root = object.__getattribute__(self, "_root")
        if root is None:
            raise AttributeError(
                f"events 还没 bind 宿主，取不到 {item!r}"
                f"（Main.__init__ 里应当调 events.bind(self)）"
            )
        try:
            return getattr(root, item)
        except AttributeError:
            raise AttributeError(f"宿主上没有 {item!r}") from None

    @staticmethod
    def _make_holder_cls(sig):
        """按 Signal 签名动态造一个 QObject 子类，把 signal 挂上去。"""
        return type('_SigHolder', (QObject,), {'signal': sig})

    def _new_holder(self, sig):
        """造一个信号宿主对象，并把它安置在宿主线程上。

        为什么要 moveToThread：订阅请求可能来自插件的工作线程（下载器里
        `self.on("...")` 是很自然的写法）。子对象不能跨线程挂在 events 名下
        （Qt 会报 Cannot create children for a parent that is in a different
        thread，并把亲和性留在那个线程），那样这个事件名就**废掉了** ——
        主线程 emit 的信号全投给一个已经退出、没有事件循环的线程，谁都收不到，
        连主线程后加的订阅者也一起收不到。
        """
        holder = self._make_holder_cls(sig)()
        try:
            app = QCoreApplication.instance()
            if app is not None and holder.thread() is not app.thread():
                holder.moveToThread(app.thread())
        except Exception:
            pass
        return holder

    # ─────────────────────── 声明 / 订阅 ───────────────────────

    def register(self, name, sig=None):
        """声明一个信号并返回它。

        sig 省略时按无参信号注册；带参的事件要在**发出方**声明一次，
        否则 emit 传的参数没处落。

        同名已存在时分两种：
          * 之前是「没声明就自动补的无参信号」（有人先 on() 订了它）——
            **换成这次声明的真签名**，并把已有订阅接到新信号上。不换的话，
            提供方带参 emit 会抛 TypeError，而且报错位置离真正的原因
            （谁先订的）隔着好几层；
          * 已经显式声明过 —— 返回原来那个（同一个名字不该有两份信号）。
        """
        if sig is None:
            sig = Signal()
        holder = self._holders.get(name)
        if holder is not None:
            if name in self._implicit:
                old = holder
                holder = self._new_holder(sig)
                self._holders[name] = holder
                self._implicit.discard(name)
                for _owner, cb in self._subs.get(name, []):
                    holder.signal.connect(cb)
                try:
                    old.deleteLater()
                except Exception:
                    pass
            return holder.signal
        holder = self._new_holder(sig)
        self._holders[name] = holder
        self._implicit.add(name)
        return holder.signal

    def on(self, name, callback, owner=None):
        """订阅事件。名字未声明过时用无参信号自动补一个（见 register 的说明）。

        owner 是「这条订阅算谁的」（插件填自己的 id）：卸载时按 owner 精确摘掉
        它的全部订阅，**包括它订的宿主事件** —— 那些名字不在它的命名空间里，
        按名字前缀是摘不到的。
        """
        if name not in self._holders:
            self.register(name)
        self._holders[name].signal.connect(callback)
        self._subs.setdefault(name, []).append((owner, callback))
        return callback      # 便于 `cb = events.on(...)` 之后再 off

    # connect 是 on 的老名字，内部调用点历史较长，保留
    connect = on

    def declared(self, name):
        """该名字是否已被声明（有没有人为它 register 过）。"""
        return name in self._holders

    def names(self):
        """当前已声明的全部事件名（排查用：看看到底有哪些人在广播）。"""
        return sorted(self._holders)

    # ─────────────────────── 广播 ───────────────────────

    def emit(self, name, *args):
        """触发事件。名字没声明过就静默跳过 —— 广播方不该关心有没有听众。

        参数个数与声明的签名不符时**不让异常打进广播方**（那可能是宿主的一次
        点击、一个工作线程的收尾），只记一条 error 日志：广播方崩掉的现场
        离原因太远，而日志里直接写着是哪个事件名、几个参数。
        """
        holder = self._holders.get(name)
        if holder is None:
            return
        try:
            holder.signal.emit(*args)
        except TypeError as e:
            self._log("error", f"事件 {name!r} 的参数与声明不符（传了 {len(args)} 个）：{e}")

    # ─────────────────────── 退订 / 清理 ───────────────────────

    @staticmethod
    def _has_subs(holder):
        """这个信号当前有没有订阅者（问不出来时返回 None）。"""
        try:
            mo = holder.metaObject()
            for i in range(mo.methodCount()):
                m = mo.method(i)
                if m.name() == b"signal":
                    return bool(holder.isSignalConnected(m))
        except Exception:
            pass
        return None

    def _disconnect(self, holder):
        """断掉一个信号上的全部订阅。

        先问一句「有没有人订过」：PySide6 对**没有任何连接**的信号调 disconnect()
        会往 stderr 打一条 Failed to disconnect (None) 的 RuntimeWarning，而空信号
        在卸载/回滚路径上是常态 —— 插件可能一次都没订上就失败了。问不出来
        （None）时照旧试着断：宁可多一条警告，也不能漏断。
        """
        if self._has_subs(holder) is False:
            return
        try:
            holder.signal.disconnect()
        except (TypeError, RuntimeError):
            pass

    def off(self, name=None, callback=None, owner=None):
        """退订。

        off(name, callback) 断开指定的那一个；
        off(name)           断开该事件的全部订阅；
        off(owner=…)        断开某个订阅者（插件 id）在这个名字上的订阅；
        off()               断开所有事件的订阅。
        """
        if name is None:
            for n, h in self._holders.items():
                self._disconnect(h)
                self._subs[n] = []
            return
        if name not in self._holders:
            self._forget(name, callback, owner)
            return
        if callback is None and owner is None:
            self._disconnect(self._holders[name])
            self._forget(name)
            return
        doomed = self._forget(name, callback, owner)
        try:
            for cb in doomed:
                self._holders[name].signal.disconnect(cb)
        except (TypeError, RuntimeError):
            pass

    def _forget(self, name, callback=None, owner=None):
        """从记账里摘掉匹配的订阅，返回被摘掉的回调。"""
        kept, doomed = [], []
        for item in self._subs.get(name, []):
            hit = ((callback is not None and item[1] == callback)
                   or (callback is None and owner is not None and item[0] == owner))
            (doomed if hit else kept).append(item)
        if name in self._subs:
            self._subs[name] = kept
        return [cb for _o, cb in doomed]

    def off_owner(self, owner):
        """摘掉某个订阅者（插件 id）的全部订阅，不论事件名在谁的命名空间下。

        插件卸载/回滚时用它：插件可以订宿主的事件（`plugins_changed` 之类），
        那些名字不归它，按名字前缀摘不到 —— 漏掉的话，卸载之后它的回调还在被
        叫（那时它的控件已经销毁），而且每重载一次多挂一份。
        """
        n = 0
        for name in list(self._subs):
            doomed = self._forget(name, owner=owner)
            if not doomed:
                continue
            holder = self._holders.get(name)
            if holder is not None:
                for cb in doomed:
                    try:
                        holder.signal.disconnect(cb)
                    except (TypeError, RuntimeError):
                        pass
            n += len(doomed)
        return n

    # disconnect 是 off 的老名字，保留
    disconnect = off

    def cancel(self, name):
        """连信号本身一起移除（插件卸载时用它，别留下空壳名字）。"""
        if name in self._holders:
            self._disconnect(self._holders[name])
            self._holders[name].deleteLater()
            del self._holders[name]
        self._subs.pop(name, None)
        self._implicit.discard(name)

    def clear(self, name):
        """只清订阅者，保留信号本身。"""
        if name in self._holders:
            self._disconnect(self._holders[name])
        self._subs[name] = []

    def drop_namespace(self, prefix):
        """按前缀移除**名字**（插件卸载：事件名约定为 '<插件id>.<名字>'）。

        只动名字本身；插件订的**别人的**事件名不在这里 —— 那些由
        `off_owner(插件id)` 摘。

        别人还在订的名字**保留**：B 订了 A 的 `A.event` 时，A 卸载不该顺手把 B
        的订阅也带走（那样 A 重装回来 B 就静默聋了，什么都不报）。名字留着，
        A 重装后 `register` 拿回同一个信号，B 的订阅照旧有效。
        """
        kept = []
        doomed = [n for n in self._holders if n == prefix or n.startswith(prefix + ".")]
        for n in doomed:
            if any(owner != prefix for owner, _cb in self._subs.get(n, [])):
                kept.append(n)
                continue
            self.cancel(n)
        return len(doomed) - len(kept)

    def _log(self, level, msg):
        """记一条日志；宿主还没 bind 时安静跳过（事件总线不该因为没宿主就炸）。"""
        try:
            log = self.logger
        except Exception:
            return
        try:
            getattr(log, level, log.info)(msg)
        except Exception:
            pass


# 全局单例：与 src/utils/bus.py 的 bus、src/utils/registry.py 的 registry 同一风格
events = EventBus()
