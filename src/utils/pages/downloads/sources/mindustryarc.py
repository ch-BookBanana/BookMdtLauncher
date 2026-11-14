# -*- coding: utf-8 -*-
"""MindustryARC 下载源（登记在 core/download.sources）。"""

from src.BMLCore import registrar
from src.utils.pages.downloads.sources._init import *   # noqa: F401,F403
from src.utils.pages.downloads.sources._init import Template


@registrar("core/download.sources").add("mindustryarc")
class MindustryARC(Template):
    # ── 下载源元信息（详见 Origin 的说明）──
    title_key   = "MdtArc"
    introUrl    = "https://raw.githubusercontent.com/squi2rel/Mindustry-CN-ARC/refs/heads/master/README.md"
    releaseRepo = "Jackson11500/Mindustry-CN-ARC-Builds"
    iconPath    = ICON_MDTARC
    cache_name  = "mindustryarc.json"

    def __init__(self, parent=None, text=None, icon=None):
        self.tmpPath = getPath(f"BML/.tmp/search/games/{self.cache_name}")
        self.classs = {}
        super().__init__(parent, text, icon)
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
        scroll = self.Scroll(self)
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
