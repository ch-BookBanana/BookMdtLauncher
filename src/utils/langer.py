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

翻译服务（L1 次基层）。

从 main.py 搬出来的（原先它是 Main 里的一个嵌套类，攥着整个宿主）。

它**不往上依赖**：插件语言包从哪来，是构造时注入的一个函数
（lang -> {键: 文案}，宿主把 pluginLoader.plugin_langs 递进来）。
原先 load() 里直接 `from src.utils.pluginLoader import plugin_langs` —— 那是
「次基层 ← 插件层」的反依赖：插件层一动，语言服务就得跟着重建，而语言服务
重建又会牵动整个界面。

三级回退：当前语言 → 默认语言(en-US) → 原键名；
键带命名空间（内置 core.*，插件 <插件id>.*），另外认一次没有 core. 前缀的老键。
"""

import json
import os

from PySide6.QtCore import QTimer

from .bus import bus
from .path_utils import getPath


class Langer:
    def __init__(self, *, settings=None, logger=None, winreg=None,
                 overrides=None, revision=None, default_lang="en-US"):
        # 全部注入：次基层也不往上依赖，更不 import 插件层。
        # overrides 是「某个语言有哪些插件覆盖项」的来源（宿主把
        # pluginLoader.plugin_langs 递进来），缺省就没有覆盖。
        # revision 是插件语言包那侧的版本号来源（宿主递 pluginLoader.langs_revision）：
        # 光看语言名分不出「插件集合变了没有」，而插件语言包是会盖内置键的。
        self._settings = settings
        self._logger = logger
        self._winreg = winreg
        self._overrides = overrides
        self._revision = revision
        self.default_lang = default_lang
        # 已经装进 self.langs 的那份输入：语言 + 插件语言包版本（见 load）
        self._loaded = None

        self.current_lang = self.resolve_startup_language()
        self.load(self.current_lang)

    # ── 小工具：拿不到就退化，不抛 ──

    def _log(self, level, msg):
        if self._logger is None:
            return
        try:
            getattr(self._logger, level, self._logger.info)(msg)
        except Exception:
            pass

    def _system_lang(self):
        if self._winreg is None:
            return None
        try:
            return self._winreg.display_language()
        except Exception:
            return None

    def resolve_startup_language(self):
        """定下这次启动用哪个语言：设置里那个 → 系统语言 → en-US。

        定完顺手写回设置（设置对象自己会排存盘，不必在这儿调 saveSettings）。
        """
        final_lang = self._settings["language"] if self._settings is not None else None
        langs = self.get_langs()
        if final_lang in langs:
            return final_lang

        sys_lang = self._system_lang()
        if final_lang is not None:
            self._log("warning",
                      f"Language '{final_lang}' not found, "
                      f"using system display language: {sys_lang}")
        if sys_lang and sys_lang in langs:
            final_lang = sys_lang
        else:
            if sys_lang:
                self._log("warning", f"System display language '{sys_lang}' not found, "
                                     f"using: {self.default_lang}")
            else:
                self._log("warning", "System display language detection failed, "
                                     f"using: {self.default_lang}")
            final_lang = self.default_lang

        if self._settings is not None:
            self._settings["language"] = final_lang
        return final_lang

    def _signature(self, lang):
        """这次加载的输入指纹：语言 + 插件语言包版本号。"""
        rev = None
        if self._revision is not None:
            try:
                rev = self._revision()
            except Exception:
                rev = None
        return (lang, rev)

    def load(self, lang):
        """加载语言文件并自动刷新所有支持多语言的控件。

        **同一份输入不重复干活**：输入指纹是 (语言, 插件语言包版本) 两样。一次
        启动里「插件进来之后」这条路会被走到两次 —— load_all 末尾的 plugins_changed
        一次、启动流程的保险一次 —— 不比对一下就是同一份表读两遍，而 load() 末尾
        那次广播的代价是所有控件各刷一遍（广播也是排进事件循环的，早晚都跑）。
        插件集合真变了版本号会跟着变，那种时候照样重读 —— 这正是那条保险的用处。
        """
        sig = self._signature(lang)
        if sig == self._loaded and getattr(self, "langs", None):
            return
        self._loaded = sig
        # 记下当前语言：调用方常用 load(self.current_lang) 做「按现在这门语言重读」，
        # 不更新的话，切到别的语言之后再重载就会被拽回启动时那门语言。
        self.current_lang = lang

        lang_path = getPath(f"src/lang/{lang}.json")
        default_lang_path = getPath(f"src/lang/{self.default_lang}.json")

        try:
            with open(lang_path, "r", encoding="utf-8") as f:
                self.langs = json.load(f)
            # 插件语言包覆盖内置同名键（插件想改哪句文案，直接在自己语言包里
            # 写那个键）。**来源是注入的那个函数**，不是从这里 import 插件层 ——
            # 原先那行是「次基层 ← 插件层」的反依赖：插件层一动，语言服务就得
            # 跟着重建，而语言服务重建又会牵动整个界面。
            if self._overrides is not None:
                try:
                    self.langs.update(self._overrides(lang) or {})
                except Exception as e:
                    self._log("error", f"插件语言包合并失败（{lang}）：{e}")
            if self._settings is not None:
                self._settings["language"] = lang
        except Exception as e:
            self._log("error", f"Failed to load language file {lang_path}: {e}")
            self.langs = {}

        # 预加载默认语言以便快速回退，避免每次get都读取文件
        try:
            if lang != self.default_lang:
                with open(default_lang_path, "r", encoding="utf-8") as f:
                    self.default_langs = json.load(f)
            else:
                self.default_langs = self.langs
        except Exception as e:
            self._log("warning", f"Failed to load default language file {default_lang_path}: {e}")
            self.default_langs = {}

        # 广播语言变化：各控件的 langing 已自行接在总线上，
        # 延到事件循环里统一刷新，避免阻塞本次语言文件的加载
        QTimer.singleShot(0, bus.set_lang)
        self._log("info", self.get("core.init.load"))

    def get(self, key):
        """
        获取翻译文本，支持三级回退：
        1. 当前语言 (zh-CN)
        2. 默认语言 (en-US)
        3. 原键名

        键带命名空间：内置一律 core.*，插件用 <插件id>.* —— 这样插件
        语言包里的某条键能精确对上要盖的内置文案，而不是靠猜。
        另外认一次没有前缀的老键：迁移期漏改的地方会去掉 core. 再找，
        不至于把键名直接显示给用户。
        """
        candidates = (key, key[5:] if key.startswith("core.") else "core." + key)
        for k in candidates:
            if k in self.langs:
                return self.langs[k]
            if k in self.default_langs:
                return self.default_langs[k]
        return key

    def get_langs(self):
        langs = []
        lang_dir = getPath("src/lang")
        try:
            if not os.path.exists(lang_dir):
                return langs
            for file in os.listdir(lang_dir):
                if file.endswith(".json"):
                    langs.append(file.replace(".json", ""))
        except Exception as e:
            self._log("error", f"Failed to list language files: {e}")
        return langs

    def get_langs_info(self):
        """
        获取所有语言文件的名称及 init 信息。
        返回字典：键为语言文件名（不带后缀），值为列表 [init, init.en]
        """
        info = {}
        lang_dir = getPath("src/lang")
        try:
            if not os.path.exists(lang_dir):
                return info
            for file in os.listdir(lang_dir):
                if file.endswith(".json"):
                    lang_name = file.replace(".json", "")
                    lang_path = os.path.join(lang_dir, file)
                    try:
                        with open(lang_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        info[lang_name] = [
                            data.get("init", lang_name),
                            data.get("init.en", lang_name)
                        ]
                    except Exception as e:
                        self._log("error", f"Failed to read language file {lang_path}: {e}")
                        info[lang_name] = [lang_name, lang_name]
        except Exception as e:
            self._log("error", f"Failed to list language files: {e}")
        return info
