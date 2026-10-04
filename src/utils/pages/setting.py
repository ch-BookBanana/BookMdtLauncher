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

from ..javaManager import javaManager

from ..options.items import Bool, Combo
from ..options.scrolls import Scroll
from ..options.texts import Title

from ..path_utils import getPath
from ..utils import change_color, t

from ._init import *


class Setting(Page):
    def __init__(self, parent=None, root=None, text=None, logo=None):
        super().__init__(parent, root, text, logo)

    class Left(Leftw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
            self.resize_(120)
            self.init_wid()
            bus.bind(self)


        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.scroll = Scroll(self, self.root)
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
                    self.text.setText(self.root.langer.get(self.text_))
                    self.setToolTip(self.root.langer.get(self.text_))

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
                        self.root.logger.warning(f"Failed to load pixmap for {self.icon_}")


            def setText(self, _text):
                self.text_ = _text
                self.langing()

            def setIcon(self, _icon):
                self.icon_ = _icon
                self.lighting(self.root.settings["theme"])
    
    class Main(Mainw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
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


            self.launcher = self.add_page("wid.pages.setting.launcher","src/assets/actions/units.png",self.Launcher)

            

        def add_page(self,text=None,icon=None,page=None):
            if page is None: page = self.Page
            btn = self.parent.left.add_btn(text,icon)
            page_ = page(self,self.root,text,icon)
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

                self.scroll = Scroll(self, self.root, margins=(30, 0, 30, 0))
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
                self._title.setText(self.root.langer.get(self.text))
            

            def add(self, wid, spacing=0):
                return self.scroll.add(wid, spacing)

        class Launcher(Page):
            def __init__(self, parent=None, root=None, text=None,icon=None):
                super().__init__(parent,root,text,icon)
                self.init_wid()

            def init_wid(self):
                self._title1 = self.add(Title(self,self.root,"wid.pages.setting.launcher.preferences"),30)

                self._t1_theme = self.add(Bool(self,self.root,"wid.pages.setting.launcher.preferences.theme"))
                self._t1_theme.btn.setChecked(self.root.settings["theme"])
                self._t1_theme.push.connect(self.root.setTheme)

                self._t1_lang = self.add(Combo(self,self.root,"wid.pages.setting.launcher.preferences.lang"))
                def _t1_lang_showEvent(self,combo):
                    items = self.root.langer.get_langs_info()
                    combo.clear()
                    for lang_name, lang_info in items.items():
                        combo.addItem(f"{lang_info[0]}",lang_name)
                        combo.setItemData(combo.count()-1,lang_info[1], Qt.ToolTipRole)
                    combo.setCurrentIndex(combo.findData(self.root.settings["language"]))
                _t1_lang_showEvent(self,self._t1_lang.combo)
                self._t1_lang.combo.popupAboutToShow.connect(lambda: _t1_lang_showEvent(self._t1_lang,self._t1_lang.combo))
                self._t1_lang.combo.activated.connect(lambda: self.root.langer.load(self._t1_lang.combo.currentData()) if self._t1_lang.combo.currentIndex() != -1 and not self._t1_lang.combo.currentData() == self.root.settings["language"] else None)


                self._title2 = self.add(Title(self,self.root,"wid.pages.setting.launcher.general"),30)


                self._title3 = self.add(Title(self,self.root,"wid.pages.setting.launcher.java"),30)
                self._t3_select = self.add(Combo(self,self.root,"wid.pages.setting.launcher.java.select"))
                # 添加 Java：挂在选择框下面（尺寸跟游戏管理那排按钮一致）
                self._t3_add_row = self.add(QWidget(),20)
                self._t3_add_row_layout = QHBoxLayout(self._t3_add_row)
                self._t3_add_row_layout.setContentsMargins(0,0,0,0)
                self._t3_add_row_layout.setSpacing(8)
                self._t3_add_row_layout.setAlignment(Qt.AlignLeft)
                self._t3_add_row_layout.addSpacing(28)
                self._t3_add = QPushButton(self._t3_add_row)
                self._t3_add.setProperty("wid","btn")
                self._t3_add.setProperty("lang","wid.pages.setting.launcher.java.add")
                self._t3_add.setFixedSize(122,40)
                self._t3_add.setIconSize(QSize(16,16))
                self._t3_add_row_layout.addWidget(self._t3_add,0)
                self._t3_select_hasjava = True
                def _t3_select_fill(javas=None):
                    if javas is None:
                        javas = self.root.settings["javaPaths"]
                    else:
                        javas = list(javas)
                    self.root.settings["javaPaths"] = javas
                    # 失效路径不进下拉框（设置里那份保持原样：硬盘插回来还能用）
                    show = [java for java in javas if javaManager.isJava(java[0])]
                    combo = self._t3_select.combo
                    combo.clear()
                    if not show:
                        self._t3_select_hasjava = False
                        combo.addItem(self.root.langer.get("wid.pages.setting.launcher.java.select.none"),"nojava")
                        return
                    self._t3_select_hasjava = True
                    combo.addItem(self.root.langer.get("wid.pages.setting.launcher.java.select.auto"),"auto")
                    for java in show:
                        combo.addItem(f"v{java[1]}",java[0])
                        combo.setItemData(combo.count()-1,java[0],Qt.ToolTipRole)
                    select = "auto"
                    chosen = self.root.settings["javaPath"]
                    for java in show:
                        # 记法可能变过（绝对 ↔ 相对），比真身而不是比字符串
                        if chosen and javaManager.sameJava(chosen, java[0]):
                            select = java[0]
                    self.root.settings["javaPath"] = select if select != "auto" else None
                    combo.setCurrentIndex(combo.findData(select))

                QTimer.singleShot(0,lambda: _t3_select_fill())
                self._t3_select.combo.popupAboutToShow.connect(lambda:_t3_select_fill())
                self._t3_select.combo.activated.connect(lambda:(self.root.settings.__setitem__("javaPath",self._t3_select.combo.currentData() if (self._t3_select.combo.currentData() != "auto") else None)))
                javaManager.changed.connect(lambda javas: _t3_select_fill(javas))

                def _t3_add_java(java):
                    # 记进候选表（javaManager 与两个页面的下拉框都读这一份）：先剔掉指向同一个
                    # java.exe 的旧条目（写法不同也算同一个），再按路径排序
                    java = javaManager.resolve(java)
                    javas = [item for item in list(self.root.settings["javaPaths"])
                             if item and not javaManager.sameJava(item[0], java)]
                    javas.append([javaManager.record(java),javaManager.getJavaVersion(java)])
                    javas.sort(key=lambda item: item[0].lower())
                    self.root.settings["javaPaths"] = javas
                    self.root.saveSettings()
                    _t3_select_fill()

                def _t3_add_clicked():
                    # 先选目录：认得出 <目录>/bin/java.exe 才往下走，认不出弹浮层说明原因
                    folder = QFileDialog.getExistingDirectory(self,self.root.langer.get("wid.pages.setting.launcher.java.add"))
                    if not folder:
                        return
                    java = os.path.join(folder,"bin","java.exe")
                    error = None
                    if not javaManager.isJava(java):
                        error = t(self.root.langer.get("log.warning.javaAddInvalid"),folder)
                        self.root.logger.warning(error,name="Java")
                    self.root.window.floatingOverlay.add_page(
                        self.AddJava(self.root,folder,_t3_add_java,error))

                self._t3_add.clicked.connect(lambda: _t3_add_clicked())

                self.langing()
                self.lighting(bool(self.root.settings["theme"]))

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
                    self.lighting(bool(self.root.settings.get("theme")))
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
                    self.title.setText(self.root.langer.get("wid.pages.setting.launcher.java.add"))
                    self.dir.setText(self.folder)
                    self.btn_ok.setText(self.root.langer.get("text.yes"))
                    self.btn_close.setToolTip(self.root.langer.get("wid.top.close"))
                    if self.error is not None:
                        # 错误态：目录不可用，提示行只说原因
                        self.msg.setStyleSheet("font-size: 13px; color: #e06c6c;")
                        self.msg.setText(self.error)
                        return
                    self.msg.setStyleSheet("font-size: 13px; color: #f0b731;")
                    self.msg.setText(t(self.root.langer.get("wid.pages.setting.launcher.java.add.ok"),
                                       javaManager.getJavaVersion(self.java)))

                def lighting(self, light: bool):
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    self.btn_close.setIcon(QIcon(change_color(getPath("src/assets/tribtns/close.png"), color).pixmap(24, 24)))

                # ---------- 确定：把认出的 java.exe 交给外面记进候选表 ----------
                def _on_ok(self):
                    if self.on_ok is not None:
                        self.on_ok(self.java)
                    self._close()

                def _close(self):
                    """出叠并销毁；防手滑连点两次 × 时对象已没了。"""
                    try:
                        self.root.window.floatingOverlay.pop_page(self)
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
                self._t3_add.setIcon(change_color(getPath("src/assets/files/folder.png"),
                                                  QColor(22,22,22) if light else QColor(255,255,255)))

            def langing(self):
                super().langing()
                try:
                    self._t3_add.setText(self.root.langer.get("wid.pages.setting.launcher.java.add"))
                    t3SelecIndex1 = self._t3_select.combo.findData("nojava")
                    t3SelecIndex2 = self._t3_select.combo.findData("auto")
                    if t3SelecIndex1 >= 0:self._t3_select.combo.setItemText(t3SelecIndex1,self.root.langer.get("wid.pages.setting.launcher.java.select.none"))
                    if t3SelecIndex2 >= 0:self._t3_select.combo.setItemText(t3SelecIndex2,self.root.langer.get("wid.pages.setting.launcher.java.select.auto"))
                except : pass
