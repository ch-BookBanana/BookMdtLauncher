# -*- coding: utf-8 -*-
"""下载源基类 Template：三个源共用，页面本体在 ../game.py。"""

import copy, hashlib, json, os, re, time, webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPixmap, QTextOption
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout,
    QWidget
)

from src.BMLCore import registrar
from src.utils.events import events
from src.utils.QDownloader import QDownloader
from src.utils.mdtManager import mdtManager
from src.utils.qthtimer import QThTimer
from src.utils.options.scrolls import Scroll
from src.utils.path_utils import getPath
from src.utils.utils import (_apply_md_image, change_color, md_to_html,
                             primary_btn_style, t)
from src.utils.pages._init import open_overlay
from src.utils.resources import (ACT_EYE, ACT_EYE_OFF, ACT_TIPS, BTN_DOWNLOAD,
                                 FILE_GENERIC, ICON_MDT, ICON_MDTARC, ICON_MDTX,
                                 NAV_LINK, NAV_MENU, TBT_CLOSE)
from src.utils.registry import Box, registry


_FIELDS = {
    "core.origin": {'color': False},
    "core.mindustryx": {'color': False},
    "core.mindustryarc": {'color': False},
    # 列表项按钮：登记名是点上的短名（"download"），条目 key 于是是
    # <owner>/<名> = core/download；查表这边统一按 "core.download" 取。
    "core.download": {'attr': 'btn_download'},
    "core.repoInfo": {'attr': 'btn_repoInfo'},
    "core.link": {'attr': 'btn_link'}
}


def unpack_box(parent, text=None, icon=None):
    """条目 init 收到 Box 时，把它拆成 (父控件, 文案 key, 图标路径)。

    条目登记成类本身之后（`init=类`），宿主传进来的第一个位置参数是
    ``registry.Box``：父控件在 box.parent，文案/图标在条目上（title / icon）。
    而 Template / Game 的老构造签名是 `(parent, text, icon)` —— 这里就地拆开，
    等价于旧写法 `init=lambda b: cls(b.parent, b.title, b.icon)`。

    不拆的话 parent 会是个 Box（控件挂不上、self.text 变 None，实例默认名
    从「MDTX-160.4」退化成「-160.4」）。
    """
    if isinstance(parent, Box):
        box = parent
        entry = box.entry
        parent = box.parent
        if text is None:
            text = getattr(entry, "title", None)
        if icon is None:
            icon = getattr(entry, "icon", None)
    return parent, text, icon


class Template(QWidget):
    introReady = Signal(object)
    # intro 抓取超时（秒），只作用于附加介绍，子类可覆盖
    introTimeout = 10

    def __init__(self, parent=None, text=None, icon=None):
        super().__init__()
        parent, text, icon = unpack_box(parent, text, icon)
        self.parent = parent
        self.text = text
        self.data = self._read_cache()
        self.icon = icon
        self._searching = False
        self._action_btns = []
        self.introReady.connect(self._on_intro_ready, Qt.QueuedConnection)
        self._init_wid()
        events.theme.changed.connect(self.lighting)
        events.lang.changed.connect(self.langing)

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
        self.add_action_btn("core.wid.pages.download.origin.search", lambda: self.search())
        self.add_action_btn("core.wid.pages.download.origin.searchAll", lambda: self.searchAll())

        # 本地导入：装新实例的第二条路（第一条是下面的下载列表）。
        # 挂在下载页这排而不是主页那颗大按钮下面 —— 主页只留一个主动作；
        # 「从本地文件装一个」本质上也是「获取游戏本体」，跟搜索下载同一件事。
        # 三个下载源共用这一排，所以只写在这一处；拖放仍是全局快捷方式。
        self.action_bar_layout.addSpacing(16)
        self.add_action_btn("core.wid.pages.download.import",
                            lambda: open_overlay("core.importJar", self))

        self.action_bar_layout.addStretch()

        self.main = QWidget()
        self.main.setProperty("wid", "panel-alt")
        self.main.setAttribute(Qt.WA_StyledBackground, True)
        self.scroll = Scroll(self, content=self.main, margins=(30, 20, 30, 20),
                             spacing=10, align=Qt.AlignTop | Qt.AlignHCenter)
        self.layout.addWidget(self.scroll)

        self.scroll_layout = self.scroll.scroll_layout

    def _set_searching(self, disabled):
        self._searching = disabled
        for btn in self._action_btns:
            btn.setDisabled(disabled)

    def add_action_btn(self, text_key, callback):
        btn = QPushButton(events.lang.get(text_key))
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
                btn.setText(events.lang.get(btn._text_key))

    def _clear_scroll_stretch(self):
        i = 0
        while i < self.scroll_layout.count():
            it = self.scroll_layout.itemAt(i)
            if it is not None and it.spacerItem() is not None:
                self.scroll_layout.takeAt(i)
                continue
            i += 1

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
    def _time_of(item):
        """条目时间戳：classify 时把 published_at 归一为 'YYYY-MM-DD HH:MM:SS'，字典序即时间序。"""
        return (item.get("time") or "") if isinstance(item, dict) else ""

    @classmethod
    def _sort_versions(cls, versions):
        """分类与组内条目全部按时间倒序（分类取组内最新时间）。"""
        out = {}
        for cls_key in sorted(
            versions.keys(),
            key=lambda k: max((cls._time_of(v) for v in versions[k].values()), default=""),
            reverse=True):
            bucket = versions[cls_key]
            out[cls_key] = {
                n: bucket[n]
                for n in sorted(bucket.keys(), key=lambda n: cls._time_of(bucket[n]), reverse=True)
            }
        return out

    @classmethod
    def _merge_releases(cls, versions, fetched):
        """按时间窗合并本次抓取结果（fetched: [(分类, 条目), ...]）。

        以本次抓取结果覆盖的 [最旧, 最新] 时间区间为界：
        该区间内的缓存条目全部删除，换成刚抓到的内容
        （release 可能被编辑、撤回或重发，区间内的旧条目不可信）；
        区间外（更早的历史版本）保持不动，增量搜索不会丢历史。
        抓取结果为空时不做任何删除。
        """
        if not fetched:
            return versions
        times = [t for t in (cls._time_of(d) for _, d in fetched) if t]
        if times:
            lo, hi = min(times), max(times)
            for cls_key in list(versions.keys()):
                bucket = versions[cls_key]
                for name in [n for n, d in bucket.items()
                                if lo <= cls._time_of(d) <= hi]:
                    del bucket[name]
                if not bucket:
                    del versions[cls_key]
        for category, d in fetched:
            versions.setdefault(category, {})[d["name"]] = d
        return versions

    def _fetch_and_merge(self, pages, per_page, cache):
        api = events.githubAPI
        releases_all = []
        max_workers = min(len(pages) + 1, 8)

        # 不用 with：__exit__ 会 shutdown(wait=True)，会被慢的 intro 连接拖住
        pool = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {
                pool.submit(api.getRelease, self.releaseRepo, p, per_page): p
                for p in pages
            }
            # intro 挂后台，抓完由 introReady 信号回主线程补写缓存，不阻塞本次搜索
            if self.introUrl:
                pool.submit(
                    events.githubAPI._session.get, self.introUrl,
                    timeout=self.introTimeout).add_done_callback(self._on_intro_fetched)

            for f in as_completed(futures):
                try:
                    ok, data = f.result()
                    if ok and isinstance(data, list):
                        releases_all.extend(data)
                    else:
                        events.logger.warning(f"[{type(self).__name__}._fetch_and_merge] release page failed: {data}")
                except Exception as e:
                    events.logger.error(f"[{type(self).__name__}._fetch_and_merge] release future exception: {e}")
        finally:
            pool.shutdown(wait=False, cancel_futures=False)

        fetched = []
        for r in releases_all:
            try:
                d = self.classify(r)
            except Exception as e:
                events.logger.error(f"[{type(self).__name__}.classify] {e}")
                continue
            category = self._normalize_class(d.get('class'))
            if category is None or d.get('name') is None:
                continue
            fetched.append((category, d))

        cache.setdefault("versions", {})
        self._merge_releases(cache["versions"], fetched)

        cache["intro"] = cache.get("intro", "")

        cache["versions"] = self._sort_versions(cache["versions"])
        self._write_cache(cache)
        return cache

    def _on_intro_fetched(self, fut):
        """子线程回调：介绍抓到了就交给主线程，失败静默（介绍缺失不影响搜索）。"""
        try:
            resp = fut.result()
        except Exception:
            return
        if getattr(resp, "status_code", None) == 200 and getattr(resp, "text", ""):
            self.introReady.emit(resp.text)

    def _on_intro_ready(self, text):
        """主线程：把介绍正文补进缓存，下次打开仓库信息页即有内容。"""
        if not text:
            return
        try:
            data = self._read_cache()
            data["intro"] = text
            self._write_cache(data)
        except Exception:
            pass
        if isinstance(getattr(self, "data", None), dict):
            self.data["intro"] = text

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
                events.logger.error(f"[{type(self).__name__}.search] {result}")

        self._search(job, on_done)

    def searchAll(self):
        def job(event):
            api = events.githubAPI
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
                events.logger.error(f"[{type(self).__name__}.searchAll] {result}")

        self._search(job, on_done)

    def classify(self, back):
        raise NotImplementedError("Subclass must implement classify()")

    class Classs(QWidget):
        def __init__(self,parent=None):
            super().__init__()
            self.parent = parent
            self.light = None
            self.data = {}
            self.btnPix = [QPixmap(),QPixmap()]
            self.setAttribute(Qt.WA_StyledBackground, True)

            self.setStyleSheet('QWidget[wid_="game-card"]{border-radius:10px;}')
            self.setProperty("wid_","download.game.classs")
            self.setMaximumWidth(600)
            self.init_wid()
            events.theme.changed.connect(self.lighting)
            events.lang.changed.connect(self.langing)

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
            self.label2.setProperty("wid","btn-text")
            self.label2.setStyleSheet("font-size:14px;")
            self.topL.addWidget(self.label2,0)

            self.topL.addStretch(1)

            self.button = QPushButton()
            self.button.setFixedSize(40,40)
            self.button.setProperty("wid","btn-text")
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

            self.scroll = self.parent.Scroll(self)
            self.contentL.addWidget(self.scroll,0)
            self.lighting(events.settings["theme"])

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
                self.btnPix[1] = change_color(getPath(ACT_EYE),QColor(25,25,25) if light else QColor(220,220,220))
                self.btnPix[0] = change_color(getPath(ACT_EYE_OFF),QColor(25,25,25) if light else QColor(220,220,220))
            self.button.setIcon(QIcon(self.btnPix[int(self.contentW.isVisible())]))

        def showEvent(self,event):
            super().showEvent(event)
            self.scroll.setFixedHeight(min(400, len(self.data)*60-10))

    class Scroll(QWidget):
        def __init__(self,parent=None):
            super().__init__()
            self.parent = parent
            # 上层模板（Classs.parent 即 Template 子类），供 Item 引用 RepoInfo 等嵌套类
            self.template = self.parent.parent if self.parent is not None else None
            self.itemd = {}   # 数据列表
            self.itemw = []   # 可视化复用item池
            self.item_h = 50
            self.viewport_h = 0
            self.total_count = 0
            self.start_index = 0
            self._hidden = False
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

            # 虚拟列表：子控件自己 setGeometry 定位，所以不要内容布局
            self.scroll = Scroll(self, layout=False)
            bar = self.scroll.bar()
            # 滚动时：1) 刷新 item 池内容 2) 刷新悬停状态
            bar.valueChanged.connect(self._update_visible)
            bar.valueChanged.connect(self._check_all_hover)
            self.layout.addWidget(self.scroll)

            self.main = self.scroll.main
            self.main.setMinimumWidth(0)

            # 空数据提示：铺满整个滚动区，无条目时显示
            self.empty_label = QLabel(self)
            self.empty_label.setAlignment(Qt.AlignCenter)
            self.empty_label.setProperty("wid", "title")
            self.empty_label.setStyleSheet("font-size:16px;")
            self.empty_label.setText(events.lang.get("core.wid.pages.download.empty"))
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
            self.empty_label.setGeometry(0, 0, self.width(), self.height())
            super().resizeEvent(event)
            self.viewport_h = self.height()
            visible = int((self.viewport_h + self.item_h - 1) / self.item_h) + 2
            while len(self.itemw) < visible:
                it = self.Item(self.main, self.template)
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
            self._hidden = False
            self.scroll.barShow()
            self._update_visible()

        def hideEvent(self, event):
            super().hideEvent(event)
            self._hidden = True
            # 隐藏时销毁 item 池，释放图片等资源；显示时由 showEvent 重建
            for it in self.itemw:
                it.setParent(None)
                it.deleteLater()
            self.itemw.clear()

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
            if self._hidden:
                return
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
                    it = self.Item(self.main, self.template)
                    it.setParent(self.main)
                    it.hide()
                    self.itemw.append(it)
            vbar = self.scroll.bar()
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
                widget.lighting(bool(events.settings.get("theme")))
                widget.check_hover()
                y = idx * self.item_h
                widget.setGeometry(0, y, self.scroll.viewport().width(), self.item_h)
                widget.show()

        class Item(QWidget):
            def __init__(self,parent=None,template=None):
                super().__init__(parent)
                self.parent = parent
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
                events.theme.changed.connect(self.lighting)
                events.lang.changed.connect(self.langing)

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
                def __init__(self, icon_path, tooltip_key, parent=None):
                    super().__init__(parent)
                    self.parent = parent
                    self._icon_path = icon_path
                    self._tooltip_key = tooltip_key
                    self._is_show = True   # 悬浮 Item 时是否显示该按钮
                    self.init_ui()
                    events.theme.changed.connect(self.lighting)
                    events.lang.changed.connect(self.langing)

                def init_ui(self):
                    self.setFixedSize(20, 20)
                    self.setProperty("wid", "btn-text")
                    # 开启 QSS 背景，让 btn-text:hover 的悬停背景生效
                    self.setAttribute(Qt.WA_StyledBackground, True)
                    self.hide()
                    self.langing()

                def langing(self):
                    self.setToolTip(events.lang.get(self._tooltip_key))

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
                        events.logger.warning(f"Failed to load pixmap for {self._icon_path}")

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

                self._action_btns = []
                for e in registry.entries("core.download.item.actions"):
                    btn = e.init(Box(parent=self, entry=e))
                    setattr(self, _FIELDS.get(e.key.replace("/", "."), {}).get("attr", ""), btn)
                    self.layout.addWidget(btn, 0)
                    self._action_btns.append(btn)

            def open_release(self):
                url = self.data.get("releaseUrl") or ""
                if url:
                    webbrowser.open(url)
                else:
                    events.logger.warning("Item has no releaseUrl to open")

            def set_hover(self, hover):
                if self._hovering != hover:
                    self._hovering = hover
                    # 悬停时应用高亮背景，移开恢复（内联样式保证 QWidget 子类背景生效）
                    light = bool(events.settings.get("theme"))
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
        """下载命名弹窗：作为叠加浮层（FloatingOverlay）页面显示。

        只保留「名称输入 + 校验提示 + 确定/关闭」；release 的图标、标题、
        发布时间由调用方 Item 自行呈现，此处不再重复展示。"""

        def __init__(self, parent=None, data=None):
            super().__init__()
            self.parent = parent
            self.data = data
            self._final_name = None
            self._validate_key = None
            self._closed = False
            self._dl_timer = None
            # 遮罩与居中由叠加浮层统一提供，本页自身即弹窗面板
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("wid","panel-alt")
            self.init_wid()
            self.langing()
            self.lighting(bool(events.settings.get("theme")))
            self._init_name_input()
            self._start_validation()
            events.theme.changed.connect(self.lighting)
            events.lang.changed.connect(self.langing)

        def init_wid(self):
            self.setFixedSize(320, 190)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setAlignment(Qt.AlignTop)

            # 关闭按钮行：release 标题 + ×（不再展示图标/发布时间）
            self.top = QWidget()
            self.top.setProperty("wid", "panel-alt")
            self.top.setFixedHeight(30)
            self.layout.addWidget(self.top, 0)
            self.top_layout = QHBoxLayout(self.top)
            self.top_layout.setContentsMargins(15, 0, 3, 0)
            self.top_layout.setSpacing(0)

            # 标题：占满剩余宽度，过长时裁切（悬停看全文）
            self.title = QLabel(self.data.get("title") or self.data.get("name") or "")
            self.title.setProperty("wid", "title")
            self.title.setStyleSheet("font-size: 16px;")
            self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.title.setToolTip(self.title.text())
            self.top_layout.addWidget(self.title, 1)

            self.btn_close = QPushButton()
            self.btn_close.setFixedSize(24, 24)
            self.btn_close.setProperty("wid", "btn-tool")
            self.btn_close.clicked.connect(lambda: self._close())
            self.top_layout.addWidget(self.btn_close, 0)

            # 分割线（同 GithubSetting：贯穿整宽）
            self.line = QWidget(self)
            self.line.setFixedHeight(1)
            self.line.setProperty("wid", "line")
            self.layout.addWidget(self.line, 0)

            # 内容区：输入框 + 提示/确定行
            self.body = QWidget()
            self.body.setProperty("wid", "panel-alt")
            self.body.setStyleSheet("background: transparent")
            self.layout.addWidget(self.body, 1)
            self.body_layout = QVBoxLayout(self.body)
            self.body_layout.setSpacing(0)
            self.body_layout.setContentsMargins(15, 0, 15, 15)
            self.body_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

            # 上方弹性空隙：输入框靠下、提示/确定行贴右下角
            self.body_layout.addStretch(1)

            # 名称输入框：默认 "界面名-版本"（自动去重 (1)(2)...）
            self.input = QLineEdit()
            self.input.setProperty("wid", "input")
            self.input.setFixedHeight(32)
            self.input.setClearButtonEnabled(True)
            # 名称即实例目录名，上限与 check_name 同源，超长直接打不进去
            self.input.setMaxLength(mdtManager.MAX_NAME_LEN)
            self.body_layout.addWidget(self.input, 0)

            self.body_layout.addStretch(1)

            # 提示标签 + 确定按钮一行（确定按钮靠右）
            self.bottom = QWidget()
            self.bottom.setStyleSheet("background: transparent")
            self.body_layout.addWidget(self.bottom, 0)
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
            self.btn_ok.setStyleSheet(primary_btn_style(bool(events.settings.get("theme")), False))
            self.btn_ok.clicked.connect(self._on_ok)
            self.bottom_layout.addWidget(self.btn_ok, 0)

        def langing(self):
            self.btn_ok.setText(events.lang.get("core.text.yes"))
            self.btn_close.setToolTip(events.lang.get("core.wid.top.close"))
        
        def lighting(self, light: bool):
            # 关闭按钮图标：随主题取色（本页其余控件由全局 qss 控制）
            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
            icon = change_color(TBT_CLOSE, color)
            self.btn_close.setIcon(QIcon(icon.pixmap(24, 24)))

        # ---------- 名称默认值与去重 ----------
        def _init_name_input(self):
            template = getattr(self.parent, "template", None)
            interface_name = ""
            if template is not None:
                interface_name = events.lang.get(getattr(template, "text", "")) or ""
            base = interface_name + "-" + (self.data.get("name") or "")
            existing = events.mdtManager.taken_names()
            default = events.mdtManager.unique_name(base, existing)
            self.input.setText(default)
            # 背景提示与默认名称一致：清空后仍能看到原名
            self.input.setPlaceholderText(default)
            self.input.textChanged.connect(self._on_text_changed)
            self._apply_existing(existing)

        # ---------- 名称校验：子线程收集 / 主线程应用 ----------
        def _collect_mdts(self, event):
            """子线程：收集已占用的游戏名集合（纯文件操作，线程安全）。"""
            try:
                return events.mdtManager.taken_names()
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

        def _close(self):
            """关闭弹窗：从叠加浮层出叠并销毁（on_close 会停止周期检测）。"""
            events.emit("overlayClosed", self, True)

        def on_close(self):
            """浮层出叠（或被清空）时同步调用：停止周期检测，防止对已销毁对象回调。"""
            self._closed = True
            self._stop_validation()

        def _on_text_changed(self, text):
            # 文字变化：立即单次检测（QThTimer.task 跑完自销毁，无需外部保活）
            if self._closed:
                return
            QThTimer.task(0, self._collect_mdts, result_callback=self._apply_validation)

        def _apply_validation(self, result):
            if self._closed or isinstance(result, Exception):
                return
            self._apply_existing(result)

        def _apply_existing(self, existing):
            """按现有游戏名集合校验输入框，并同步更新按钮/提示状态。

            字形规则与去重全取自 mdtManager（check_name / unique_name），
            本页只负责把失败码翻成提示文案与边框颜色。
            """
            text = self.input.text().strip()
            if not text:
                state, final, msg = "empty", None, ""
            else:
                error = mdtManager.check_name(text)
                unique = events.mdtManager.unique_name(text, existing)
                if error == "dot":
                    state, final, msg = "dot", None, events.lang.get("core.wid.pages.download.item.name.dot")
                elif error:
                    state, final, msg = "illegal", None, events.lang.get("core.wid.pages.download.item.name.illegal")
                elif unique != text:
                    state, final, msg = "dup", unique, t(events.lang.get("core.wid.pages.download.item.name.willBe"), unique)
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
                self.btn_ok.setStyleSheet(primary_btn_style(bool(events.settings.get("theme")), False))
            elif state == "dup":
                self.input.setStyleSheet("border: 1px solid yellow;")
                self.label2.setStyleSheet("font-size: 13px; color: yellow;")
                self.label2.setText(msg)
                self.btn_ok.setEnabled(True)
                self.btn_ok.setStyleSheet(primary_btn_style(bool(events.settings.get("theme")), True))
            elif state == "empty":
                self.input.setStyleSheet("")
                self.label2.setStyleSheet("font-size: 13px;")
                self.label2.setText("")
                self.btn_ok.setEnabled(False)
                self.btn_ok.setStyleSheet(primary_btn_style(bool(events.settings.get("theme")), False))
            else:
                self.input.setStyleSheet("")
                self.label2.setStyleSheet("font-size: 13px;")
                self.label2.setText("")
                self.btn_ok.setEnabled(True)
                self.btn_ok.setStyleSheet(primary_btn_style(bool(events.settings.get("theme")), True))

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
                self.label2.setText(events.lang.get("core.wid.pages.download.item.name.noUrl"))
                return
            target_dir = getPath("BML/.Mindustrys/" + name)
            try:
                os.makedirs(target_dir, exist_ok=True)
            except OSError as e:
                events.logger.error("[mdt-download] 创建目录失败: %s" % e)
                return
            dest_path = os.path.join(target_dir, "mdt.jar")
            _tpl = getattr(self.parent, "template", None)
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
            }
            try:
                with open(os.path.join(target_dir, "downloading.json"), "w", encoding="utf-8") as f:
                    json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
            except OSError as e:
                events.logger.error("[mdt-download] 写入 downloading.json 失败: %s" % e)
                return
            try:
                dl = QDownloader(url=url, dest_path=dest_path, num_threads=4, chunk_size_mb=4, title=name)
            except Exception as e:
                events.logger.error("[mdt-download] 创建下载任务失败: %s" % e)
                return
            _ACTIVE_DOWNLOADS.append(dl)
            dl.finished.connect(lambda ok, d=dl, n=name: self._on_dl_finished(d, n, ok))
            dl.error.connect(lambda err, d=dl: events.logger.error("[mdt-download:%s] %s" % (getattr(d, "task_id", "?"), err)))
            dl.start()
            events.logger.info("[mdt-download] 开始下载 %s: %s" % (name, url))
            # 关闭弹窗，下载在后台由 QDownloader 自行处理
            events.emit("overlayClosed", self, True)

        def _on_dl_finished(self, dl, name, ok):
            """下载完成收尾：释放 QDownloader；成功后刷新 BML.json 并删除 downloading.json。"""
            try:
                dl.wait_thread(5000)
                dl.deleteLater()
            except Exception:
                pass
            try:
                if dl in _ACTIVE_DOWNLOADS:
                    _ACTIVE_DOWNLOADS.remove(dl)
            except Exception:
                pass
            if not ok:
                events.logger.error("[mdt-download] %s 下载失败（downloading.json 已保留）" % name)
                return
            try:
                events.mdtManager._retrieve_mdt_data(name)
                dfile = getPath("BML/.Mindustrys/%s/downloading.json" % name)
                if os.path.isfile(dfile):
                    # 把下载时记录的类图标路径合并进 BML.json
                    try:
                        with open(dfile, "r", encoding="utf-8") as f:
                            dinfo = json.load(f)
                        icon_path = dinfo.get("icon_path")
                        if icon_path:
                            bfile = getPath("BML/.Mindustrys/%s/BML.json" % name)
                            bdata = {}
                            if os.path.isfile(bfile):
                                with open(bfile, "r", encoding="utf-8") as f:
                                    bdata = json.load(f)
                            bdata["icon_path"] = icon_path
                            with open(bfile, "w", encoding="utf-8") as f:
                                json.dump(bdata, f, ensure_ascii=False, separators=(",", ":"))
                    except Exception:
                        pass
                    os.remove(dfile)
                events.mdtManager.invalidate_cache()
                events.logger.info("[mdt-download] %s 下载完成" % name)
            except Exception as e:
                events.logger.error("[mdt-download] %s 收尾失败: %s" % (name, e))

    class RepoInfo(QWidget):
        mdImageReady = Signal(object, object)

        def __init__(self, parent=None, data=None, pixmap=None): 
            super().__init__()
            self.parent = parent
            self.data = data
            self.pixmap = pixmap
            self.setObjectName("repoInfo")
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.init_wid()
            self.langing()
            self.lighting(bool(events.settings.get("theme")))
            events.theme.changed.connect(self.lighting)
            events.lang.changed.connect(self.langing)

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignTop)

            # 滚动区（整体可滚，内容最大宽度 800，超出后在视口中水平居中）
            self.main = QWidget()
            self.main.setObjectName("repoMain")
            self.main.setAttribute(Qt.WA_StyledBackground, True)
            self.main.setMaximumWidth(800)
            self.scroll = Scroll(self, content=self.main, margins=(20, 15, 20, 15),
                                 spacing=10, content_align=Qt.AlignHCenter)
            self.scroll_layout = self.scroll.scroll_layout
            self.layout.addWidget(self.scroll, 1)

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
            self.intro = QTextBrowser()
            self.intro.setAlignment(Qt.AlignTop)
            self.intro.setProperty("wid", "text")
            self.intro.setStyleSheet("font-size: 14px;")
            self.intro.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            self.intro.setTextInteractionFlags(Qt.NoTextInteraction)
            self.intro.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.intro.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.intro.document().setDocumentMargin(0)
            self.intro_area = Scroll(self.main, content=self.intro, content_align=Qt.AlignTop)
            self.intro_area.setFixedHeight(300)
            self.scroll_layout.addWidget(self.intro_area, 0)

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
                try:
                    on_image = self.mdImageReady.emit
                except Exception:
                    on_image = None
                return md_to_html(
                    intro_md,
                    base_url=base_url,
                    session=events.githubAPI._session,
                    cache_dir=getPath("BML/.tmp/mdimg"),
                    on_image=on_image)

            def _done(result):
                try:
                    if not isinstance(result, str):
                        result = md_to_html(intro_md)
                    self._intro_md = result
                    # _job 已返回 HTML（含图片缓存与 0.2 缩放），直接渲染
                    self.intro.setHtml(result)
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
                try:
                    self._mdimg_pending[full] = local
                    if self._mdimg_flush is None:
                        self._mdimg_flush = QTimer.singleShot(0, _flush_md_images)
                except Exception:
                    pass

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
                fi = self.FileItem(self.files_w, name)
                self.files.append(fi)
                self.files_layout.addWidget(fi, 0)

            self.scroll_layout.addStretch(1)

        def langing(self):
            time_str = (self.data or {}).get("time") or ""
            self.time.setText(t(events.lang.get("core.wid.pages.download.item.repoInfo.publish"), time_str))
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

        class FileItem(QWidget):
            def __init__(self, parent=None, name=""):
                super().__init__(parent)
                self.parent = parent
                self.name = name
                self.setFixedHeight(40)
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.init_wid()
                self.langing()
                self.lighting(bool(events.settings.get("theme")))
                events.theme.changed.connect(self.lighting)
                events.lang.changed.connect(self.langing)

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
                self.btn_download.setProperty("wid", "btn-text")
                self.btn_download.setAttribute(Qt.WA_StyledBackground, True)
                # 目前不连接任何信号
                self.layout.addWidget(self.btn_download, 0)

            def langing(self):
                self.btn_download.setToolTip(events.lang.get("core.wid.pages.download.item.download"))

            def lighting(self, light):
                color = QColor(0, 0, 0) if light else QColor(255, 255, 255)
                icon = change_color(FILE_GENERIC, color)
                pixmap = icon.pixmap(24, 24)
                if not pixmap.isNull():
                    self.icon.setPixmap(pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                bicon = change_color(BTN_DOWNLOAD, color)
                bpixmap = bicon.pixmap(18, 18)
                if not bpixmap.isNull():
                    self.btn_download.setIcon(QIcon(bpixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.FastTransformation)))

            


# 三个下载源拆在 sources/ 下，import 即登记（要在 Template 定义之后，避免循环）
