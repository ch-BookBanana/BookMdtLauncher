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
"""

import os

from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QButtonGroup, QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QVBoxLayout)

from ..events import events
from ..javaManager import javaManager

from ..options.navBtn import NavBtn
from ..options.items import Bool, Combo
from ..options.scrolls import Scroll
from ..options.sections import Section

from ..path_utils import getPath
from ..utils import change_color, t
from ..resources import (ACT_UNITS, BTN_SETTING, FILE_FOLDER, TBT_CLOSE)
from ..registry import page, Box, registry, simple

from ._init import *

# 条目 key → 那一项的界面参数（原先写在登记里，现在归本文件自己拿）
_FIELDS = {
    "core.setting.preferences": {'spacing': 30},
    "core.setting.general": {'spacing': 30},
    "core.setting.java": {'attr': 'sec_java', 'spacing': 30},
    "core.setting.plugins": {'spacing': 30},
    "core.setting.theme": {'attr': '_t1_theme'},
    "core.setting.lang": {'attr': '_t1_lang'},
    "core.setting.close": {'attr': '_t2_close'},
    "core.setting.java.select": {'attr': '_t3_select'},
}



@page("core.setting")


class Setting(Page):
    name = "core.wid.pages.setting"
    icon = BTN_SETTING
    order = 40

    def __init__(self, btn=None):
        super().__init__(btn)

    class Left(Leftw):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.resize_(120)
            self.init_wid()
            bus.bind(self)


        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.scroll = Scroll(self)
            self.layout.addWidget(self.scroll)

            self.bthGroup = QButtonGroup(self)

        def add_btn(self, text=None, icon=None):
            btn = NavBtn(text, icon, self)
            self.scroll.add(btn)
            self.bthGroup.addButton(btn)
            return btn


    class Main(Mainw):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.init_wid()
            self.btns_[0].click()

        def init_wid(self):
            self.layout = QHBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignLeft)

            self.line = QWidget()
            self.line.setProperty("wid", "line")
            self.line.setAttribute(Qt.WA_StyledBackground,True)
            self.line.setFixedWidth(1)
            self.layout.addWidget(self.line,0)

            self.pages = QStackedWidget()
            self.layout.addWidget(self.pages,1)

            self.pages_ = []
            self.btns_ = []

            # 设置子页从注册表取：本模块的 register() 登记一次（由 builtin.py 调）。
            for e in registry.entries("core.setting.pages"):
                self.add_page(e)

        def add_page(self, entry):
            """按条目建一个子页：备好按钮 → 交给条目的 init 去造。"""
            btn = self.parent.left.add_btn(entry.title, entry.icon)
            page_ = entry.init(Box(parent=self, entry=entry, btn=btn))
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.pages.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.pages.setCurrentWidget(page_))
            return page_

        class Page(QWidget):
            def __init__(self,parent=None,text=None,icon=None):
                super().__init__()
                self.parent = parent
                self.text=text
                self.icon=icon

                self._init_wid()
                bus.bind(self)

            def _init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 10, 0, 10)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignHCenter)

                self.scroll = Scroll(self, margins=(30, 0, 30, 0))
                self.scroll.setStyleSheet("max-width: 600px;")
                self.layout.addWidget(self.scroll)

                self._title = QLabel()
                self._title.setProperty("wid", "title")
                self._title.setFixedHeight(38)
                self._title.setStyleSheet("font-size: 28px;")
                self._title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.scroll.add(self._title)
                self.langing()

            def langing(self):
                self._title.setText(events.lang.get(self.text))
            

            def add(self, wid, spacing=0):
                return self.scroll.add(wid, spacing)

        class Launcher(Page):
            def __init__(self, parent=None, text=None,icon=None):
                super().__init__(parent,text,icon)
                self._secs = {}          # 容器 key → (控件, 签名)，对账用
                # javaManager 是全局单例：这条线只接一次，回调读的永远是当前那份
                # 控件（重建之后照样对）。接在 init_wid 里的话，每次重建会多接一条。
                javaManager.changed.connect(lambda javas: self._t3_select_fill(javas))
                self.init_wid()

            # ── 分组：从注册表建，也能按注册表对账 ──

            def _plan(self):
                """当前该摆哪几组、每组哪几项。

                分组容器从注册表取，每个容器再取自己那几项（条目用 section 指着
                容器 key）：加一组 = 登记一条容器 + 条目写它的 key，本页一行都不用改。
                空容器不摆 —— 插件的组在没装插件时就是空的，那块标题也就不出现。
                """
                items_all = registry.entries("core.setting.items")
                out = []
                for sec in registry.entries("core.setting.sections"):
                    items = [e for e in items_all if e.get("section") == sec.key]
                    if items:
                        out.append((sec, items))
                return out

            @staticmethod
            def _sig(sec, items):
                """一组的签名：容器的 init 工厂 + 每项的 key 与 init 工厂。

                为什么要带上 init：插件重载之后键还是那些键，但工厂是新的一份
                （闭包连着新实例）。签名就是用来认出「同一批键、换了实例」的。
                """
                return (sec.init, tuple((e.key, e.init) for e in items))

            def init_wid(self):
                for sec, items in self._plan():
                    self._add_section(sec, items)
                self._wire_preferences()
                self._wire_general()
                self._wire_java()
                self.langing()
                self.lighting(bool(events.settings["theme"]))
                # 插件集合一变就对账：条目没了控件不能留着，重载后还得换成连着
                # 新实例的那一份（见 sync_registry_parts）。
                events.on("plugins_changed", self.sync_registry_parts)

            def _add_section(self, sec, items, index=None):
                f = _FIELDS.get(sec.key, {})
                wid = sec.init(Box(parent=self, entry=sec, items=items, fields=_FIELDS))
                if f.get("attr"):
                    setattr(self, f["attr"], wid)
                spacing = f.get("spacing", 0)
                if index is None:
                    self.add(wid, spacing)
                else:
                    if spacing:
                        self.scroll.scroll_layout.insertSpacing(index, spacing)
                        index += 1
                    self.scroll.scroll_layout.insertWidget(index, wid)
                    self.scroll.barShow()
                self._secs[sec.key] = (wid, self._sig(sec, items))
                return wid

            def _insert_index(self, key, plan):
                """新的一组该插在布局的哪一格：排在它后面、且已经有控件的那组之前。"""
                keys = [s.key for s, _ in plan]
                for later in keys[keys.index(key) + 1:]:
                    wid = self._secs.get(later, (None,))[0]
                    if wid is not None:
                        return self.scroll.scroll_layout.indexOf(wid)
                return self.scroll.scroll_layout.count()

            def _drop_section(self, key):
                wid, _ = self._secs.pop(key)
                self.scroll.scroll_layout.removeWidget(wid)
                wid.setParent(None)
                wid.deleteLater()

            def sync_registry_parts(self):
                """插件集合变了：设置页按注册表对账（增 / 删 / 换实例）。

                为什么要走这一步：设置项是**界面构建期**从注册表建出来的，条目被
                摘掉时没有任何人会顺手删那个控件 —— 留着就是一个连着已卸载实例的
                开关（拨一下写进一个已经不存在的插件的设置里）；插件重载之后，
                台上那些控件也还连着旧实例。页面 / 语言 / 样式 / 托盘各自都订了
                plugins_changed 对账，设置页跟着一起。

                内置那几组签名永不改变（条目在本文件 register() 里一次性登记），
                所以它们连同手工接的线原样留着 —— 重建只落在插件动过的那一组上，
                重建之后由 _reconnect 把那一组的手工线按新控件重接。
                """
                plan = self._plan()
                want = {sec.key: (sec, items) for sec, items in plan}
                changed = []
                for key in list(self._secs):
                    now = want.get(key)
                    if now is None or self._sig(*now) != self._secs[key][1]:
                        self._drop_section(key)
                        changed.append(key)
                for sec, items in plan:
                    if sec.key in self._secs:
                        continue
                    self._add_section(sec, items, self._insert_index(sec.key, plan))
                    self._reconnect(sec.key)
                    changed.append(sec.key)
                if changed:
                    self.langing()
                    self.lighting(bool(events.settings["theme"]))
                return changed

            def _reconnect(self, key):
                """某一组重建之后，把它那几条手工接的线按新控件重接一遍。

                只接这一组：别的组没重建，重复连接会让同一个动作执行两遍。
                """
                {"core.setting.preferences": self._wire_preferences,
                 "core.setting.general": self._wire_general,
                 "core.setting.java": self._wire_java,
                 }.get(key, lambda: None)()

            # ── 行为绑定：控件已就位，这里只接信号与填初值 ──

            def _wire_preferences(self):
                self._t1_theme.btn.setChecked(events.settings["theme"])
                self._t1_theme.push.connect(events.setTheme)

                def _t1_lang_showEvent(combo):
                    items = events.lang.get_langs_info()
                    combo.clear()
                    for lang_name, lang_info in items.items():
                        combo.addItem(f"{lang_info[0]}",lang_name)
                        combo.setItemData(combo.count()-1,lang_info[1], Qt.ToolTipRole)
                    combo.setCurrentIndex(combo.findData(events.settings["language"]))
                _t1_lang_showEvent(self._t1_lang.combo)
                self._t1_lang.combo.popupAboutToShow.connect(lambda: _t1_lang_showEvent(self._t1_lang.combo))
                self._t1_lang.combo.activated.connect(lambda: events.lang.load(self._t1_lang.combo.currentData()) if self._t1_lang.combo.currentIndex() != -1 and not self._t1_lang.combo.currentData() == events.settings["language"] else None)

            def _wire_general(self):
                # 关闭窗口时：未设置（= 每次点 × 都弹一层问，见 main.py 的 close_()）
                # / 隐藏到托盘 / 退出启动器。写的就是那个 closeByTray（浮层里那条
                # 「保存到设置」写的是同一个键，两处看到的是同一件事）。
                # 「未设置」只在当前真的是 None 时露面：一旦选定了做法，这个选项就
                # 不再出现（想回到「每次都问」得手改 settings.json —— 这是有意的，
                # 不然那个选项会变成一个随时能把用户的选择抹掉的按钮）。
                def _t2_close_fill():
                    combo = self._t2_close.combo
                    value = events.settings["closeByTray"]
                    combo.clear()
                    if value is None:
                        combo.addItem(events.lang.get("core.wid.closeAsk.unset"), "unset")
                    combo.addItem(events.lang.get("core.wid.closeAsk.tray"), "tray")
                    combo.addItem(events.lang.get("core.wid.closeAsk.quit"), "quit")
                    combo.setCurrentIndex(combo.findData(
                        "unset" if value is None else ("tray" if value else "quit")))

                def _t2_close_pick(data):
                    events.settings["closeByTray"] = None if data == "unset" else (data == "tray")

                _t2_close_fill()
                # 每次展开前重填：选项集本身会随当前值变（未设置那条的来去）
                self._t2_close.combo.popupAboutToShow.connect(_t2_close_fill)
                self._t2_close.combo.activated.connect(
                    lambda: _t2_close_pick(self._t2_close.combo.currentData()))

            def _wire_java(self):
                # 添加 Java：挂在 Java 那一组的末尾（尺寸跟游戏管理那排按钮一致）。
                # 复合控件（QWidget + 布局 + 按钮），不是标准条目，仍手写 ——
                # 但挂进容器（sec_java），不再往页面上平铺。
                self._t3_add_row = self.sec_java.add_wid(QWidget(), 20)
                self._t3_add_row_layout = QHBoxLayout(self._t3_add_row)
                self._t3_add_row_layout.setContentsMargins(0,0,0,0)
                self._t3_add_row_layout.setSpacing(8)
                self._t3_add_row_layout.setAlignment(Qt.AlignLeft)
                self._t3_add_row_layout.addSpacing(28)
                self._t3_add = QPushButton(self._t3_add_row)
                self._t3_add.setProperty("wid","btn")
                self._t3_add.setProperty("lang","core.wid.pages.setting.launcher.java.add")
                self._t3_add.setFixedSize(122,40)
                self._t3_add.setIconSize(QSize(16,16))
                self._t3_add_row_layout.addWidget(self._t3_add,0)
                self._t3_add.clicked.connect(lambda: self._t3_add_clicked())
                self._t3_add_light = None      # 重建后是新按钮，主题色得重刷一遍
                self._t3_select_hasjava = True
                QTimer.singleShot(0, lambda: self._t3_select_fill())
                self._t3_select.combo.popupAboutToShow.connect(lambda: self._t3_select_fill())
                self._t3_select.combo.activated.connect(lambda: events.settings.__setitem__("javaPath", self._t3_select.combo.currentData() if (self._t3_select.combo.currentData() != "auto") else None))

            def _t3_select_fill(self, javas=None):
                if getattr(self, "_t3_select", None) is None:
                    return          # Java 那一组还没建出来（总线先广播过一次）
                if javas is None:
                    javas = events.settings["javaPaths"]
                else:
                    javas = list(javas)
                events.settings["javaPaths"] = javas
                # 失效路径不进下拉框（设置里那份保持原样：硬盘插回来还能用）
                show = [java for java in javas if javaManager.isJava(java[0])]
                combo = self._t3_select.combo
                combo.clear()
                if not show:
                    self._t3_select_hasjava = False
                    combo.addItem(events.lang.get("core.wid.pages.setting.launcher.java.select.none"),"nojava")
                    return
                self._t3_select_hasjava = True
                combo.addItem(events.lang.get("core.wid.pages.setting.launcher.java.select.auto"),"auto")
                for java in show:
                    combo.addItem(f"v{java[1]}",java[0])
                    combo.setItemData(combo.count()-1,java[0],Qt.ToolTipRole)
                select = "auto"
                chosen = events.settings["javaPath"]
                for java in show:
                    # 记法可能变过（绝对 ↔ 相对），比真身而不是比字符串
                    if chosen and javaManager.sameJava(chosen, java[0]):
                        select = java[0]
                events.settings["javaPath"] = select if select != "auto" else None
                combo.setCurrentIndex(combo.findData(select))

            def _t3_add_java(self, java):
                # 记进候选表（javaManager 与两个页面的下拉框都读这一份）：先剔掉指向同一个
                # java.exe 的旧条目（写法不同也算同一个），再按路径排序
                java = javaManager.resolve(java)
                javas = [item for item in list(events.settings["javaPaths"])
                         if item and not javaManager.sameJava(item[0], java)]
                javas.append([javaManager.record(java),javaManager.getJavaVersion(java)])
                javas.sort(key=lambda item: item[0].lower())
                events.settings["javaPaths"] = javas
                events.saveSettings()
                self._t3_select_fill()

            def _t3_add_clicked(self):
                # 先选目录：认得出 <目录>/bin/java.exe 才往下走，认不出弹浮层说明原因
                folder = QFileDialog.getExistingDirectory(self,events.lang.get("core.wid.pages.setting.launcher.java.add"))
                if not folder:
                    return
                java = os.path.join(folder,"bin","java.exe")
                error = None
                if not javaManager.isJava(java):
                    error = t(events.lang.get("core.log.warning.javaAddInvalid"),folder)
                    events.logger.warning(error,name="Java")
                events.emit(
                    "overlayRequested",
                    self.AddJava(folder,self._t3_add_java,error))

            class AddJava(QWidget):
                """添加 Java 的叠加浮层：目录已经在外面选好了，这里只交代「认出了哪个 Java」。

                记法不用选：装在启动器目录里的一律记相对路径（整个启动器文件夹能整体搬走），
                在外面的记绝对路径，由 javaManager.record() 定。error 非空时是错误态：目录
                不可用，这里只说明原因，不写候选表；确认后把 java.exe 路径交给 on_ok()。
                """

                def __init__(self, folder=None, on_ok=None, error=None):
                    super().__init__()
                    self.on_ok = on_ok
                    self.error = error     # 非空则是错误态：只显示原因
                    self.folder = folder   # 外面选好的目录（绝对路径）
                    self.java = javaManager.resolve(os.path.join(folder, "bin", "java.exe"))
                    # 遮罩与居中由叠加浮层统一提供，本页自身即弹窗面板
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.setProperty("wid", "color2")
                    self.init_wid()
                    self.langing()
                    self.lighting(bool(events.settings.get("theme")))
                    bus.bind(self)

                def init_wid(self):
                    self.setFixedSize(360, 160)

                    self.layout = QVBoxLayout(self)
                    self.layout.setSpacing(0)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setAlignment(Qt.AlignTop)

                    # 标题行：标题 + ×
                    self.top = QWidget()
                    self.top.setFixedHeight(30)
                    self.layout.addWidget(self.top, 0)
                    self.top_layout = QHBoxLayout(self.top)
                    self.top_layout.setContentsMargins(15, 0, 3, 0)
                    self.top_layout.setSpacing(0)

                    self.title = QLabel()
                    self.title.setProperty("wid", "title")
                    self.title.setStyleSheet("font-size: 16px;")
                    self.top_layout.addWidget(self.title, 1)

                    self.btn_close = QPushButton()
                    self.btn_close.setFixedSize(24, 24)
                    self.btn_close.setProperty("wid", "tbtn")
                    self.btn_close.clicked.connect(lambda: self._close())
                    self.top_layout.addWidget(self.btn_close, 0)

                    self.line = QWidget()
                    self.line.setFixedHeight(1)
                    self.line.setProperty("wid", "line")
                    self.layout.addWidget(self.line, 0)

                    self.body = QWidget()
                    self.body.setStyleSheet("background: transparent")
                    self.layout.addWidget(self.body, 1)
                    self.body_layout = QVBoxLayout(self.body)
                    self.body_layout.setContentsMargins(15, 10, 15, 15)
                    self.body_layout.setSpacing(8)
                    self.body_layout.setAlignment(Qt.AlignTop)

                    # 目录行：显示选中的目录（写进候选表的是 java.exe，记法由位置定）
                    self.dir = QLabel()
                    self.dir.setProperty("wid", "text")
                    self.dir.setStyleSheet("font-size: 13px;")
                    self.dir.setWordWrap(True)
                    self.dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    self.dir.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                    self.body_layout.addWidget(self.dir, 1)

                    # 提示行：识别出来的版本
                    self.msg = QLabel()
                    self.msg.setProperty("wid", "text")
                    self.msg.setStyleSheet("font-size: 13px; color: #f0b731;")
                    self.msg.setWordWrap(True)
                    self.msg.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                    self.body_layout.addWidget(self.msg, 0)

                    self.bottom = QHBoxLayout()
                    self.bottom.setContentsMargins(0, 0, 0, 0)
                    self.bottom.setSpacing(0)
                    self.bottom.addStretch(1)

                    self.btn_ok = QPushButton()
                    self.btn_ok.setProperty("wid", "btn")
                    self.btn_ok.setFixedSize(80, 30)
                    self.btn_ok.setStyleSheet("background-color: #f0b731; border: none;")
                    self.btn_ok.clicked.connect(lambda: self._close() if self.error else self._on_ok())
                    self.bottom.addWidget(self.btn_ok, 0)
                    self.body_layout.addLayout(self.bottom)

                # ---------- 文案 / 主题 ----------
                def langing(self):
                    self.title.setText(events.lang.get("core.wid.pages.setting.launcher.java.add"))
                    self.dir.setText(self.folder)
                    self.btn_ok.setText(events.lang.get("core.text.yes"))
                    self.btn_close.setToolTip(events.lang.get("core.wid.top.close"))
                    if self.error is not None:
                        # 错误态：目录不可用，提示行只说原因
                        self.msg.setStyleSheet("font-size: 13px; color: #e06c6c;")
                        self.msg.setText(self.error)
                        return
                    self.msg.setStyleSheet("font-size: 13px; color: #f0b731;")
                    self.msg.setText(t(events.lang.get("core.wid.pages.setting.launcher.java.add.ok"),
                                       javaManager.getJavaVersion(self.java)))

                def lighting(self, light: bool):
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    self.btn_close.setIcon(QIcon(change_color(getPath(TBT_CLOSE), color).pixmap(24, 24)))

                # ---------- 确定：把认出的 java.exe 交给外面记进候选表 ----------
                def _on_ok(self):
                    if self.on_ok is not None:
                        self.on_ok(self.java)
                    self._close()

                def _close(self):
                    """出叠并销毁；防手滑连点两次 × 时对象已没了。"""
                    try:
                        events.emit("overlayClosed", self, True)
                    except RuntimeError:
                        pass

            def showEvent(self, event):
                """本页显示：让 javaManager 扫一遍并在可见期间低频轮询（hideEvent 里收工）。"""
                super().showEvent(event)
                javaManager.watch()

            def hideEvent(self, event):
                super().hideEvent(event)
                javaManager.unwatch()

            def lighting(self, light):
                """folder.png 是白图，按主题改色，取色跟着按钮文字走。"""
                if getattr(self,"_t3_add",None) is None:
                    return   # 总线在 Page.__init__ 就广播过：那会儿按钮还没建
                if getattr(self,"_t3_add_light",None) == light:
                    return
                self._t3_add_light = light
                self._t3_add.setIcon(change_color(getPath(FILE_FOLDER),
                                                  QColor(22,22,22) if light else QColor(255,255,255)))

            def langing(self):
                super().langing()
                try:
                    self._t3_add.setText(events.lang.get("core.wid.pages.setting.launcher.java.add"))
                    t3SelecIndex1 = self._t3_select.combo.findData("nojava")
                    t3SelecIndex2 = self._t3_select.combo.findData("auto")
                    if t3SelecIndex1 >= 0:self._t3_select.combo.setItemText(t3SelecIndex1,events.lang.get("core.wid.pages.setting.launcher.java.select.none"))
                    if t3SelecIndex2 >= 0:self._t3_select.combo.setItemText(t3SelecIndex2,events.lang.get("core.wid.pages.setting.launcher.java.select.auto"))
                except : pass


def register():
    """设置子页与条目的登记。由 pages/builtin.py 调用一次。

    原先这两段写在 init_wid 里：第二次构建设置页就会撞「已存在条目」。
    init 从 Box.parent 取宿主（子页是 Main 实例，条目是 Launcher 实例）。
    """

    registry.add("core.setting.pages", "core.setting.launcher",
                 init=lambda b: b.parent.Launcher(b.parent, b.title, b.icon),
                 order=10,
                 title="core.wid.pages.setting.launcher", icon=ACT_UNITS)
    # 分组容器：条目用 section 字段指向它。空容器设置页不摆（插件的组没装插件时
    # 就是空的，那块标题也就不出现）。spacing 是加在容器上方的空隙。
    registry.add("core.setting.sections", "core.setting.preferences",
                 init=lambda b: Section(b.parent, b.title, b.items, _FIELDS),
                 order=10,
                 title="core.wid.pages.setting.launcher.preferences")
    registry.add("core.setting.sections", "core.setting.general",
                 init=lambda b: Section(b.parent, b.title, b.items, _FIELDS),
                 order=40,
                 title="core.wid.pages.setting.launcher.general")
    registry.add("core.setting.sections", "core.setting.java",
                 init=lambda b: Section(b.parent, b.title, b.items, _FIELDS),
                 order=50,
                 title="core.wid.pages.setting.launcher.java")
    # 插件那些设置项的落脚处（Plugin.add_setting 的默认 section）。插件想自己开
    # 一组就照上面这样再登记一条容器。
    registry.add("core.setting.sections", "core.setting.plugins",
                 init=lambda b: Section(b.parent, b.title, b.items, _FIELDS),
                 order=900,
                 title="core.wid.pages.setting.plugins")
    # 标准条目：attr 是绑回 Launcher 的老名字，下面的行为绑定代码仍按这些名字
    # 引用控件；section 指着上面那几个容器。
    registry.add("core.setting.items", "core.setting.theme",
                 init=simple(Bool), section="core.setting.preferences", order=20,
                 title="core.wid.pages.setting.launcher.preferences.theme")
    registry.add("core.setting.items", "core.setting.lang",
                 init=simple(Combo), section="core.setting.preferences", order=30,
                 title="core.wid.pages.setting.launcher.preferences.lang")
    # 通用：关闭窗口时怎么办（和点 × 弹的那一层是同一个设置）
    registry.add("core.setting.items", "core.setting.close",
                 init=simple(Combo), section="core.setting.general", order=10,
                 title="core.wid.pages.setting.launcher.general.close")
    registry.add("core.setting.items", "core.setting.java.select",
                 init=simple(Combo), section="core.setting.java", order=60,
                 title="core.wid.pages.setting.launcher.java.select")
