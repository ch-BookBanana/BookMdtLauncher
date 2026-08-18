
from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QScrollBar, QSizePolicy, QSlider, QStackedWidget, QStyle, QStyleOptionComboBox, QStyleOptionSlider, QVBoxLayout

from ..javaScanner import javaScanner
from ..path_utils import getPath

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
                    self.parent.scroll_layout.addWidget(self)
                
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

                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    intr = self.intro.sizePolicy()
                    intr.setRetainSizeWhenHidden(True)
                    self.intro.setSizePolicy(intr)

                    self.tips = QLabel()
                    self.layout.addWidget(self.tips)
                    self.tips.hide()
                    self.tips.setFixedSize(20,20)

                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    tip = self.tips.sizePolicy()
                    tip.setRetainSizeWhenHidden(True)
                    self.tips.setSizePolicy(intr)

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

            class Line(QWidget):
                def __init__(self,parent=None,root=None,text=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_wid()
                    self.parent.scroll_layout.addWidget(self)
                
                def init_wid(self):
                    self.setFixedHeight(1)
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(10, 0, 10, 0)
                    self.line = QWidget()
                    self.line.setProperty("wid","line")

            class Title(QWidget):
                def __init__(self,parent=None,root=None,text=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.text_ = text
                    self.init_wid()
                    self.parent.scroll_layout.addSpacing(30)
                    self.parent.scroll_layout.addWidget(self)
                
                def init_wid(self):
                    self.setFixedHeight(40)
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(15)

                    self.l1 = QWidget()
                    self.l1.setProperty("wid","line")
                    self.l1.setFixedHeight(1)
                    self.layout.addWidget(self.l1,1)

                    self.text = QLabel()
                    self.text.setProperty("wid","text")
                    self.text.setStyleSheet("font-size: 22px;")
                    self.langing()
                    self.layout.addWidget(self.text,0)
                    
                    self.l2 = QWidget()
                    self.l2.setProperty("wid","line")
                    self.l2.setFixedHeight(1)
                    self.layout.addWidget(self.l2,1)

                def langing(self):
                    self.text.setText(self.root.langer.get(self.text_))

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
                    self.parent.scroll_layout.addWidget(self)

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
                                handle_rect = self._get_handle_rect()
                                self.setValue(self._pos_to_value(event.pos()))
                                self.sliderPressed.emit()
                                self.sliderMoved.emit(self.value())
                                event.accept()
                            else: super().mousePressEvent(event)

                        def mouseMoveEvent(self, event):
                            if event.buttons() & Qt.LeftButton:
                                handle_rect = self._get_handle_rect()
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

                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    intr = self.intro.sizePolicy()
                    intr.setRetainSizeWhenHidden(True)
                    self.intro.setSizePolicy(intr)

                    self.tips = QLabel()
                    self.layout.addWidget(self.tips)
                    self.tips.hide()
                    self.tips.setFixedSize(20,20)

                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    tip = self.tips.sizePolicy()
                    tip.setRetainSizeWhenHidden(True)
                    self.tips.setSizePolicy(intr)
                    
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
                    self.parent.scroll_layout.addWidget(self)
                
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

                    self.intro.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    intr = self.intro.sizePolicy()
                    intr.setRetainSizeWhenHidden(True)
                    self.intro.setSizePolicy(intr)

                    self.tips = QLabel()
                    self.layout.addWidget(self.tips)
                    self.tips.hide()
                    self.tips.setFixedSize(20,20)

                    self.tips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    tip = self.tips.sizePolicy()
                    tip.setRetainSizeWhenHidden(True)
                    self.tips.setSizePolicy(intr)

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
                self._title1 = self.Title(self,self.root,"wid.pages.setting.launcher.preferences")

                self._t1_theme = self.Bool(self,self.root,"wid.pages.setting.launcher.preferences.theme")
                self._t1_theme.btn.setChecked(self.root.settings["theme"])
                self._t1_theme.push.connect(self.root.setTheme)

                self._t1_lang = self.Combo(self,self.root,"wid.pages.setting.launcher.preferences.lang")
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


                self._title2 = self.Title(self,self.root,"wid.pages.setting.launcher.general")


                self._title3 = self.Title(self,self.root,"wid.pages.setting.launcher.java")
                self._t3_select = self.Combo(self,self.root,"wid.pages.setting.launcher.java.select")
                self._t3_select_hasjava = True
                def _t3_select_showEvent(self):
                    self._t3_select.combo.clear()
                    if not self.root.settings["javaPaths"]:
                        self.root.settings["javaPaths"] = javaScanner.getJavas()
                        if not self.root.settings["javaPaths"]:
                            self._t3_select_hasjava = False
                            self._t3_select.combo.addItem(self.root.langer.get("wid.pages.setting.launcher.java.select.none"),"nojava")
                            return
                    else:
                        javas = self.root.settings["javaPaths"]
                        for java in javas:
                            if not javaScanner.isJava(java[0]):
                                javas.remove(java)
                        if not javas:
                            _t3_select_showEvent(self)
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
                try:
                    t3SelecIndex1 = self._t3_select.combo.findData("nojava")
                    t3SelecIndex2 = self._t3_select.combo.findData("auto")
                    if t3SelecIndex1 >= 0:self._t3_select.combo.setItemText(t3SelecIndex1,self.root.langer.get("wid.pages.setting.launcher.java.select.none"))
                    if t3SelecIndex2 >= 0:self._t3_select.combo.setItemText(t3SelecIndex2,self.root.langer.get("wid.pages.setting.launcher.java.select.auto"))
                except : pass
