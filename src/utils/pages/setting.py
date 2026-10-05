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

from ..options.items import Bool, Combo
from ..options.scrolls import Scroll
from ..options.texts import Title

from ..path_utils import getPath
from ..utils import change_color, t
from ..resources import (ACT_UNITS, BTN_SETTING, FILE_FOLDER, TBT_CLOSE)
from ..registry import page, Box, registry, simple

from ._init import *


@page("core.setting")
class Setting(Page):
    name = "core.wid.pages.setting"
    icon = BTN_SETTING
    order = 40

    def __init__(self, btn=None):
        super().__init__(btn)

    class Left(Leftw):
        def __init__(self, parent=None, root=None):
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
            btn = self.Btns(text, icon, self, self.root)
            self.scroll.add(btn)
            self.bthGroup.addButton(btn)
            return btn


        class Btns(QPushButton):
            def __init__(self, text=None, icon=None, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.text_ = text
                self.icon_ = icon
                self.init_ui()
                self.init_wid()
                bus.bind(self)

            def init_ui(self):
                self.setFixedSize(120, 30)
                self.setAttribute(Qt.WA_StyledBackground, False)
                self.setProperty("wid", "lbtn")
                self.setCheckable(True)

            def init_wid(self):
                self.layout = QHBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(5)

                self.icon = QLabel()
                self.icon.setAttribute(Qt.WA_StyledBackground, False)
                self.icon.setFixedSize(30, 30)
                self.icon.setScaledContents(False)
                self.layout.addWidget(self.icon)
                self.icon.setAlignment(Qt.AlignCenter)

                self.text = QLabel()
                self.text.setAttribute(Qt.WA_StyledBackground, False)
                self.text.setFixedSize(90, 30)
                self.text.setProperty("wid", "lbtn")
                self.langing()
                self.layout.addWidget(self.text)

            def langing(self):
                if self.text_ is not None:
                    self.text.setText(events.lang.get(self.text_))
                    self.setToolTip(events.lang.get(self.text_))

            def lighting(self, light: bool):
                if self.icon_ is not None:
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    logo = change_color(self.icon_, color)
                    pixmap = logo.pixmap(30,30)

                    if not pixmap.isNull():
                        smooth_pixmap = pixmap.scaled(
                            22, 22,
                            Qt.KeepAspectRatio,
                            Qt.FastTransformation
                        )
                        self.icon.setPixmap(smooth_pixmap)
                    else:
                        events.logger.warning(f"Failed to load pixmap for {self.icon_}")


            def setText(self, _text):
                self.text_ = _text
                self.langing()

            def setIcon(self, _icon):
                self.icon_ = _icon
                self.lighting(events.settings["theme"])
    
    class Main(Mainw):
        def __init__(self, parent=None, root=None):
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

            # 设置子页走注册中心：加一个子页 = 写一个 Page 子类 + 一条 registry.add。
            # init 由子页自己提供，装配方不猜它的构造签名。
            registry.add("core.setting.pages", "core.setting.launcher",
                         init=lambda b: self.Launcher(b.parent, b.root, b.title, b.icon),
                         order=10,
                         title="core.wid.pages.setting.launcher", icon=ACT_UNITS)

            for e in registry.entries("core.setting.pages"):
                self.add_page(e)

        def add_page(self, entry):
            """按条目建一个子页：备好按钮 → 交给条目的 init 去造。"""
            btn = self.parent.left.add_btn(entry.title, entry.icon)
            page_ = entry.init(Box(parent=self, root=self.root, entry=entry, btn=btn))
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.pages.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.pages.setCurrentWidget(page_))
            return page_

        class Page(QWidget):
            def __init__(self,parent=None,root=None,text=None,icon=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.text=text
                self.icon=icon

                self._init_wid()
                bus.bind(self)

            def _init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
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
            def __init__(self, parent=None, root=None, text=None,icon=None):
                super().__init__(parent,root,text,icon)
                self.init_wid()

            def init_wid(self):
                # 标准条目（分组标题 / Bool / Combo）走注册中心：加一项 = 一条 registry.add。
                # attr 是绑到 self 上的名字 —— 下面的行为代码仍按老名字引用控件；
                # 这一批只把「有哪些项、什么顺序、归哪组」数据化，行为绑定留在原地。

                registry.add("core.setting.items", "core.setting.preferences",
                             init=simple(Title), group="launcher", order=10, spacing=30,
                             attr="_title1",
                             title="core.wid.pages.setting.launcher.preferences")
                registry.add("core.setting.items", "core.setting.theme",
                             init=simple(Bool), group="launcher", order=20, attr="_t1_theme",
                             title="core.wid.pages.setting.launcher.preferences.theme")
                registry.add("core.setting.items", "core.setting.lang",
                             init=simple(Combo), group="launcher", order=30, attr="_t1_lang",
                             title="core.wid.pages.setting.launcher.preferences.lang")
                registry.add("core.setting.items", "core.setting.general",
                             init=simple(Title), group="launcher", order=40, spacing=30,
                             attr="_title2",
                             title="core.wid.pages.setting.launcher.general")
                registry.add("core.setting.items", "core.setting.java",
                             init=simple(Title), group="launcher", order=50, spacing=30,
                             attr="_title3",
                             title="core.wid.pages.setting.launcher.java")
                registry.add("core.setting.items", "core.setting.java.select",
                             init=simple(Combo), group="launcher", order=60, attr="_t3_select",
                             title="core.wid.pages.setting.launcher.java.select")

                for e in registry.entries("core.setting.items", where={"group": "launcher"}):
                    wid = e.init(Box(parent=self, root=self.root, entry=e))
                    self.add(wid, e.get("spacing", 0))
                    attr = e.get("attr")          # 可选：只有内置条目要绑回老名字
                    if attr:
                        setattr(self, attr, wid)

                # 插件登记进来的设置项：单独归到末尾，不和内置项混排。
                # 分组名固定 'plugins'（Plugin.add_setting 的默认值）；卸载插件时
                # 它按命名空间摘条目，这一段自然就空了。
                plugin_items = registry.entries("core.setting.items",
                                                where={"group": "plugins"})
                if plugin_items:
                    self.add(Title(self, "core.wid.pages.setting.plugins"), 30)
                    for e in plugin_items:
                        wid = e.init(Box(parent=self, root=self.root, entry=e))
                        self.add(wid, e.get("spacing", 0))

                # ── 行为绑定：控件已就位，这里只接信号与填初值 ──
                self._t1_theme.btn.setChecked(events.settings["theme"])
                self._t1_theme.push.connect(events.setTheme)

                def _t1_lang_showEvent(self,combo):
                    items = events.lang.get_langs_info()
                    combo.clear()
                    for lang_name, lang_info in items.items():
                        combo.addItem(f"{lang_info[0]}",lang_name)
                        combo.setItemData(combo.count()-1,lang_info[1], Qt.ToolTipRole)
                    combo.setCurrentIndex(combo.findData(events.settings["language"]))
                _t1_lang_showEvent(self,self._t1_lang.combo)
                self._t1_lang.combo.popupAboutToShow.connect(lambda: _t1_lang_showEvent(self._t1_lang,self._t1_lang.combo))
                self._t1_lang.combo.activated.connect(lambda: events.lang.load(self._t1_lang.combo.currentData()) if self._t1_lang.combo.currentIndex() != -1 and not self._t1_lang.combo.currentData() == events.settings["language"] else None)

                # 添加 Java：挂在选择框下面（尺寸跟游戏管理那排按钮一致）
                # 复合控件（QWidget + 布局 + 按钮），不是标准条目，仍手写
                self._t3_add_row = self.add(QWidget(),20)
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
                self._t3_select_hasjava = True
                def _t3_select_fill(javas=None):
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

                QTimer.singleShot(0,lambda: _t3_select_fill())
                self._t3_select.combo.popupAboutToShow.connect(lambda:_t3_select_fill())
                self._t3_select.combo.activated.connect(lambda:(events.settings.__setitem__("javaPath",self._t3_select.combo.currentData() if (self._t3_select.combo.currentData() != "auto") else None)))
                javaManager.changed.connect(lambda javas: _t3_select_fill(javas))

                def _t3_add_java(java):
                    # 记进候选表（javaManager 与两个页面的下拉框都读这一份）：先剔掉指向同一个
                    # java.exe 的旧条目（写法不同也算同一个），再按路径排序
                    java = javaManager.resolve(java)
                    javas = [item for item in list(events.settings["javaPaths"])
                             if item and not javaManager.sameJava(item[0], java)]
                    javas.append([javaManager.record(java),javaManager.getJavaVersion(java)])
                    javas.sort(key=lambda item: item[0].lower())
                    events.settings["javaPaths"] = javas
                    events.saveSettings()
                    _t3_select_fill()

                def _t3_add_clicked():
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
                        self.AddJava(self.root,folder,_t3_add_java,error))

                self._t3_add.clicked.connect(lambda: _t3_add_clicked())

                self.langing()
                self.lighting(bool(events.settings["theme"]))

            class AddJava(QWidget):
                """添加 Java 的叠加浮层：目录已经在外面选好了，这里只交代「认出了哪个 Java」。

                记法不用选：装在启动器目录里的一律记相对路径（整个启动器文件夹能整体搬走），
                在外面的记绝对路径，由 javaManager.record() 定。error 非空时是错误态：目录
                不可用，这里只说明原因，不写候选表；确认后把 java.exe 路径交给 on_ok()。
                """

                def __init__(self, root=None, folder=None, on_ok=None, error=None):
                    super().__init__()
                    self.root = root
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

