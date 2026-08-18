
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

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib, json, os, copy, re, time

from PySide6.QtCore import QEvent, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPixmap, QTextOption
from PySide6.QtWidgets import QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QScrollBar, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout
import webbrowser

from src.utils.QDownloader import QDownloader
from src.utils.path_utils import getPath

from ..mdtScanner import mdtScanner
from ..QThTimer import QThTimer
from ..utils import _apply_md_image, change_color, md_to_html, t

from ._init import *

class Download(Page):
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

        def resizeEvent(self, event):
            self.scroll_slider.setGeometry(self.scroll.width() - 5, 0, 5, self.scroll.height())
            self.barShow()
            super().resizeEvent(event)

        def showEvent(self, event):
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

            def lighting(self, light: bool):
                if self.icon_ is not None:
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    logo = change_color(self.icon_, color)
                    pixmap = logo.pixmap(30, 30)

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
            super().__init__(parent)
            self.root = root
            self.init_wid()

        def init_wid(self):
            self.layout = QHBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignLeft)

            self.line = QWidget()
            self.line.setProperty("wid", "line")
            self.line.setAttribute(Qt.WA_StyledBackground, True)
            self.line.setFixedWidth(1)
            self.layout.addWidget(self.line, 0)

            self.stack = QStackedWidget()
            self.layout.addWidget(self.stack, 1)

            self.pages_ = []
            self.btns_ = []


            self.game = self.add_page(self.Game,"wid.pages.download.game", "src/assets/nav/menu.png")

        def add_page(self, page_cls, text=None, icon=None):
            btn = self.parent.left.add_btn(text, icon)
            page_ = page_cls(self, self.root, text, icon)
            self.pages_.append(page_)
            self.btns_.append(btn)
            self.stack.addWidget(page_)
            page_.btn = btn
            btn.clicked.connect(lambda: self.stack.setCurrentWidget(page_))
            if len(self.btns_) == 1:
                btn.click()
            return page_

        class Game(QWidget):
            def __init__(self, parent=None, root=None, text=None, icon=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.text = text
                self.icon = icon
                self.init_wid()

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(10, 10, 10, 10)
                self.layout.setSpacing(0)

                self.top = self.Top(self, self.root)
                self.layout.addWidget(self.top,0)

                self.line = QWidget()
                self.line.setFixedHeight(1)
                self.line.setProperty("wid", "line")
                self.line.setAttribute(Qt.WA_StyledBackground, True)
                self.layout.addWidget(self.line,0)

                self.main = self.Main(self, self.root)
                self.layout.addWidget(self.main, 1)
            
            class Top(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.setFixedHeight(35)  # 30 按钮 + 5 底部横向滑块
                    self.init_wid()

                def init_wid(self):
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)

                    self.scroll = self.HScrollArea(self)
                    self.scroll.setWidgetResizable(True)
                    self.scroll.setFrameShape(QFrame.NoFrame)
                    self.layout.addWidget(self.scroll)

                    self.main = QWidget()
                    self.scroll_layout = QHBoxLayout(self.main)
                    self.scroll_layout.setContentsMargins(0, 0, 0, 0)
                    self.scroll_layout.setSpacing(0)
                    self.scroll_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                    self.scroll.setWidget(self.main)

                    # 自定义横向滚动条：浮在底部 5px，内容超宽才显示
                    self.scroll_slider = QScrollBar(Qt.Horizontal, self.scroll)
                    self.scroll_slider.valueChanged.connect(self.scroll.horizontalScrollBar().setValue)
                    self.scroll.horizontalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                    self.scroll.horizontalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                    self.bthGroup = QButtonGroup(self)

                def add_btn(self, text=None, icon=None, color=True):
                    btn = self.Btns(text, getPath(icon), self, self.root, color)
                    self.scroll_layout.addWidget(btn)
                    self.bthGroup.addButton(btn)
                    self.barShow()
                    return btn

                def barShow(self):
                    self.scroll_slider.setVisible(
                        self.scroll.horizontalScrollBar().maximum() > self.scroll.horizontalScrollBar().minimum()
                    )

                def resizeEvent(self, event):
                    self.scroll_slider.setGeometry(0, self.height() - 5, self.width(), 5)
                    self.barShow()
                    super().resizeEvent(event)

                def showEvent(self, event):
                    super().showEvent(event)
                    self.barShow()

                class HScrollArea(QScrollArea):
                    """横向滚动区域：隐藏原生滚动条，滚轮转为横向，空白处可拖拽"""
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                        self._drag_pos = None
                        self.viewport().installEventFilter(self)

                    def wheelEvent(self, event):
                        delta = event.angleDelta().y()
                        if delta == 0:
                            delta = event.angleDelta().x()
                        bar = self.horizontalScrollBar()
                        bar.setValue(bar.value() - delta)
                        event.accept()

                    def eventFilter(self, obj, event):
                        if obj is self.viewport():
                            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                                self._drag_pos = event.pos()
                            elif event.type() == QEvent.MouseMove and self._drag_pos is not None:
                                bar = self.horizontalScrollBar()
                                bar.setValue(bar.value() - (event.pos().x() - self._drag_pos.x()))
                                self._drag_pos = event.pos()
                                return True
                            elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                                self._drag_pos = None
                        return super().eventFilter(obj, event)

                class Btns(QPushButton):
                    def __init__(self, text=None, icon=None, parent=None, root=None, color=True):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.text_ = text
                        self.icon_ = icon
                        self.colorable = color
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(30)
                        self.setMinimumWidth(100)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid", "lbtn")
                        self.setCheckable(True)

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(5, 0, 5, 0)
                        self.layout.setSpacing(5)

                        self.icon = QLabel()
                        self.icon.setAttribute(Qt.WA_StyledBackground, False)
                        self.icon.setFixedSize(20, 20)
                        self.icon.setScaledContents(False)
                        self.layout.addWidget(self.icon)
                        self.icon.setAlignment(Qt.AlignCenter)

                        self.text = QLabel()
                        self.text.setAttribute(Qt.WA_StyledBackground, False)
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
                            logo = change_color(self.icon_, color) if self.colorable else QIcon(self.icon_)
                            pixmap = logo.pixmap(20, 20)

                            if not pixmap.isNull():
                                smooth_pixmap = pixmap.scaled(
                                    16, 16,
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

            class Main(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_wid()
                    self.btns_[0].click()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignHCenter)

                    # 页面栈（每个 Template 自带滚动 + 按钮栏）
                    self.stack = QStackedWidget()
                    self.layout.addWidget(self.stack, 1)

                    self.pages_ = []
                    self.btns_ = []

                    self.add_page(self.Origin, "wid.pages.download.origin","src/assets/icons/mdt/mdt.png" ,color=False)
                    self.add_page(self.MindustryX, "MindustryX","src/assets/icons/mdt/mdtx.png" ,color=False)
                    self.add_page(self.MindustryARC, "MdtArc","src/assets/icons/mdt/mdtarc.png" ,color=False)

                def add_page(self, page_cls, text=None, icon=None, color=True):
                    btn = self.parent.top.add_btn(text, icon, color=color)
                    page_ = page_cls(self, self.root, text, icon)
                    self.pages_.append(page_)
                    self.btns_.append(btn)
                    self.stack.addWidget(page_)
                    page_.btn = btn
                    btn.clicked.connect(lambda: self.stack.setCurrentWidget(page_))
                    if len(self.btns_) == 1:
                        btn.click()
                    return page_

                # 下载界面游戏本体模板
                class Template(QWidget):
                    def __init__(self, parent=None, root=None, text=None, icon=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.text = text
                        self.data = self._read_cache()
                        self.icon = icon
                        self._searching = False
                        self._action_btns = []
                        self._init_wid()

                    def _init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)

                        # 按钮栏：子类通过 add_action_btn 注册
                        self.action_bar = QWidget()
                        self.action_bar.setFixedHeight(40)
                        self.action_bar_layout = QHBoxLayout(self.action_bar)
                        self.action_bar_layout.setContentsMargins(10, 5, 10, 5)
                        self.action_bar_layout.setSpacing(5)
                        self.action_bar_layout.setAlignment(Qt.AlignLeft)
                        self.layout.addWidget(self.action_bar)

                        # 统一注册搜索按钮（增量/全量），子类无需重复注册
                        self.add_action_btn("wid.pages.download.origin.search", lambda: self.search())
                        self.add_action_btn("wid.pages.download.origin.searchAll", lambda: self.searchAll())
                        self.action_bar_layout.addStretch()

                        self.scroll = QScrollArea(self)
                        self.scroll.setWidgetResizable(True)
                        self.scroll.setFrameShape(QFrame.NoFrame)
                        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                        self.layout.addWidget(self.scroll)

                        self.main = QWidget()
                        self.main.setProperty("wid", "color2")
                        self.main.setAttribute(Qt.WA_StyledBackground, True)
                        self.scroll_layout = QVBoxLayout(self.main)
                        self.scroll_layout.setContentsMargins(30, 20, 30, 20)
                        self.scroll_layout.setSpacing(10)
                        self.scroll_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
                        self.scroll.setWidget(self.main)

                        self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                        self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                        self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                        self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                    def _set_searching(self, disabled):
                        self._searching = disabled
                        for btn in self._action_btns:
                            btn.setDisabled(disabled)

                    def add_action_btn(self, text_key, callback):
                        btn = QPushButton(self.root.langer.get(text_key))
                        btn.setFixedSize(100, 30)
                        btn.setProperty("wid", "btn")
                        btn.setAttribute(Qt.WA_StyledBackground, False)
                        btn._text_key = text_key
                        btn.clicked.connect(callback)
                        self._action_btns.append(btn)
                        self.action_bar_layout.addWidget(btn)
                        return btn

                    def langing(self):
                        for btn in self._action_btns:
                            if hasattr(btn, '_text_key'):
                                btn.setText(self.root.langer.get(btn._text_key))

                    def barShow(self):
                        self.scroll_slider.setVisible(
                            self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum()
                        )

                    def _clear_scroll_stretch(self):
                        i = 0
                        while i < self.scroll_layout.count():
                            it = self.scroll_layout.itemAt(i)
                            if it is not None and it.spacerItem() is not None:
                                self.scroll_layout.takeAt(i)
                                continue
                            i += 1

                    def resizeEvent(self, event):
                        self.scroll_slider.setGeometry(
                            self.scroll.width() - 5, 0, 5, self.scroll.height()
                        )
                        self.barShow()
                        super().resizeEvent(event)

                    def showEvent(self, event):
                        super().showEvent(event)
                        self.barShow()

                    def _read_cache(self):
                        if not hasattr(self, 'tmpPath') or self.tmpPath is None:
                            return {"intro": "", "versions": {}}
                        if os.path.exists(self.tmpPath):
                            try:
                                with open(self.tmpPath, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                    if isinstance(data, dict):
                                        data.setdefault("intro", "")
                                        data.setdefault("versions", {})
                                        return data
                            except (json.JSONDecodeError, OSError):
                                pass
                        return {"intro": "", "versions": {}}

                    def _write_cache(self, data):
                        if not hasattr(self, 'tmpPath') or self.tmpPath is None:
                            return
                        os.makedirs(os.path.dirname(self.tmpPath), exist_ok=True)
                        with open(self.tmpPath, "w", encoding="utf-8") as f:
                            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)

                    @staticmethod
                    def _normalize_class(category):
                        if category is None:
                            return None
                        if isinstance(category, str):
                            category = category.strip()
                            if category.startswith('v') and len(category) > 1:
                                return category
                            try:
                                return 'v' + str(int(float(category)))
                            except Exception:
                                return category
                        try:
                            return 'v' + str(int(float(category)))
                        except Exception:
                            return None

                    @staticmethod
                    def _sort_versions(versions):
                        def _key(k):
                            if not isinstance(k, str):
                                return float(k) if isinstance(k, (int, float)) else 0.0
                            m = re.match(r'v?(\d+(?:\.\d+)*)', k)
                            if m:
                                try:
                                    return float(m.group(1))
                                except Exception:
                                    return 0.0
                            return 0.0

                        def _ver_key(k):
                            # 版本号转可比较元组，兼容多段版本（如 146.1.0.0.0）
                            s = str(k)
                            m = re.match(r'^(\d+)(?:\.(\d+))*$', s)
                            if m:
                                try:
                                    return tuple(int(p) for p in m.groups() if p is not None)
                                except ValueError:
                                    return (0,)
                            return (0,)

                        out = {}
                        for cls_key in sorted(versions.keys(), key=_key, reverse=True):
                            out[cls_key] = {
                                n: versions[cls_key][n]
                                for n in sorted(versions[cls_key].keys(), key=_ver_key, reverse=True)
                            }
                        return out

                    def _fetch_and_merge(self, pages, per_page, cache):
                        api = self.root.githubAPI
                        releases_all = []
                        max_workers = min(len(pages) + 1, 8)

                        with ThreadPoolExecutor(max_workers=max_workers) as pool:
                            futures = {
                                pool.submit(api.getRelease, self.releaseRepo, p, per_page): p
                                for p in pages
                            }
                            f_intro = pool.submit(self.root.githubAPI._session.get, self.introUrl, timeout=15) if self.introUrl else None

                            for f in as_completed(futures):
                                try:
                                    ok, data = f.result()
                                    if ok and isinstance(data, list):
                                        releases_all.extend(data)
                                    else:
                                        self.root.logger.warning(f"[{type(self).__name__}._fetch_and_merge] release page failed: {data}")
                                except Exception as e:
                                    self.root.logger.error(f"[{type(self).__name__}._fetch_and_merge] release future exception: {e}")

                            intro_resp = None
                            if f_intro is not None:
                                try:
                                    intro_resp = f_intro.result()
                                except Exception as e:
                                    self.root.logger.warning(f"[{type(self).__name__}._fetch_and_merge] intro fetch failed: {e}")

                        for r in releases_all:
                            try:
                                d = self.classify(r)
                            except Exception as e:
                                self.root.logger.error(f"[{type(self).__name__}.classify] {e}")
                                continue
                            category = self._normalize_class(d.get('class'))
                            if category is None or d.get('name') is None:
                                continue
                            cache["versions"].setdefault(category, {})[d["name"]] = d

                        cache["intro"] = cache.get("intro", "")
                        if intro_resp is not None and getattr(intro_resp, 'status_code', None) == 200:
                            cache["intro"] = intro_resp.text

                        cache["versions"] = self._sort_versions(cache["versions"])
                        self._write_cache(cache)
                        return cache

                    def _before_search(self):
                        pass

                    def _on_data_changed(self):
                        pass

                    def _search(self, job, on_done):
                        if self._searching:
                            return
                        self._before_search()
                        self._set_searching(True)
                        safety = QTimer(self)
                        safety.setSingleShot(True)
                        safety.timeout.connect(lambda: self._set_searching(False))
                        safety.start(30000)

                        def _on_done(result):
                            if safety.isActive():
                                safety.stop()
                            on_done(result)

                        QThTimer.task(0, job, result_callback=_on_done, dedicated=True)

                    def search(self):
                        def job(event):
                            cache = self._read_cache()
                            return self._fetch_and_merge([1], 50, cache)

                        def on_done(result):
                            self._set_searching(False)
                            if not isinstance(result, Exception) and isinstance(result, dict):
                                self.data = result
                                self._on_data_changed()
                            elif isinstance(result, Exception):
                                self.root.logger.error(f"[{type(self).__name__}.search] {result}")

                        self._search(job, on_done)

                    def searchAll(self):
                        def job(event):
                            api = self.root.githubAPI
                            cache = self._read_cache()
                            per_page = 100
                            pages = [1]

                            ok, first_page = api.getRelease(self.releaseRepo, 1, per_page)
                            if not ok or not isinstance(first_page, list):
                                return cache

                            releases = first_page
                            if len(first_page) == per_page:
                                current_page = 2
                                while current_page <= 10:
                                    ok, next_page = api.getRelease(self.releaseRepo, current_page, per_page)
                                    if not ok or not isinstance(next_page, list) or len(next_page) == 0:
                                        break
                                    releases.extend(next_page)
                                    pages.append(current_page)
                                    if len(next_page) < per_page:
                                        break
                                    current_page += 1
                            return self._fetch_and_merge(pages, per_page, cache)

                        def on_done(result):
                            self._set_searching(False)
                            if not isinstance(result, Exception) and isinstance(result, dict):
                                self.data = result
                                self._on_data_changed()
                            elif isinstance(result, Exception):
                                self.root.logger.error(f"[{type(self).__name__}.searchAll] {result}")

                        self._search(job, on_done)

                    def classify(self, back):
                        raise NotImplementedError("Subclass must implement classify()")

                    class Classs(QWidget):
                        def __init__(self,parent=None,root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.light = None
                            self.data = {}
                            self.btnPix = [QPixmap(),QPixmap()]
                            self.setAttribute(Qt.WA_StyledBackground, True)

                            self.setStyleSheet('QWidget[wid_="download.game.classs"]{border-radius:10px;}')
                            self.setProperty("wid_","download.game.classs")
                            self.setMaximumWidth(600)
                            self.init_wid()

                        def sizeHint(self):
                            h = super().sizeHint().height()
                            if h < 0 and self.layout() is not None:
                                h = self.layout().totalSizeHint().height()
                            return QSize(600, h)

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(10,10,10,10)
                            self.layout.setSpacing(5)

                            self.top = QWidget()
                            self.top.setFixedHeight(40)
                            self.layout.addWidget(self.top)

                            self.topL = QHBoxLayout(self.top)
                            self.topL.setContentsMargins(15,0,0,0)
                            self.topL.setSpacing(5)
                            self.topL.setAlignment(Qt.AlignLeft | Qt.AlignBottom)

                            self.label = QLabel()
                            self.label.setProperty("wid","text")
                            self.label.setStyleSheet("font-size:16px;")
                            self.topL.addWidget(self.label,0)

                            self.label2 = QLabel()
                            self.label2.setProperty("wid","lbtn")
                            self.label2.setStyleSheet("font-size:14px;")
                            self.topL.addWidget(self.label2,0)

                            self.topL.addStretch(1)

                            self.button = QPushButton()
                            self.button.setFixedSize(40,40)
                            self.button.setProperty("wid","lbtn")
                            self.button.setStyleSheet("border-radius:20px;")
                            self.topL.addWidget(self.button)

                            class VisiWidget(QWidget):
                                visibled = Signal(bool)

                                def showEvent(self,event):
                                    self.visibled.emit(True)
                                    super().showEvent(event)

                                def hideEvent(self,event):
                                    self.visibled.emit(False)
                                    super().hideEvent(event)

                            self.contentW = VisiWidget()
                            self.contentW.visibled.connect(lambda i:self.button.setIcon(QIcon(self.btnPix[int(i)])))
                            self.layout.addWidget(self.contentW)
                            self.contentW.hide()

                            self.contentL = QVBoxLayout(self.contentW)
                            self.contentL.setContentsMargins(0,0,0,0)
                            self.contentL.setSpacing(5)

                            self.line = QWidget()
                            self.line.setFixedHeight(1)
                            self.line.setProperty("wid","line")
                            self.contentL.addWidget(self.line)

                            self.scroll = self.parent.Scroll(self,self.root)
                            self.contentL.addWidget(self.scroll,0)
                            self.lighting(self.root.settings["theme"])

                            self.button.clicked.connect(lambda:self.contentW.setVisible(not self.contentW.isVisible()))
                        
                        def setData(self,name,data,icon_pixmap=None):
                            self.data = copy.deepcopy(data)
                            self.label.setText(name+" ("+str(len(self.data))+")")
                            self.scroll.setFixedHeight(min(400, len(self.data)*60-10))
                            self.scroll.setData(self.data, icon_pixmap)

                        def langing(self):
                            pass

                        def lighting(self,light):
                            if self.light != light:
                                self.light = light
                                self.btnPix[1] = change_color(getPath("src/assets/actions/eye.png"),QColor(25,25,25) if light else QColor(220,220,220))
                                self.btnPix[0] = change_color(getPath("src/assets/actions/eye-off.png"),QColor(25,25,25) if light else QColor(220,220,220))
                            self.button.setIcon(QIcon(self.btnPix[int(self.contentW.isVisible())]))

                        def showEvent(self,event):
                            super().showEvent(event)
                            self.scroll.setFixedHeight(min(400, len(self.data)*60-10))

                    class Scroll(QWidget):
                        def __init__(self,parent=None,root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            # 上层模板（Classs.parent 即 Template 子类），供 Item 引用 RepoInfo 等嵌套类
                            self.template = self.parent.parent if self.parent is not None else None
                            self.itemd = {}   # 数据列表
                            self.itemw = []   # 可视化复用item池
                            self.item_h = 50
                            self.viewport_h = 0
                            self.total_count = 0
                            self.start_index = 0
                            self.init_wid()
                            self._update_visible()
                            self._app_state_conn = None
                            _app = QApplication.instance()
                            if _app is not None:
                                self._app_state_conn = _app.applicationStateChanged.connect(self._on_app_state_changed)

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(10)

                            self.scroll = QScrollArea(self)
                            self.scroll.setWidgetResizable(True)
                            self.scroll.setFrameShape(QFrame.NoFrame)
                            # 滚动时：1) 刷新 item 池内容 2) 刷新悬停状态
                            self.scroll.verticalScrollBar().valueChanged.connect(self._update_visible)
                            self.scroll.verticalScrollBar().valueChanged.connect(self._check_all_hover)
                            self.layout.addWidget(self.scroll)

                            self.main = QWidget()
                            self.main.setMinimumWidth(0)
                            self.scroll.setWidget(self.main)

                            self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                            self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                            self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                            self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                            # 空数据提示：铺满整个滚动区，无条目时显示
                            self.empty_label = QLabel(self)
                            self.empty_label.setAlignment(Qt.AlignCenter)
                            self.empty_label.setProperty("wid", "title")
                            self.empty_label.setStyleSheet("font-size:16px;")
                            self.empty_label.setText(self.root.langer.get("wid.pages.download.empty"))
                            self.empty_label.hide()

                        def setData(self, data: dict, icon_pixmap=None):
                            self.itemd.clear()
                            self.item_icon_pixmap = icon_pixmap
                            for idx, (name, item) in enumerate(data.items()):
                                item["name"] = name
                                self.itemd[idx] = item
                            self.total_count = len(data)
                            self.main.setFixedHeight(self.total_count * self.item_h)
                            if self.total_count == 0:
                                self.empty_label.show()
                                self.empty_label.raise_()
                            else:
                                self.empty_label.hide()
                            self._update_visible()

                        def resizeEvent(self, event):
                            self.scroll_slider.setGeometry(
                                self.scroll.width() - 5, 0, 5, self.scroll.height()
                            )
                            self.empty_label.setGeometry(0, 0, self.width(), self.height())
                            super().resizeEvent(event)
                            self.viewport_h = self.height()
                            visible = int((self.viewport_h + self.item_h - 1) / self.item_h) + 2
                            while len(self.itemw) < visible:
                                it = self.Item(self.main, self.root, self.template)
                                it.setParent(self.main)
                                it.hide()
                                self.itemw.append(it)
                            while len(self.itemw) > visible:
                                it = self.itemw.pop()
                                it.setParent(None)
                                it.deleteLater()
                            self.main.setMinimumHeight(self.total_count * self.item_h)
                            self._update_visible()

                        def showEvent(self, event):
                            super().showEvent(event)
                            self.scroll_slider.setVisible(
                                self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum()
                            )
                            self._update_visible()

                        def _check_all_hover(self):
                            for w in self.itemw:
                                w.check_hover()

                        def _on_app_state_changed(self, state):
                            self._check_all_hover()

                        def deleteLater(self):
                            conn = getattr(self, '_app_state_conn', None)
                            if conn is not None:
                                try:
                                    QApplication.instance().applicationStateChanged.disconnect(conn)
                                except Exception:
                                    pass
                                self._app_state_conn = None
                            super().deleteLater()

                        def _update_visible(self):
                            if self.total_count == 0:
                                for w in self.itemw:
                                    w.hide()
                                return
                            if not self.itemw:
                                self.viewport_h = self.scroll.viewport().height()
                                if self.viewport_h <= 0:
                                    self.viewport_h = 400
                                visible = max(1, int(self.viewport_h / self.item_h)) + 1
                                for _ in range(visible):
                                    it = self.Item(self.main, self.root, self.template)
                                    it.setParent(self.main)
                                    it.hide()
                                    self.itemw.append(it)
                            vbar = self.scroll.verticalScrollBar()
                            scroll_y = vbar.value()
                            first = int(scroll_y / self.item_h)
                            if first < 0:
                                first = 0
                            self.start_index = first
                            for i, widget in enumerate(self.itemw):
                                idx = self.start_index + i
                                if idx >= self.total_count:
                                    widget.hide()
                                    continue
                                data = self.itemd.get(idx)
                                if data is None:
                                    widget.hide()
                                    continue
                                widget.set_data(data, getattr(self, 'item_icon_pixmap', None))
                                widget.lighting(bool(self.root.settings.get("theme")))
                                widget.check_hover()
                                y = idx * self.item_h
                                widget.setGeometry(0, y, self.scroll.viewport().width(), self.item_h)
                                widget.show()

                        class Item(QWidget):
                            def __init__(self,parent=None,root=None,template=None):
                                super().__init__(parent)
                                self.parent = parent
                                self.root = root
                                self.template = template
                                if self.template is None:
                                    # 兜底：沿父链查找包含 RepoInfo 的模板
                                    w = self.parent
                                    while w is not None:
                                        if hasattr(w, "RepoInfo"):
                                            self.template = w
                                            break
                                        w = w.parent()
                                self.data={}
                                self.light = None
                                self._hovering = False
                                self.pixmap = QPixmap()
                                self.setFixedHeight(50)
                                self.setMouseTracking(True)
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.setObjectName("item")
                                self.init_wid()

                            def set_data(self, data: dict, icon_pixmap=None):
                                self.data = data or {}
                                title = self.data.get("title") or self.data.get("name") or ""
                                time = self.data.get("time") or ""
                                self.title.setText(title)
                                self.time.setText(time)
                                self.pixmap = icon_pixmap or QPixmap()
                                # pre-computed pixmap passed from outside
                                if icon_pixmap and not icon_pixmap.isNull():
                                    self.icon.setPixmap(icon_pixmap.scaled(30,30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                else:
                                    self.icon.clear()

                            class RBtn(QPushButton):
                                def __init__(self, icon_path, tooltip_key, parent=None, root=None):
                                    super().__init__(parent)
                                    self.parent = parent
                                    self.root = root
                                    self._icon_path = icon_path
                                    self._tooltip_key = tooltip_key
                                    self._is_show = True   # 悬浮 Item 时是否显示该按钮
                                    self.init_ui()

                                def init_ui(self):
                                    self.setFixedSize(20, 20)
                                    self.setProperty("wid", "lbtn")
                                    # 开启 QSS 背景，让 lbtn:hover 的悬停背景生效
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.hide()
                                    self.langing()

                                def langing(self):
                                    self.setToolTip(self.root.langer.get(self._tooltip_key))

                                def lighting(self, light: bool):
                                    color = QColor(0, 0, 0) if light else QColor(255, 255, 255)
                                    icon = change_color(self._icon_path, color)
                                    pixmap = icon.pixmap(20, 20)
                                    if not pixmap.isNull():
                                        smooth_pixmap = pixmap.scaled(
                                            18, 18,
                                            Qt.KeepAspectRatio,
                                            Qt.FastTransformation
                                        )
                                        self.setIcon(QIcon(smooth_pixmap))
                                    else:
                                        self.root.logger.warning(f"Failed to load pixmap for {self._icon_path}")

                            def init_wid(self):
                                self.layout = QHBoxLayout(self)
                                self.layout.setContentsMargins(10, 0, 10, 0)
                                self.layout.setSpacing(0)
                                self.layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                                self.icon = QLabel()
                                self.icon.setFixedSize(30,30)
                                self.layout.addWidget(self.icon,0)

                                self.layout.addSpacing(10)

                                self.l1w = QWidget()
                                self.l1w.setStyleSheet("background:transparent")
                                self.layout.addWidget(self.l1w,1)
                                self.l1 = QVBoxLayout(self.l1w)
                                self.l1.setContentsMargins(0, 0, 0, 0)
                                self.l1.setSpacing(0)

                                self.title = QLabel()
                                self.title.setProperty("wid","text")
                                self.title.setStyleSheet("font-size:16px;")
                                self.title.setFixedHeight(30)
                                self.l1.addWidget(self.title,0)

                                self.time = QLabel()
                                self.time.setProperty("wid","title")
                                self.time.setFixedHeight(20)
                                self.l1.addWidget(self.time,0)

                                self.layout.addStretch(1)

                                # right-side action buttons
                                self.btn_download = self.RBtn(getPath("src/assets/buttons/download.png"), "wid.pages.download.item.download", self, self.root)
                                self.layout.addWidget(self.btn_download, 0)
                                self.btn_download.clicked.connect(lambda:self.root.window.floatingStack.add_page(self.template.Download(self,self.root,self.data,self.pixmap)))

                                self.btn_repoInfo = self.RBtn(getPath("src/assets/nav/menu.png"), "wid.pages.download.item.repoInfo", self, self.root)
                                self.layout.addWidget(self.btn_repoInfo, 0)
                                self.btn_repoInfo.clicked.connect(lambda:self.root.window.floatingStack.add_page(self.template.RepoInfo(self,self.root,self.data,self.pixmap)))
                                
                                self.btn_link = self.RBtn(getPath("src/assets/nav/link.png"), "wid.pages.download.item.link", self, self.root)
                                self.layout.addWidget(self.btn_link, 0)
                                self.btn_link.clicked.connect(self.open_release)

                                self._action_btns = [self.btn_download, self.btn_repoInfo, self.btn_link]

                            def open_release(self):
                                url = self.data.get("releaseUrl") or ""
                                if url:
                                    webbrowser.open(url)
                                else:
                                    self.root.logger.warning("Item has no releaseUrl to open")

                            def set_hover(self, hover):
                                if self._hovering != hover:
                                    self._hovering = hover
                                    # 悬停时应用高亮背景，移开恢复（内联样式保证 QWidget 子类背景生效）
                                    light = bool(self.root.settings.get("theme"))
                                    bg = "rgb(229, 228, 228)" if light else "rgb(55, 55, 55)"
                                    self.setStyleSheet(
                                        "QWidget#item { background: %s; }" % bg if hover else ""
                                    )
                                    self._update_btns()

                            def _update_btns(self):
                                for btn in self._action_btns:
                                    btn.setVisible(self._hovering and getattr(btn, '_is_show', True))

                            def check_hover(self):
                                if self.isVisible():
                                    pos = self.mapFromGlobal(QCursor.pos())
                                    self.set_hover(self.rect().contains(pos))
                                else:
                                    self.set_hover(False)

                            def enterEvent(self, event):
                                self.set_hover(True)
                                super().enterEvent(event)

                            def leaveEvent(self, event):
                                # 鼠标移到子按钮上时 Item 也会收到 Leave，
                                # 但不能直接取消悬停，需按全局位置判断是否真的离开 Item
                                self.check_hover()
                                super().leaveEvent(event)

                            def mouseMoveEvent(self, event):
                                self.check_hover()
                                super().mouseMoveEvent(event)

                            def lighting(self, light: bool):
                                if self.light == light:
                                    return
                                self.light = light
                                for btn in self._action_btns:
                                    btn.lighting(light)

                    class Download(QWidget):
                        def __init__(self, parent=None, root=None, data=None, pixmap=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.data = data
                            self.pixmap = pixmap
                            self._final_name = None
                            self._validate_key = None
                            self._closed = False
                            self._dl_timer = None
                            self._task_list = []
                            self.setAttribute(Qt.WA_StyledBackground, True)
                            self.setProperty("wid","color2")
                            self.init_wid()
                            self.langing()
                            self.lighting(bool(self.root.settings.get("theme")))
                            self._init_name_input()
                            self._start_validation()

                        def init_wid(self):
                            self.lay = QVBoxLayout(self)
                            self.lay.setSpacing(0)
                            self.lay.setContentsMargins(0, 0, 0, 0)
                            self.lay.setAlignment(Qt.AlignCenter)

                            self.main = QWidget()
                            self.main.setAttribute(Qt.WA_StyledBackground, True)
                            self.main.setFixedSize(400, 300)
                            self.lay.addWidget(self.main,0)

                            self.layout = QVBoxLayout(self.main)
                            self.layout.setSpacing(0)
                            self.layout.setContentsMargins(15, 15, 15, 15)
                            self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)


                            self.h1 = QWidget()
                            self.h1.setStyleSheet("background: transparent")
                            self.layout.addWidget(self.h1, 0)
                            self.h1_layout = QHBoxLayout(self.h1)
                            self.h1_layout.setContentsMargins(0, 0, 0, 0)
                            self.h1_layout.setSpacing(15)
                            self.h1_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                            self.icon = QLabel()
                            self.icon.setFixedSize(48, 48)
                            self.h1_layout.addWidget(self.icon, 0)

                            self.h1w = QWidget()
                            self.h1w.setStyleSheet("background: transparent")
                            self.h1_layout.addWidget(self.h1w, 1)
                            self.h1w_layout = QVBoxLayout(self.h1w)
                            self.h1w_layout.setContentsMargins(0, 0, 0, 0)
                            self.h1w_layout.setSpacing(4)
                            self.h1w_layout.setAlignment(Qt.AlignVCenter)

                            self.title = QLabel(self.data.get("title") or self.data.get("name") or "")
                            self.title.setProperty("wid", "text")
                            self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
                            self.title.setWordWrap(True)
                            self.h1w_layout.addWidget(self.title, 0)

                            self.time = QLabel()
                            self.time.setProperty("wid", "title")
                            self.time.setStyleSheet("font-size: 13px;")
                            self.h1w_layout.addWidget(self.time, 0)


                            self.layout.addSpacing(15)


                            self.line = QWidget()
                            self.line.setProperty("wid", "line")
                            self.line.setFixedHeight(1)
                            self.layout.addWidget(self.line, 0)

                            self.layout.addStretch(1)

                            self.label = QLabel()
                            self.label.setFixedHeight(40)
                            self.label.setStyleSheet("font-size: 18px;")
                            self.label.setProperty("wid", "text")
                            self.layout.addWidget(self.label, 0)

                            # 名称输入框：默认 "界面名-版本"（自动去重 (1)(2)...）
                            self.input = QLineEdit()
                            self.input.setProperty("wid", "input")
                            self.input.setFixedHeight(32)
                            self.input.setClearButtonEnabled(True)
                            self.layout.addWidget(self.input, 0)

                            self.layout.addSpacing(6)

                            # 提示标签 + 确定按钮一行
                            self.bottom = QWidget()
                            self.bottom.setStyleSheet("background: transparent")
                            self.layout.addWidget(self.bottom, 0)
                            self.bottom_layout = QHBoxLayout(self.bottom)
                            self.bottom_layout.setContentsMargins(0, 0, 0, 0)
                            self.bottom_layout.setSpacing(8)
                            self.bottom_layout.setAlignment(Qt.AlignVCenter)

                            self.label2 = QLabel()
                            self.label2.setProperty("wid", "text")
                            self.label2.setStyleSheet("font-size: 13px;")
                            self.label2.setWordWrap(True)
                            self.bottom_layout.addWidget(self.label2, 1)

                            self.btn_ok = QPushButton()
                            self.btn_ok.setProperty("wid", "btn")
                            self.btn_ok.setFixedSize(80, 30)
                            self.btn_ok.setEnabled(False)
                            self.btn_ok.setStyleSheet("background-color: rgba(240, 183, 49, 100); border: none;")
                            self.btn_ok.clicked.connect(self._on_ok)
                            self.bottom_layout.addWidget(self.btn_ok, 0)

                            self.layout.addStretch(1)

                        def langing(self):
                            time_str = (self.data or {}).get("time") or ""
                            self.time.setText(t(self.root.langer.get("wid.pages.download.item.repoInfo.publish"), time_str))
                            self.label.setText(self.root.langer.get("wid.pages.download"))
                            self.btn_ok.setText(self.root.langer.get("text.yes"))
                        
                        def lighting(self, light):
                            if self.pixmap is not None and not self.pixmap.isNull():
                                self.icon.setPixmap(self.pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            else:
                                self.icon.clear()

                        # ---------- 名称默认值与去重 ----------
                        @staticmethod
                        def _unique_name(name, existing):
                            if name not in existing:
                                return name
                            i = 1
                            while "%s(%d)" % (name, i) in existing:
                                i += 1
                            return "%s(%d)" % (name, i)

                        def _init_name_input(self):
                            template = getattr(self.parent, "template", None)
                            interface_name = ""
                            if template is not None:
                                interface_name = self.root.langer.get(getattr(template, "text", "")) or ""
                            base = interface_name + "-" + (self.data.get("name") or "")
                            existing = set(mdtScanner.getMdts())
                            existing |= set((mdtScanner.getDownloadingMdts() or {}).keys())
                            self.input.setText(self._unique_name(base, existing))
                            self.input.textChanged.connect(self._on_text_changed)

                        # ---------- 名称校验：子线程收集 / 主线程应用 ----------
                        def _collect_mdts(self, event):
                            """子线程：收集已安装/下载中的游戏名列表（纯文件/缓存操作，线程安全）。"""
                            try:
                                mdts = set(mdtScanner.getMdts())
                                downloading = set((mdtScanner.getDownloadingMdts() or {}).keys())
                                return {"mdts": mdts, "downloading": downloading}
                            except Exception as e:
                                return e

                        def _start_validation(self):
                            # 周期检测：覆盖下载中任务的新建/完成/失败变化
                            self._dl_timer = QThTimer.taskP(1000, self._collect_mdts, result_callback=self._apply_validation)

                        def _stop_validation(self):
                            try:
                                t = getattr(self, "_dl_timer", None)
                                if t is not None:
                                    t.destroy()
                                    self._dl_timer = None
                            except Exception:
                                pass

                        def on_close(self):
                            """FloatingStack 出栈时同步调用：停止周期检测，防止对已销毁对象回调。"""
                            self._closed = True
                            self._stop_validation()

                        def _on_text_changed(self, text):
                            # 文字变化：立即单次检测（QThTimer.task）
                            if self._closed:
                                return
                            try:
                                timer = QThTimer.task(0, self._collect_mdts, result_callback=self._apply_validation)
                                self._task_list.append(timer)
                                timer.finished.connect(lambda: self._discard_task(timer))
                            except Exception:
                                pass

                        def _discard_task(self, timer):
                            try:
                                if timer in self._task_list:
                                    self._task_list.remove(timer)
                            except Exception:
                                pass

                        def _apply_validation(self, result):
                            if self._closed or isinstance(result, Exception):
                                return
                            text = self.input.text().strip()
                            existing = result["mdts"] | result["downloading"]
                            if not text:
                                state, final, msg = "empty", None, ""
                            elif re.search(r'[\\/:*?"<>|]', text):
                                state, final, msg = "illegal", None, self.root.langer.get("wid.pages.download.item.name.illegal")
                            elif text.startswith("."):
                                state, final, msg = "dot", None, self.root.langer.get("wid.pages.download.item.name.dot")
                            elif text in existing:
                                unique = self._unique_name(text, existing)
                                state, final, msg = "dup", unique, t(self.root.langer.get("wid.pages.download.item.name.willBe"), unique)
                            else:
                                state, final, msg = "ok", text, ""
                            self._final_name = final
                            key = (state, msg)
                            if key == self._validate_key:
                                return
                            self._validate_key = key
                            if state in ("illegal", "dot"):
                                self.input.setStyleSheet("border: 1px solid red;")
                                self.label2.setStyleSheet("font-size: 13px; color: red;")
                                self.label2.setText(msg)
                                self.btn_ok.setEnabled(False)
                                self.btn_ok.setStyleSheet("background-color: rgba(240, 183, 49, 100); border: none;")
                            elif state == "dup":
                                self.input.setStyleSheet("border: 1px solid yellow;")
                                self.label2.setStyleSheet("font-size: 13px; color: yellow;")
                                self.label2.setText(msg)
                                self.btn_ok.setEnabled(True)
                                self.btn_ok.setStyleSheet("background-color: #f0b731; border: none;")
                            elif state == "empty":
                                self.input.setStyleSheet("")
                                self.label2.setStyleSheet("font-size: 13px;")
                                self.label2.setText("")
                                self.btn_ok.setEnabled(False)
                                self.btn_ok.setStyleSheet("background-color: rgba(240, 183, 49, 100); border: none;")
                            else:
                                self.input.setStyleSheet("")
                                self.label2.setStyleSheet("font-size: 13px;")
                                self.label2.setText("")
                                self.btn_ok.setEnabled(True)
                                self.btn_ok.setStyleSheet("background-color: #f0b731; border: none;")

                        # ---------- 确定：创建下载任务 ----------
                        def _on_ok(self):
                            name = self._final_name
                            if not name:
                                return
                            url = self.data.get("gameLinear") or ""
                            if not url:
                                for a in (self.data.get("assets") or {}).values():
                                    url = a.get("linear") or ""
                                    if url:
                                        break
                            if not url:
                                self.label2.setStyleSheet("font-size: 13px; color: red;")
                                self.label2.setText(self.root.langer.get("wid.pages.download.item.name.noUrl"))
                                return
                            target_dir = getPath("BML/.Mindustrys/" + name)
                            try:
                                os.makedirs(target_dir, exist_ok=True)
                            except OSError as e:
                                self.root.logger.error("[mdt-download] 创建目录失败: %s" % e)
                                return
                            dest_path = os.path.join(target_dir, "mdt.jar")
                            # appdataCopy：仅原版（Anuken/Mindustry）且版本号早于 126（不含 126）时置 True
                            # （v126 起才支持 MINDUSTRY_DATA_DIR，更早版本数据目录会落在系统 AppData）
                            _appdata_copy = False
                            _tpl = getattr(self.parent, "template", None)
                            if getattr(_tpl, "releaseRepo", None) == "Anuken/Mindustry":
                                _ver_m = re.match(r'^(\d+)', str(self.data.get("name") or ""))
                                _appdata_copy = bool(_ver_m and int(_ver_m.group(1)) < 126)
                            info = {
                                "id": hashlib.md5(dest_path.encode("utf-8")).hexdigest()[:8],
                                "name": name,
                                "repo": getattr(_tpl, "releaseRepo", None),
                                "icon_path": getattr(_tpl, "icon", None),
                                "title": name,
                                "time": self.data.get("time"),
                                "url": url,
                                "dest": dest_path,
                                "created_at": int(time.time()),
                                "appdataCopy": _appdata_copy,
                            }
                            try:
                                with open(os.path.join(target_dir, "downloading.json"), "w", encoding="utf-8") as f:
                                    json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                            except OSError as e:
                                self.root.logger.error("[mdt-download] 写入 downloading.json 失败: %s" % e)
                                return
                            try:
                                dl = QDownloader(url=url, dest_path=dest_path, num_threads=4, chunk_size_mb=4, title=name)
                            except Exception as e:
                                self.root.logger.error("[mdt-download] 创建下载任务失败: %s" % e)
                                return
                            if not hasattr(self.root, "_mdt_downloads"):
                                self.root._mdt_downloads = []
                            self.root._mdt_downloads.append(dl)
                            dl.finished.connect(lambda ok, d=dl, n=name: self._on_dl_finished(d, n, ok))
                            dl.error.connect(lambda err, d=dl: self.root.logger.error("[mdt-download:%s] %s" % (getattr(d, "task_id", "?"), err)))
                            dl.start()
                            self.root.logger.info("[mdt-download] 开始下载 %s: %s" % (name, url))
                            # 删除自身，下载在后台由 QDownloader 自行处理
                            self.root.window.floatingStack.pop_page()

                        def _on_dl_finished(self, dl, name, ok):
                            """下载完成收尾：释放 QDownloader；成功后刷新 BML.json 并删除 downloading.json。"""
                            try:
                                dl.wait_thread(5000)
                                dl.deleteLater()
                            except Exception:
                                pass
                            try:
                                if dl in self.root._mdt_downloads:
                                    self.root._mdt_downloads.remove(dl)
                            except Exception:
                                pass
                            if not ok:
                                self.root.logger.error("[mdt-download] %s 下载失败（downloading.json 已保留）" % name)
                                return
                            try:
                                mdtScanner._retrieve_mdt_data(name)
                                dfile = getPath("BML/.Mindustrys/%s/downloading.json" % name)
                                if os.path.isfile(dfile):
                                    # 把下载时记录的类图标路径 / appdataCopy 合并进 BML.json
                                    try:
                                        with open(dfile, "r", encoding="utf-8") as f:
                                            dinfo = json.load(f)
                                        icon_path = dinfo.get("icon_path")
                                        appdata_copy = dinfo.get("appdataCopy")
                                        if icon_path or appdata_copy is not None:
                                            bfile = getPath("BML/.Mindustrys/%s/BML.json" % name)
                                            bdata = {}
                                            if os.path.isfile(bfile):
                                                with open(bfile, "r", encoding="utf-8") as f:
                                                    bdata = json.load(f)
                                            if icon_path:
                                                bdata["icon_path"] = icon_path
                                            if appdata_copy is not None:
                                                bdata["appdataCopy"] = appdata_copy
                                            with open(bfile, "w", encoding="utf-8") as f:
                                                json.dump(bdata, f, ensure_ascii=False, separators=(",", ":"))
                                    except Exception:
                                        pass
                                    os.remove(dfile)
                                mdtScanner.invalidate_cache()
                                self.root.logger.info("[mdt-download] %s 下载完成" % name)
                            except Exception as e:
                                self.root.logger.error("[mdt-download] %s 收尾失败: %s" % (name, e))

                    class RepoInfo(QWidget):
                        mdImageReady = Signal(object, object)

                        def __init__(self, parent=None, root=None, data=None, pixmap=None): 
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.data = data
                            self.pixmap = pixmap
                            self.setObjectName("repoInfo")
                            self.setAttribute(Qt.WA_StyledBackground, True)
                            self.init_wid()
                            self.langing()
                            self.lighting(bool(self.root.settings.get("theme")))

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)
                            self.layout.setAlignment(Qt.AlignTop)

                            # 滚动区域（整体可滚动，隐藏原生滚动条）
                            self.scroll = QScrollArea(self)
                            self.scroll.setWidgetResizable(True)
                            self.scroll.setFrameShape(QFrame.NoFrame)
                            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            self.layout.addWidget(self.scroll, 1)

                            self.main = QWidget()
                            self.main.setObjectName("repoMain")
                            self.main.setAttribute(Qt.WA_StyledBackground, True)
                            # 内容最大宽度 800，超出后在视口中水平居中
                            self.main.setMaximumWidth(800)
                            self.scroll_layout = QVBoxLayout(self.main)
                            self.scroll_layout.setContentsMargins(20, 15, 20, 15)
                            self.scroll_layout.setSpacing(10)
                            self.scroll_layout.setAlignment(Qt.AlignTop)
                            self.scroll.setWidget(self.main)
                            self.scroll.setAlignment(Qt.AlignHCenter)

                            self.scroll_slider = QScrollBar(Qt.Vertical, self.scroll)
                            self.scroll_slider.valueChanged.connect(self.scroll.verticalScrollBar().setValue)
                            self.scroll.verticalScrollBar().rangeChanged.connect(self.scroll_slider.setRange)
                            self.scroll.verticalScrollBar().valueChanged.connect(self.scroll_slider.setValue)

                            data = self.data or {}

                            # ===== 顶部：左图标 + 中间(title / 发布时间) =====
                            self.h1 = QWidget()
                            self.h1.setStyleSheet("background: transparent")
                            self.scroll_layout.addWidget(self.h1, 0)
                            self.h1_layout = QHBoxLayout(self.h1)
                            self.h1_layout.setContentsMargins(0, 0, 0, 0)
                            self.h1_layout.setSpacing(15)
                            self.h1_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                            self.icon = QLabel()
                            self.icon.setFixedSize(48, 48)
                            self.h1_layout.addWidget(self.icon, 0)

                            self.h1w = QWidget()
                            self.h1w.setStyleSheet("background: transparent")
                            self.h1_layout.addWidget(self.h1w, 1)
                            self.h1w_layout = QVBoxLayout(self.h1w)
                            self.h1w_layout.setContentsMargins(0, 0, 0, 0)
                            self.h1w_layout.setSpacing(4)
                            self.h1w_layout.setAlignment(Qt.AlignVCenter)

                            self.title = QLabel(data.get("title") or data.get("name") or "")
                            self.title.setProperty("wid", "text")
                            self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
                            self.title.setWordWrap(True)
                            self.h1w_layout.addWidget(self.title, 0)

                            self.time = QLabel()
                            self.time.setProperty("wid", "title")
                            self.time.setStyleSheet("font-size: 13px;")
                            self.h1w_layout.addWidget(self.time, 0)

                            # ===== 分隔线 =====
                            line1 = QWidget()
                            line1.setProperty("wid", "line")
                            line1.setFixedHeight(1)
                            self.scroll_layout.addWidget(line1, 0)

                            # ===== 定高介绍区（内部可滚动查看全文） =====
                            self.intro_area = QScrollArea(self.main)
                            self.intro_area.setFixedHeight(300)
                            self.intro_area.setWidgetResizable(True)
                            self.intro_area.setFrameShape(QFrame.NoFrame)
                            self.intro_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            self.scroll_layout.addWidget(self.intro_area, 0)

                            self.intro = QTextBrowser()
                            self.intro.setAlignment(Qt.AlignTop)
                            self.intro.setProperty("wid", "text")
                            self.intro.setStyleSheet("font-size: 14px;")
                            self.intro.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
                            self.intro.setTextInteractionFlags(Qt.NoTextInteraction)
                            self.intro.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            self.intro.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            self.intro.document().setDocumentMargin(0)
                            self.intro_area.setWidget(self.intro)

                            # 后台处理 markdown（Qt 原生渲染，含图片缓存），完成后渲染
                            intro_md = data.get("intro") or ""
                            base_url = getattr(getattr(self.parent, "template", None), "introUrl", None)
                            # 图片先全部以占位图显示，后台逐张下载，每成功一张就替换为真实图
                            self._intro_md = ""
                            self._mdimg_pending = {}
                            self._mdimg_flush = None
                            self._intro_loading = QLabel("...")
                            self._intro_loading.setStyleSheet("color: gray; font-size: 14px;")
                            self._intro_loading.setParent(self.intro_area.viewport())
                            self._intro_loading.adjustSize()
                            self._intro_loading.move(0, 0)

                            def _job(event):
                                # 图片下载完成的回调不依赖 QThTimer 的 event（task 一次性任务
                                # 结束后 event 会被自动销毁，下载线程再 emit 会丢失），改用
                                # RepoInfo 自身的 mdImageReady 信号回到主线程。
                                try:
                                    on_image = self.mdImageReady.emit
                                except Exception:
                                    on_image = None
                                return md_to_html(
                                    intro_md,
                                    base_url=base_url,
                                    session=self.root.githubAPI._session if self.root else None,
                                    cache_dir=getPath("BML/.tmp/mdimg"),
                                    on_image=on_image,
                                )

                            def _done(result):
                                try:
                                    if not isinstance(result, str):
                                        result = md_to_html(intro_md)
                                    self._intro_md = result
                                    # _job 已返回 HTML（含图片缓存与 0.2 缩放），直接渲染
                                    self.intro.setHtml(result)
                                    # 竞态兑底：若下载回调先于本结果到达（_flush 已保留 pending），
                                    # 结果就绪后补一次刷新，保证已下载图片一定回填
                                    if getattr(self, "_mdimg_pending", None) and self._mdimg_flush is None:
                                        self._mdimg_flush = QTimer.singleShot(0, _flush_md_images)
                                except Exception:
                                    pass
                                finally:
                                    try:
                                        self._intro_loading.hide()
                                        self._intro_loading.deleteLater()
                                    except Exception:
                                        pass

                            def _on_md_image(full, local):
                                # 主线程（mdImageReady 信号 QueuedConnection 回到主线程）：
                                # 收集已下载图片，同帧合并刷新
                                try:
                                    self._mdimg_pending[full] = local
                                    if self._mdimg_flush is None:
                                        self._mdimg_flush = QTimer.singleShot(0, _flush_md_images)
                                except Exception:
                                    pass

                            # 下载线程通过 mdImageReady 信号触发本回调；绑定到 self 作为
                            # receiver 上下文，保证 QueuedConnection 一定回到主线程
                            self.mdImageReady.connect(_on_md_image, Qt.QueuedConnection)

                            def _flush_md_images():
                                try:
                                    self._mdimg_flush = None
                                    if not self._mdimg_pending:
                                        return
                                    md = getattr(self, "_intro_md", None)
                                    if not md:
                                        # 结果尚未就绪：保留待处理项，等 _done 就绪后补触发
                                        return
                                    pending, self._mdimg_pending = self._mdimg_pending, {}
                                    for full, local in pending.items():
                                        md = _apply_md_image(md, full, local)
                                    self._intro_md = md
                                    self.intro.setHtml(md)
                                except Exception:
                                    pass

                            QThTimer.task(0, _job, result_callback=_done, dedicated=True)

                            # ===== 分隔线 =====
                            line2 = QWidget()
                            line2.setProperty("wid", "line")
                            line2.setFixedHeight(1)
                            self.scroll_layout.addWidget(line2, 0)

                            # ===== 文件列表（item 风格：图标 + 标题 + 下载按钮） =====
                            self.files_w = QWidget()
                            self.files_w.setStyleSheet("background: transparent")
                            self.scroll_layout.addWidget(self.files_w, 0)
                            self.files_layout = QVBoxLayout(self.files_w)
                            self.files_layout.setContentsMargins(0, 0, 0, 0)
                            self.files_layout.setSpacing(0)
                            self.files_layout.setAlignment(Qt.AlignTop)

                            self.files = []
                            assets = data.get("assets") or {}
                            for name in assets.keys():
                                fi = self.FileItem(self.files_w, self.root, name)
                                self.files.append(fi)
                                self.files_layout.addWidget(fi, 0)

                            self.scroll_layout.addStretch(1)

                        def langing(self):
                            time_str = (self.data or {}).get("time") or ""
                            self.time.setText(t(self.root.langer.get("wid.pages.download.item.repoInfo.publish"), time_str))
                            for fi in self.files:
                                fi.langing()

                        def lighting(self, light):
                            bg = "rgb(229, 228, 228)" if light else "rgb(55, 55, 55)"
                            self.setStyleSheet("QWidget#repoInfo { background: %s; }" % bg)
                            self.main.setStyleSheet("QWidget#repoMain { background: %s; }" % bg)
                            if self.pixmap is not None and not self.pixmap.isNull():
                                self.icon.setPixmap(self.pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            else:
                                self.icon.clear()
                            for fi in self.files:
                                fi.lighting(light)

                        def resizeEvent(self, event):
                            self.scroll_slider.setGeometry(
                                self.scroll.width() - 5, 0, 5, self.scroll.height()
                            )
                            super().resizeEvent(event)

                        def showEvent(self, event):
                            super().showEvent(event)
                            self.scroll_slider.setVisible(
                                self.scroll.verticalScrollBar().maximum() > self.scroll.verticalScrollBar().minimum()
                            )

                        class FileItem(QWidget):
                            def __init__(self, parent=None, root=None, name=""):
                                super().__init__(parent)
                                self.parent = parent
                                self.root = root
                                self.name = name
                                self.setFixedHeight(40)
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.init_wid()
                                self.langing()
                                self.lighting(bool(self.root.settings.get("theme")))

                            def init_wid(self):
                                self.layout = QHBoxLayout(self)
                                self.layout.setContentsMargins(8, 0, 8, 0)
                                self.layout.setSpacing(8)
                                self.layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                                self.icon = QLabel()
                                self.icon.setFixedSize(24, 24)
                                self.layout.addWidget(self.icon, 0)

                                self.title = QLabel(self.name)
                                self.title.setProperty("wid", "text")
                                self.title.setStyleSheet("font-size: 14px;")
                                self.title.setWordWrap(True)
                                self.layout.addWidget(self.title, 1)

                                self.btn_download = QPushButton(self)
                                self.btn_download.setFixedSize(18, 18)
                                self.btn_download.setProperty("wid", "lbtn")
                                self.btn_download.setAttribute(Qt.WA_StyledBackground, True)
                                # 目前不连接任何信号
                                self.layout.addWidget(self.btn_download, 0)

                            def langing(self):
                                self.btn_download.setToolTip(self.root.langer.get("wid.pages.download.item.download"))

                            def lighting(self, light):
                                color = QColor(0, 0, 0) if light else QColor(255, 255, 255)
                                icon = change_color("src/assets/files/file.png", color)
                                pixmap = icon.pixmap(24, 24)
                                if not pixmap.isNull():
                                    self.icon.setPixmap(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                bicon = change_color("src/assets/buttons/download.png", color)
                                bpixmap = bicon.pixmap(18, 18)
                                if not bpixmap.isNull():
                                    self.btn_download.setIcon(QIcon(bpixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.FastTransformation)))

                            

                class Origin(Template):
                    def __init__(self, parent=None, root=None, text=None, icon=None):
                        self.introUrl = "https://raw.githubusercontent.com/Anuken/Mindustry/master/README.md"
                        self.releaseRepo = "Anuken/Mindustry"
                        self.iconPath = "src/assets/icons/mdt/mdt.png"
                        self.tmpPath = getPath("BML/.tmp/search/games/.origin.json")
                        self.classs = {}
                        super().__init__(parent, root, text, icon)
                        self.setClasss()

                    def _before_search(self):
                        for w in self.classs.values():
                            w.deleteLater()
                        self.classs.clear()

                    def _on_data_changed(self):
                        self.setClasss()

                    def setClasss(self):
                        for w in self.classs.values():
                            w.deleteLater()
                        self.classs.clear()
                        # 清理上次添加的 stretch（遍历移除全部 spacer，防止残留累积）
                        self._clear_scroll_stretch()
                        # pre-compute icon pixmap once
                        icon_pixmap = QPixmap()
                        icon_full = getPath(self.iconPath)
                        if os.path.exists(icon_full):
                            icon_pixmap.load(icon_full)
                        for i, j in self.data["versions"].items():
                            clss = self.Classs(self, self.root)
                            clss.setData(i, j, icon_pixmap)
                            self.classs[i] = clss
                            self.scroll_layout.addWidget(clss,0)
                        # 尾部 stretch 吸收剩余空间，防止面板被垂直拉伸（挤压在顶部）
                        self.scroll_layout.addStretch(1)

                    def classify(self, back):
                        name_raw = back.get("name") or ""
                        time_raw = back.get("published_at")
                        assets_raw = back.get("assets", [])
                        game_link = next(
                            (a.get("browser_download_url")
                                for a in assets_raw
                                if any(k in a.get("name", "") for k in ("Mindustry", "desktop"))),
                            None
                        )
                        assets = {
                            a["name"]: {"name": a["name"], "linear": a.get("browser_download_url")}
                            for a in assets_raw
                            if a.get("name") and a.get("browser_download_url")
                        }
                        # 如果没有任何可下载的编译包（早期 release），则跳过该 release（不显示、不缓存）
                        if not assets:
                            return {
                                "class": None,
                                "name": None,
                            }
                        m = re.search(r'v?([\d.]+)\s+Build\s+([\d.]+)', name_raw)
                        return {
                            "class": "v" + str(int(float(m.group(1)))) if m else None,
                            "name": re.sub(r'\.0+$', '', m.group(2)) if m else None,
                            "title": name_raw or None,
                            "intro": back.get("body"),
                            "time": time_raw.replace("T", " ").replace("Z", "") if time_raw else None,
                            "releaseUrl": back.get("html_url"),
                            "gameLinear": game_link,
                            "assets": assets,
                        }

                class MindustryX(Template):
                    def __init__(self, parent=None, root=None, text=None, icon=None):
                        self.introUrl = "https://raw.githubusercontent.com/TinyLake/MindustryX/refs/heads/main/README.md"
                        self.releaseRepo = "TinyLake/MindustryX"
                        self.iconPath = "src/assets/icons/mdt/mdtx.png"
                        self.tmpPath = getPath("BML/.tmp/search/games/mindustryx.json")
                        self.classs = {}
                        super().__init__(parent, root, text, icon)
                        self.init_wid()
                        self.setClasss()

                    def init_wid(self):
                        # beta 提示：mindustryX 的 beta 为时效性版本，不写入缓存
                        self.betaTips = QWidget()
                        self.betaTips.setStyleSheet(
                            "QWidget#betaTips{"
                            "background-color: rgba(255, 255, 0, 50);"
                            "border: 1px solid orange;"
                            "border-radius: 4px;"
                            "}"
                        )
                        self.betaTips.setObjectName("betaTips")
                        bt_l = QHBoxLayout(self.betaTips)
                        bt_l.setContentsMargins(8, 6, 8, 6)
                        bt_l.setSpacing(8)

                        self.betaTipsIcon = QLabel()
                        self.betaTipsIcon.setFixedSize(20, 20)
                        self.betaTipsIcon.setScaledContents(True)
                        bt_l.addWidget(self.betaTipsIcon, 0, Qt.AlignTop)

                        self.betaTipsText = QLabel()
                        self.betaTipsText.setProperty("wid", "text")
                        self.betaTipsText.setStyleSheet("font-size: 12px;")
                        self.betaTipsText.setWordWrap(True)
                        bt_l.addWidget(self.betaTipsText, 1)

                        self.betaTips.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
                        self.betaTips.setMaximumWidth(600)
                        try:
                            self.betaTipsIcon.setPixmap(change_color(getPath("src/assets/actions/tips.png"), QColor(255,165,0)).pixmap(QSize(18,18)))
                        except Exception:
                            pass
                        self.betaTipsText.setText(self.root.langer.get("wid.pages.download.mindustryx.betaTips"))

                    def langing(self):
                        super().langing()
                        self.betaTipsText.setText(self.root.langer.get("wid.pages.download.mindustryx.betaTips"))

                    def _before_search(self):
                        for w in self.classs.values():
                            w.deleteLater()
                        self.classs.clear()

                    def _on_data_changed(self):
                        self.setClasss()

                    def search(self):
                        def job(event):
                            cache = self._read_cache()
                            return self._fetch_and_merge([1], 100, cache)

                        def on_done(result):
                            self._set_searching(False)
                            if not isinstance(result, Exception) and isinstance(result, dict):
                                self.data = result
                                self._on_data_changed()
                            elif isinstance(result, Exception):
                                self.root.logger.error(f"[{type(self).__name__}.search] {result}")

                        self._search(job, on_done)

                    @staticmethod
                    def _sort_versions(versions):
                        order = {"alpha": 0, "beta": 1}
                        out = {}
                        for cls_key in sorted(versions.keys(), key=lambda k: order.get(k, 99)):
                            out[cls_key] = dict(sorted(
                                versions[cls_key].items(),
                                key=lambda kv: kv[0],
                                reverse=True
                            ))
                        return out

                    def setClasss(self):
                        for w in self.classs.values():
                            w.deleteLater()
                        self.classs.clear()
                        # 清理上次添加的 stretch（遍历移除全部 spacer，防止残留累积）
                        self._clear_scroll_stretch()
                        icon_pixmap = QPixmap()
                        icon_full = getPath(self.iconPath)
                        if os.path.exists(icon_full):
                            icon_pixmap.load(icon_full)
                        # insert beta tip above the first class panel
                        try:
                            # remove existing if present
                            if getattr(self, 'betaTips', None) and self.betaTips.parent() is not None:
                                try:
                                    self.scroll_layout.removeWidget(self.betaTips)
                                except Exception:
                                    pass
                            if getattr(self, 'betaTips', None):
                                self.scroll_layout.insertWidget(0, self.betaTips, 0)
                        except Exception:
                            pass

                        for i, j in self.data["versions"].items():
                            clss = self.Classs(self, self.root)
                            display_name = self.root.langer.get(f"wid.pages.download.{i}")
                            clss.setData(display_name, j, icon_pixmap)
                            self.classs[i] = clss
                            self.scroll_layout.addWidget(clss,0)
                        # 尾部 stretch 吸收剩余空间，防止面板被垂直拉伸（挤压在顶部）
                        self.scroll_layout.addStretch(1)

                    def classify(self, back):
                        name_raw = back.get("name") or ""
                        time_raw = back.get("published_at")
                        assets_raw = back.get("assets", [])
                        game_link = next(
                            (a.get("browser_download_url")
                                for a in assets_raw
                                if "Desktop" in a.get("name", "")),
                            None
                        )
                        assets = {
                            a["name"]: {"name": a["name"], "linear": a.get("browser_download_url")}
                            for a in assets_raw
                            if a.get("name") and a.get("browser_download_url")
                        }
                        if "X" in name_raw:
                            clss = "alpha"
                        elif "B" in name_raw:
                            clss = "beta"
                        else:
                            clss = None
                        return {
                            "class": clss,
                            "name": name_raw,
                            "title": name_raw or None,
                            "intro": back.get("body"),
                            "time": time_raw.replace("T", " ").replace("Z", "") if time_raw else None,
                            "releaseUrl": back.get("html_url"),
                            "gameLinear": game_link,
                            "assets": assets,
                        }

                    def _fetch_and_merge(self, pages, per_page, cache):
                        # Custom fetch: keep beta results in-memory for rendering,
                        # but only persist alpha versions to disk because beta is time-sensitive.
                        api = self.root.githubAPI
                        releases_all = []
                        max_workers = min(len(pages) + 1, 8)

                        with ThreadPoolExecutor(max_workers=max_workers) as pool:
                            futures = {
                                pool.submit(api.getRelease, self.releaseRepo, p, per_page): p
                                for p in pages
                            }
                            f_intro = None

                            for f in as_completed(futures):
                                try:
                                    ok, data = f.result()
                                    if ok and isinstance(data, list):
                                        releases_all.extend(data)
                                    else:
                                        self.root.logger.warning(f"[{type(self).__name__}._fetch_and_merge] release page failed: {data}")
                                except Exception as e:
                                    self.root.logger.error(f"[{type(self).__name__}._fetch_and_merge] release future exception: {e}")

                        # Build full cache (including beta) for rendering
                        full_cache = cache or {"intro": "", "versions": {}}
                        for r in releases_all:
                            try:
                                d = self.classify(r)
                            except Exception as e:
                                self.root.logger.error(f"[{type(self).__name__}.classify] {e}")
                                continue
                            category = self._normalize_class(d.get('class'))
                            if category is None or d.get('name') is None:
                                continue
                            full_cache.setdefault("versions", {}).setdefault(category, {})[d["name"]] = d

                        # intro is not used for MindustryX (introUrl None)
                        full_cache["versions"] = self._sort_versions(full_cache.get("versions", {}))

                        # Persist only alpha classes
                        write_cache = {"intro": full_cache.get("intro", ""), "versions": {}}
                        for k, v in full_cache.get("versions", {}).items():
                            if k == 'alpha':
                                write_cache["versions"][k] = v

                        self._write_cache(write_cache)
                        return full_cache

                class MindustryARC(Template):
                    def __init__(self, parent=None, root=None, text=None, icon=None):
                        self.introUrl = "https://raw.githubusercontent.com/squi2rel/Mindustry-CN-ARC/refs/heads/master/README.md"
                        self.releaseRepo = "Jackson11500/Mindustry-CN-ARC-Builds"
                        self.iconPath = "src/assets/icons/mdt/mdtarc.png"
                        self.tmpPath = getPath("BML/.tmp/search/games/mindustryarc.json")
                        self.classs = {}
                        super().__init__(parent, root, text, icon)
                        self.scroll_layout.setContentsMargins(1, 1, 1, 1)
                        self.setClasss()

                    def _before_search(self):
                        old = getattr(self, "_flat_scroll", None)
                        if old is not None:
                            old.deleteLater()
                            self._flat_scroll = None

                    def _on_data_changed(self):
                        self.setClasss()

                    def setClasss(self):
                        # 清理旧的平铺 scroll，避免重建时残留
                        old = getattr(self, "_flat_scroll", None)
                        if old is not None:
                            old.deleteLater()
                            self._flat_scroll = None
                        # 清理上次添加的 stretch（遍历移除全部 spacer，防止残留累积）
                        self._clear_scroll_stretch()
                        icon_pixmap = QPixmap()
                        icon_full = getPath(self.iconPath)
                        if os.path.exists(icon_full):
                            icon_pixmap.load(icon_full)
                        # 无分区：合并所有分类的版本，直接平铺进单个 Scroll（无折叠面板）
                        flat = {}
                        for j in self.data["versions"].values():
                            flat.update(j)
                        scroll = self.Scroll(self, self.root)
                        # Scroll.template 默认取 parent.parent（Classs 场景），平铺时需手动指向当前模板
                        scroll.template = self
                        scroll.setData(copy.deepcopy(flat), icon_pixmap)
                        self._flat_scroll = scroll
                        # 铺满整个剩余区域，滚动列表内部自行滚动
                        self.scroll_layout.addWidget(scroll, 1)

                    def classify(self, back):
                        time_raw = back.get("published_at")
                        assets_raw = back.get("assets", [])
                        # 游戏包只匹配 Desktop 资产
                        game_link = next(
                            (a.get("browser_download_url")
                                for a in assets_raw
                                if "Desktop" in a.get("name", "")),
                            None
                        )
                        assets = {
                            a["name"]: {"name": a["name"], "linear": a.get("browser_download_url")}
                            for a in assets_raw
                            if a.get("name") and a.get("browser_download_url")
                        }
                        # 如果没有任何可下载的编译包，则跳过该 release（不显示、不缓存）
                        if not assets:
                            return {
                                "class": None,
                                "name": None,
                            }
                        # 版本号全部为 5 位数：name 与 title 统一使用 release 标题字段
                        title = back.get("name") or back.get("tag_name") or ""
                        return {
                            "class": ".",
                            "name": title,
                            "title": title or None,
                            "intro": back.get("body"),
                            "time": time_raw.replace("T", " ").replace("Z", "") if time_raw else None,
                            "releaseUrl": back.get("html_url"),
                            "gameLinear": game_link,
                            "assets": assets,
                        }
