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

from PySide6.QtCore import QObject, Signal

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

    # ─────────────────────── 声明 / 订阅 ───────────────────────

    def register(self, name, sig=None):
        """声明一个信号并返回它（同名已存在则返回已有的）。

        sig 省略时按无参信号注册；带参数的事件要在**发出方**声明一次，
        否则 emit 传的参数没处落。
        """
        if sig is None:
            sig = Signal()
        if name in self._holders:
            return self._holders[name].signal
        holder = self._make_holder_cls(sig)(self)
        self._holders[name] = holder
        return holder.signal

    def on(self, name, callback):
        """订阅事件。名字未声明过时用无参信号自动补一个。"""
        if name not in self._holders:
            self.register(name)
        self._holders[name].signal.connect(callback)
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
        """触发事件。名字没声明过就静默跳过 —— 广播方不该关心有没有听众。"""
        if name in self._holders:
            self._holders[name].signal.emit(*args)

    # ─────────────────────── 退订 / 清理 ───────────────────────

    def off(self, name=None, callback=None):
        """退订。

        off(name, callback) 断开指定的那一个；
        off(name)           断开该事件的全部订阅；
        off()               断开所有事件的订阅。
        """
        if name is None:
            for h in self._holders.values():
                try:
                    h.signal.disconnect()
                except TypeError:
                    pass
            return
        if name not in self._holders:
            return
        sig = self._holders[name].signal
        try:
            sig.disconnect(callback) if callback is not None else sig.disconnect()
        except TypeError:
            pass

    # disconnect 是 off 的老名字，保留
    disconnect = off

    def cancel(self, name):
        """连信号本身一起移除（插件卸载时用它，别留下空壳名字）。"""
        if name in self._holders:
            self._holders[name].signal.disconnect()
            self._holders[name].deleteLater()
            del self._holders[name]

    def clear(self, name):
        """只清订阅者，保留信号本身。"""
        if name in self._holders:
            try:
                self._holders[name].signal.disconnect()
            except TypeError:
                pass

    def drop_namespace(self, prefix):
        """按前缀移除事件名（插件卸载：事件名约定为 '<插件id>.<名字>'）。"""
        doomed = [n for n in self._holders if n == prefix or n.startswith(prefix + ".")]
        for n in doomed:
            self.cancel(n)
        return len(doomed)


# 全局单例：与 src/utils/bus.py 的 bus、src/utils/registry.py 的 registry 同一风格
events = EventBus()
