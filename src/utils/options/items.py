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

from ._init import *


class Bool(QWidget):
    push = Signal(bool)
    def __init__(self,parent=None,root=None,text=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.text_ = text
        self.intro_ = ""
        self.tips_ = ""
        self.btnpix = [QPixmap(),QPixmap()]
        self.introable = False
        self.tipsable = False
        self.init_wid()
        bus.bind(self)

    def init_wid(self):
        self.setFixedHeight(40)
        self.layout = QHBoxLayout(self)
        self.layout.setAlignment(Qt.AlignVCenter)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        self.btn = QPushButton()
        self.btn.setProperty("wid","check")
        self.btn.setFixedSize(20,20)
        self.btn.setCheckable(True)
        self.layout.addWidget(self.btn,0)

        self.text = QLabel()
        self.text.setProperty("wid","text")
        self.text.setStyleSheet("font-size: 17px;")
        self.text.setAlignment(Qt.AlignVCenter)
        self.layout.addWidget(self.text,0)
        self.text.setFixedHeight(30)

        self.layout.addStretch(1)

        self.intro = QLabel()
        self.layout.addWidget(self.intro)
        self.intro.hide()
        self.intro.setFixedSize(20,20)

        intr = self.intro.sizePolicy()
        intr.setRetainSizeWhenHidden(True)
        self.intro.setSizePolicy(intr)

        self.tips = QLabel()
        self.layout.addWidget(self.tips)
        self.tips.hide()
        self.tips.setFixedSize(20,20)

        tip = self.tips.sizePolicy()
        tip.setRetainSizeWhenHidden(True)
        self.tips.setSizePolicy(tip)

        self.langing()
        self.lighting(self.root.settings["theme"])
        self.btn.toggled.connect(self.btnEvent)
        self.btn.setIcon(QIcon(self.btnpix[0]))

    def btnEvent(self,booll):
        self.push.emit(booll)
        self.btn.setIcon(QIcon(self.btnpix[1 if booll else 0]))

    def setToolBar(self,wid,shown=None,text=None):
        if wid == "intro":
            if shown is not None:
                self.introable = shown
                self.intro.setVisible(shown)
            if text is not None: self.intro_ = text
        if wid == "tips":
            if shown is not None:
                self.tipsable = shown
                self.tips.setVisible(shown)
            if text is not None: self.tips_ = text
            self.lighting(self.root.settings["theme"])
            self.langing()

    def langing(self):
        self.text.setText(self.root.langer.get(self.text_))
        self.intro.setToolTip(self.root.langer.get(self.intro_))
        self.tips.setToolTip(self.root.langer.get(self.tips_))

    def lighting(self,light):
        self.btnpix =[change_color(getPath("src/assets/actions/btn_on.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(35,35)),change_color(getPath("src/assets/actions/btn_off.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(35,35))]
        if self.introable:
            self.intro.setPixmap(change_color(getPath("src/assets/actions/intro.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
        if self.tipsable:
            self.tips.setPixmap(change_color(getPath("src/assets/actions/tips.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))


class Slider(QWidget):
    push = Signal(int)
    def __init__(self,parent=None,root=None,text=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.text_ = text
        self.intro_ = ""
        self.tips_ = ""
        self.val = lambda i: str(i)
        self.introable = False
        self.tipsable = False
        self.init_wid()
        bus.bind(self)

    def init_wid(self):
        class Slid(QSlider):
            def _get_handle_rect(self):
                opt = QStyleOptionSlider()
                self.initStyleOption(opt)
                return self.style().subControlRect(
                    QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
                )

            def _pos_to_value(self, pos):
                handle_rect = self._get_handle_rect()

                if self.orientation() == Qt.Horizontal:
                    span = self.width() - handle_rect.width()
                    if span <= 0: return self.minimum()
                    pos_in_span = pos.x() - handle_rect.width() / 2.0
                    pos_in_span = max(0.0, min(span, pos_in_span))
                    ratio = pos_in_span / span
                else:
                    span = self.height() - handle_rect.height()
                    if span <= 0: return self.minimum()
                    pos_in_span = (self.height() - pos.y()) - handle_rect.height() / 2.0
                    pos_in_span = max(0.0, min(span, pos_in_span))
                    ratio = pos_in_span / span
                return self.minimum() + round(ratio * (self.maximum() - self.minimum()))

            def mousePressEvent(self, event):
                if event.button() == Qt.LeftButton:
                    self.setValue(self._pos_to_value(event.pos()))
                    self.sliderPressed.emit()
                    self.sliderMoved.emit(self.value())
                    event.accept()
                else: super().mousePressEvent(event)

            def mouseMoveEvent(self, event):
                if event.buttons() & Qt.LeftButton:
                    self.setValue(self._pos_to_value(event.pos()))
                    self.sliderMoved.emit(self.value())
                    event.accept()
                    return
                super().mouseMoveEvent(event)

        self.setFixedHeight(40)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.scroll = Slid(Qt.Horizontal)
        self.scroll.setProperty("wid","mdt")
        self.scroll.setFixedHeight(30)
        self.layout.addWidget(self.scroll)
        self.scroll.valueChanged.connect(self.pushEvent)

        self.intro = QLabel()
        self.layout.addWidget(self.intro)
        self.intro.hide()
        self.intro.setFixedSize(20,20)

        intr = self.intro.sizePolicy()
        intr.setRetainSizeWhenHidden(True)
        self.intro.setSizePolicy(intr)

        self.tips = QLabel()
        self.layout.addWidget(self.tips)
        self.tips.hide()
        self.tips.setFixedSize(20,20)

        tip = self.tips.sizePolicy()
        tip.setRetainSizeWhenHidden(True)
        self.tips.setSizePolicy(tip)

        self.lay2 = QHBoxLayout(self.scroll)
        self.lay2.setContentsMargins(5, 0, 5, 0)
        self.lay2.setSpacing(0)
        self.lay2.setAlignment(Qt.AlignVCenter)

        self.text = QLabel()
        self.text.setProperty("wid","text")
        self.text.setStyleSheet("font-size: 17px;")
        self.text.setAlignment(Qt.AlignVCenter)
        self.text.setFixedHeight(30)
        self.lay2.addWidget(self.text)
        self.text.setAttribute(Qt.WA_TranslucentBackground)

        self.lay2.addStretch(1)

        self.value = QLabel()
        self.value.setProperty("wid","text")
        self.value.setStyleSheet("font-size: 17px;")
        self.value.setAlignment(Qt.AlignVCenter)
        self.value.setFixedHeight(30)
        self.lay2.addWidget(self.value)
        self.value.setAttribute(Qt.WA_TranslucentBackground)

        self.langing()

    def lighting(self,light):
        if self.introable:
            self.intro.setPixmap(change_color(getPath("src/assets/actions/intro.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
        if self.tipsable:
            self.tips.setPixmap(change_color(getPath("src/assets/actions/tips.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))

    def langing(self):
        self.text.setText(self.root.langer.get(self.text_))
        self.intro.setToolTip(self.root.langer.get(self.intro_))
        self.tips.setToolTip(self.root.langer.get(self.tips_))
        self.value.setText(self.val(self.scroll.value()))

    def pushEvent(self, i):
        self.push.emit(i)
        self.value.setText(self.val(i))

    def setToolBar(self,wid,shown=None,text=None):
        if wid == "intro":
            if shown is not None:
                self.introable = shown
                self.intro.setVisible(shown)
            if text is not None: self.intro_ = text
        if wid == "tips":
            if shown is not None:
                self.tipsable = shown
                self.tips.setVisible(shown)
            if text is not None: self.tips_ = text
            self.lighting(self.root.settings["theme"])
            self.langing()


class DropBtnCombo(QComboBox):
    """只在点击下拉箭头时弹出下拉框"""
    def mousePressEvent(self, event):
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        drop_rect = self.style().subControlRect(
            QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxArrow, self
        )
        if drop_rect.contains(event.pos()):
            self.showPopup()
        else:
            super().mousePressEvent(event)


class Combo(QWidget):
    push = Signal(str)

    class _QComboBox(QComboBox):
        popupAboutToShow = Signal()
        def showPopup(self):
            self.popupAboutToShow.emit()
            super().showPopup()

        def wheelEvent(self, event):
            event.ignore()
            if self.parent():
                self.parent().wheelEvent(event)

    def __init__(self,parent=None,root=None,text=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.text_ = text
        self.intro_ = ""
        self.tips_ = ""
        self.introable = False
        self.tipsable = False
        self.init_wid()
        bus.bind(self)

    def init_wid(self):
        self.setFixedHeight(40)
        self.layout = QHBoxLayout(self)
        self.layout.setAlignment(Qt.AlignVCenter)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        self.layout.addSpacing(28)

        self.text = QLabel()
        self.text.setProperty("wid","text")
        self.text.setStyleSheet("font-size: 17px;")
        self.text.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.layout.addWidget(self.text,0)
        self.text.setFixedHeight(30)

        self.layout.addStretch(1)

        self.combo = self._QComboBox()
        self.combo.setFixedHeight(25)
        self.combo.setFixedWidth(150)
        self.layout.addWidget(self.combo,0)

        self.intro = QLabel()
        self.layout.addWidget(self.intro)
        self.intro.hide()
        self.intro.setFixedSize(20,20)

        intr = self.intro.sizePolicy()
        intr.setRetainSizeWhenHidden(True)
        self.intro.setSizePolicy(intr)

        self.tips = QLabel()
        self.layout.addWidget(self.tips)
        self.tips.hide()
        self.tips.setFixedSize(20,20)

        tip = self.tips.sizePolicy()
        tip.setRetainSizeWhenHidden(True)
        self.tips.setSizePolicy(tip)

        self.langing()

    def setToolBar(self,wid,shown=None,text=None):
        if wid == "intro":
            if shown is not None:
                self.introable = shown
                self.intro.setVisible(shown)
            if text is not None: self.intro_ = text
        if wid == "tips":
            if shown is not None:
                self.tipsable = shown
                self.tips.setVisible(shown)
            if text is not None: self.tips_ = text
            self.lighting(self.root.settings["theme"])
            self.langing()

    def langing(self):
        self.text.setText(self.root.langer.get(self.text_))
        self.intro.setToolTip(self.root.langer.get(self.intro_))
        self.tips.setToolTip(self.root.langer.get(self.tips_))

    def lighting(self,light):
        if self.introable:
            self.intro.setPixmap(change_color(getPath("src/assets/actions/intro.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
        if self.tipsable:
            self.tips.setPixmap(change_color(getPath("src/assets/actions/tips.png"),QColor(0,0,0)if light else QColor(255,255,255)).pixmap(QSize(20,20)))
