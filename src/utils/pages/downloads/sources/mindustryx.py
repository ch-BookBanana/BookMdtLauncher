# -*- coding: utf-8 -*-
"""MindustryX 下载源（登记在 core/download.sources）。"""

from src.BMLCore import registrar
from src.utils.pages.downloads.sources._init import *   # noqa: F401,F403
from src.utils.pages.downloads.sources._init import Template


@registrar("core/download.sources").add("mindustryx")
class MindustryX(Template):
    # ── 下载源元信息（详见 Origin 的说明）──
    title_key   = "MdtX"
    introUrl    = "https://raw.githubusercontent.com/TinyLake/MindustryX/refs/heads/main/README.md"
    releaseRepo = "TinyLake/MindustryX"
    iconPath    = ICON_MDTX
    cache_name  = "mindustryx.json"

    def __init__(self, parent=None, text=None, icon=None):
        self.tmpPath = getPath(f"BML/.tmp/search/games/{self.cache_name}")
        self.classs = {}
        super().__init__(parent, text, icon)
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
            self.betaTipsIcon.setPixmap(change_color(getPath(ACT_TIPS), QColor(255,165,0)).pixmap(QSize(18,18)))
        except Exception:
            pass
        self.betaTipsText.setText(events.lang.get("core.wid.pages.download.mindustryx.betaTips"))

    def langing(self):
        super().langing()
        self.betaTipsText.setText(events.lang.get("core.wid.pages.download.mindustryx.betaTips"))

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
                events.logger.error(f"[{type(self).__name__}.search] {result}")

        self._search(job, on_done)

    @classmethod
    def _sort_versions(cls, versions):
        order = {"alpha": 0, "beta": 1}
        out = {}
        for cls_key in sorted(versions.keys(), key=lambda k: order.get(k, 99)):
            bucket = versions[cls_key]
            out[cls_key] = {
                n: bucket[n]
                for n in sorted(bucket.keys(), key=lambda n: cls._time_of(bucket[n]), reverse=True)
            }
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
            clss = self.Classs(self)
            display_name = events.lang.get(f"core.wid.pages.download.{i}")
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
        api = events.githubAPI
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
                        events.logger.warning(f"[{type(self).__name__}._fetch_and_merge] release page failed: {data}")
                except Exception as e:
                    events.logger.error(f"[{type(self).__name__}._fetch_and_merge] release future exception: {e}")

        # Build full cache (including beta) for rendering
        full_cache = cache or {"intro": "", "versions": {}}
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

        # intro is not used for MindustryX (introUrl None)
        full_cache.setdefault("versions", {})
        self._merge_releases(full_cache["versions"], fetched)
        full_cache["versions"] = self._sort_versions(full_cache.get("versions", {}))

        # Persist only alpha classes
        write_cache = {"intro": full_cache.get("intro", ""), "versions": {}}
        for k, v in full_cache.get("versions", {}).items():
            if k == 'alpha':
                write_cache["versions"][k] = v

        self._write_cache(write_cache)
        return full_cache
