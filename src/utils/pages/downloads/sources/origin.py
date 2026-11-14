# -*- coding: utf-8 -*-
"""Origin 下载源（登记在 core/download.sources）。"""

from src.BMLCore import registrar
from src.utils.pages.downloads.sources._init import *   # noqa: F401,F403
from src.utils.pages.downloads.sources._init import Template


@registrar("core/download.sources").add("origin")
class Origin(Template):
    title_key   = "core.wid.pages.download.origin"
    introUrl    = "https://raw.githubusercontent.com/Anuken/Mindustry/master/README.md"
    releaseRepo = "Anuken/Mindustry"
    iconPath    = ICON_MDT
    cache_name  = ".origin.json"

    def __init__(self, parent=None, text=None, icon=None):
        self.tmpPath = getPath(f"BML/.tmp/search/games/{self.cache_name}")
        self.classs = {}
        super().__init__(parent, text, icon)
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
            clss = self.Classs(self)
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
