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

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScrollBar, QStackedWidget, QVBoxLayout

from ..javaScanner import javaScanner

from ..options.items import Bool, Combo
from ..options.texts import Title

from ..utils import change_color

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

            self.scroll = QScrollArea(self)
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.NoFrame)
            self.layout.addWidget(self.scroll)

            self.main = QWidget()
            self.scroll_layout = QVBoxLayout(self.main)
            self.scroll_layout.setContentsMargins(0, 0, 0, 0)
            self.scroll_layout.setSpacing(0)
            self.scroll_layout.setAlignment(Qt.AlignTop)
            self.scroll.setWidget(self.main)
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
            
            self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
            self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
            self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

            self.bthGroup = QButtonGroup(self)

        def add_btn(self, text=None, icon=None):
            btn = self.Btns(text, icon, self, self.root)
            self.scroll_layout.addWidget(btn)
            self.bthGroup.addButton(btn)
            self.barShow()
            return btn

        def barShow(self):
            self.scroll_slider.setVisible(self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum())

        def resizeEvent(self,event):
            self.scroll_slider.setGeometry(self.scroll.width()-5,0,5,self.scroll.height())
            self.barShow()
            super().resizeEvent(event)

        def showEvent(self,event):
            super().showEvent(event)
            self.barShow()


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

                self.scroll = QScrollArea(self)
                self.scroll.setStyleSheet("max-width: 600px;")
                self.scroll.setWidgetResizable(True)
                self.scroll.setFrameShape(QFrame.NoFrame)
                self.layout.addWidget(self.scroll)

                self.main = QWidget()
                
                self.scroll_layout = QVBoxLayout(self.main)
                self.scroll_layout.setContentsMargins(30,0,30,0)
                self.scroll_layout.setSpacing(0)
                self.scroll_layout.setAlignment(Qt.AlignTop)
                self.scroll.setWidget(self.main)
                self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

                self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                
                self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                self._title = QLabel()
                self._title.setProperty("wid", "title")
                self._title.setFixedHeight(38)
                self._title.setStyleSheet("font-size: 28px;")
                self._title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.scroll_layout.addWidget(self._title)
                self.langing()

            def langing(self):
                self._title.setText(self.root.langer.get(self.text))
            

            def add(self, wid, spacing=0):
                if spacing: self.scroll_layout.addSpacing(spacing)
                self.scroll_layout.addWidget(wid)
                return wid

            def barShow(self):
                self.scroll_slider.setVisible(self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum())

            def resizeEvent(self,event):
                self.scroll_slider.setGeometry(self.scroll.width()-5,0,5,self.scroll.height())
                self.barShow()
                super().resizeEvent(event)

            def showEvent(self,event):
                super().showEvent(event)
                self.barShow()

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
                self._t3_select_hasjava = True
                def _t3_select_showEvent(self):
                    # 取候选 → 剔失效 → 一次性填下拉框。
                    # 原写法筛空后会回头再调自己一遍（递归），顺带再跑一次整盘嗅探，
                    # 打开下拉框时会顿一下；这里一条直路走到底，筛没了就按"没装 Java"处理。
                    self._t3_select.combo.clear()
                    javas = self.root.settings["javaPaths"]
                    if javas:
                        # 遍历副本：原写法边遍历边 remove，紧挨着的元素会被漏掉
                        for java in list(javas):
                            if not javaScanner.isJava(java[0]):
                                javas.remove(java)
                    else:
                        javas = javaScanner.getJavas()
                        self.root.settings["javaPaths"] = javas
                    if not javas:
                        self._t3_select_hasjava = False
                        self._t3_select.combo.addItem(self.root.langer.get("wid.pages.setting.launcher.java.select.none"),"nojava")
                        return
                    self._t3_select_hasjava = True
                    self._t3_select.combo.addItem(self.root.langer.get("wid.pages.setting.launcher.java.select.auto"),"auto")
                    for java in javas:
                        self._t3_select.combo.addItem(f"v{java[1]}",java[0])
                        self._t3_select.combo.setItemData(self._t3_select.combo.count()-1,java[0],Qt.ToolTipRole)
                    select = "auto"
                    for java in javas:
                        if self.root.settings["javaPath"] == java[0]:
                            select = java[0]
                    self.root.settings["javaPath"] = select if select != "auto" else None
                    self._t3_select.combo.setCurrentIndex(self._t3_select.combo.findData(select))

                QTimer.singleShot(0,lambda: _t3_select_showEvent(self))
                self._t3_select.combo.popupAboutToShow.connect(lambda:_t3_select_showEvent(self))
                self._t3_select.combo.activated.connect(lambda:(self.root.settings.__setitem__("javaPath",self._t3_select.combo.currentData() if (self._t3_select.combo.currentData() != "auto") else None)))

            def langing(self):
                super().langing()
                try:
                    t3SelecIndex1 = self._t3_select.combo.findData("nojava")
                    t3SelecIndex2 = self._t3_select.combo.findData("auto")
                    if t3SelecIndex1 >= 0:self._t3_select.combo.setItemText(t3SelecIndex1,self.root.langer.get("wid.pages.setting.launcher.java.select.none"))
                    if t3SelecIndex2 >= 0:self._t3_select.combo.setItemText(t3SelecIndex2,self.root.langer.get("wid.pages.setting.launcher.java.select.auto"))
                except : pass
