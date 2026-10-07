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

插件 API 门面 —— 插件作者只需要认识这一个名字。

一个插件长这样：

    from BMLCore import Plugin

    class Hello(Plugin):
        id = "you_hello"              # 标识符，建议带作者名；同时是注册表命名空间
        name = "Hello"

        def __init__(self, host):
            super().__init__(host)
            self.add("core.setting.items", "greet",
                     init=..., section="core.setting.plugins", title="you_hello.greet")

为什么中间要有这一层
--------------------
插件一旦 import 到内部模块（src.utils.events、src.utils.registry、main.py…），
内部一重构插件就全断 —— 而内部一定还会接着重构（看看这个分支里搬过多少东西）。
BMLCore 是**承诺稳定**的那一层：里面怎么挪都行，这层的名字与签名尽量不动；
真要动就抬 API_VERSION，加载器按插件声明的 api 范围决定收不收。

只放「插件真的会用到」的东西
----------------------------
门面越薄越守得住：塞进来的每个名字都是一份长期承诺。所以宁可少放、以后再补，
也不要先图方便把内部结构一股脑转出来。现在有这几样：

    API_VERSION  宿主 API 版本（插件按它声明自己兼容的范围）
    Plugin       插件基类（元信息 + 生命周期 + 便捷动作 + 自己的设置）
    Widgets      现成控件（Bool / Combo / Title…，和内置界面同一套）
    events       事件总线（on / emit，插件间的通知与命令都走它）
    registry     扩展点登记（一般用 Plugin.add 就够了，需要直连时再用）
    simple       把「签名是 (parent, root, title) 的控件类」变成 init 工厂
    getPath      取自己的资源（${plugin}/…），换 id、换安装位置都不用改代码
    Signal       PySide6 的 Signal，转一道手：插件自定义信号不必自己 import Qt
                 （将来换掉 Qt 绑定，这一层的名字也还在）

另外三个「往宿主界面里伸」的动作挂在插件实例上，不占门面的名字：

    self.add_setting(...)   设置页加一项
    self.add_qss(...)       往全局样式表末尾追加 css（可只对某套主题生效）
    self.add_tray(...)      往系统托盘右键菜单加一项

插件设置不用单独记一个名字：它挂在插件实例上 —— self.settings["key"]，
存进宿主 settings.json 的 "pluginSettings" 里自己那一格（见 utils/pluginSettings.py）。

边界提醒（写插件前务必分清）
----------------------------
通知 / 命令 → 走 events ✓
查询（要返回值）→ 用具名工具，别拿事件当函数调用 —— 信号是单向广播，
硬做请求-响应会让调用方挂在一个永远不返回的 emit 上。
"""

from PySide6.QtCore import Signal

from . import Widgets, registrar
from .Plugin import API_VERSION, BMLPlugin, Ctx, Plugin, Service
from ..utils.events import events
from ..utils.path_utils import getPath
from ..utils.registry import registry, simple

__all__ = ["API_VERSION", "Plugin", "BMLPlugin", "Ctx", "Service", "registrar",
           "Widgets", "events", "registry", "simple", "getPath", "Signal"]
