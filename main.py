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
"""
版本信息见上方英文，以下为中文摘要：
本程序为自由软件，您可以根据GNU通用公共许可证的条款重新分发和修改它，许可证版本为3或（由您选择）更高版本。
本程序的发布目的是希望它能有用，但不提供任何保证，包括但不限于适销性或特定用途的适用性的隐含保证。有关更多细节，请参阅GNU通用公共许可证。
您应该已经收到GNU通用公共许可证的副本，如果没有，请访问http://www.gnu.org/licenses/。
"""

init = {
    "version": "26-T0818",
    "BuildCode": "10000.01"
}


from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QSize, QByteArray, QUrl, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QFont, QFontMetrics, QPainterPath, QCursor, QAction, QTextOption, QImage
from PySide6.QtWidgets import QWidget, QScrollBar, QApplication, QHBoxLayout, QVBoxLayout, QStackedWidget, QStackedLayout, QGridLayout, QLineEdit, QPushButton, QLabel, QTextBrowser, QFrame, QScrollArea, QButtonGroup, QSizePolicy, QStyle, QStyleOptionSlider, QStyleOptionComboBox, QSlider, QComboBox, QSystemTrayIcon, QMenu, QDialog, QTextEdit, QProgressBar
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import sys, os, json, copy, winreg, logging, glob, locale, hashlib, base64, re, time, shutil, traceback, webbrowser, threading
from urllib.parse import urljoin, urlparse
import requests
import markdown
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import ctypes.wintypes
from src.utils.path_utils import getPath
from src.utils.mdtScanner import mdtScanner
from src.utils.mdtLauncher import mdtLauncher, set_tr_func as mdt_set_tr_func
from src.utils.javaScanner import javaScanner
from src.utils.QThTimer import QThTimer
from src.utils.githubAPI import GithubAPI
from src.utils import javaDownload
from src.utils.QDownloader import QDownloader


def change_color(path, color: QColor):
    """白底png改色"""
    pix = QPixmap(getPath(path))
    colored = QPixmap(pix.size())
    colored.fill(Qt.transparent)
    painter = QPainter(colored)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pix)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(colored.rect(), color)
    painter.end()
    return QIcon(colored)

def pngSha(path):
    """计算png的sha256"""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(65536)  # 64KB
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

def t(text, *args):
    try:
        for i, arg in enumerate(reversed(args), start=1):
            text = text.replace(f"${i}", str(arg))
    except Exception:
        pass
    return text


def _is_mdt_download(dest):
    """dest 是否属于 mdt 游戏下载目标（BML/.Mindustrys/ 下）。"""
    if not dest:
        return False
    try:
        base = os.path.normcase(os.path.normpath(mdtScanner.base_dir))
        path = os.path.normcase(os.path.normpath(dest))
        return path == base or path.startswith(base + os.sep)
    except Exception:
        return False


def _preprocess_md(text):
    """markdown 预处理：修复 GitHub release body 中的表格解析问题。

    - 统一换行符为 \\n
    - 表格块（连续的 | 行）前若无空行则补空行（tables 扩展要求表格是新块开头）
    - 去除表格行前导缩进（缩进的表格会被当作代码块/列表续行）
    """
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        is_table_row = stripped.startswith("|") and "|" in stripped[1:]
        if is_table_row:
            block = []
            j = i
            while j < n:
                s = lines[j].strip()
                if s.startswith("|") and "|" in s[1:]:
                    block.append(s)  # 去缩进
                    j += 1
                else:
                    break
            if out and out[-1].strip() != "":
                out.append("")
            out.extend(block)
            i = j
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def md_to_html(text, base_url=None, session=None, cache_dir=None, on_image=None):
    """markdown → HTML（含表格支持），并把 <img> 资源缓存到本地。

    参数:
        text      : markdown 原文
        base_url  : 相对路径图片的解析基准（如 README 的 raw 地址）
        session   : requests.Session，用于下载图片（可为 None 表示离线）
        cache_dir : 图片缓存目录（默认 BML/.tmp/mdimg）
        on_image  : 可选回调 on_image(full, local)。未缓存图片先以占位图显示，
                    后台逐张下载，每成功一张调用一次该回调（下载线程中触发）。
    返回:
        HTML 字符串。
    """
    if not text:
        return text or ""
    try:
        # 预处理：修复表格块（补空行 + 去缩进）
        text = _preprocess_md(text)
        # nl2br：把单个换行（CRLF 等）也转为 <br>，避免 markdown 默认合并为同一行
        html = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists", "nl2br"])
    except Exception:
        return text
    # 给表格加边框（Qt 富文本渲染表格默认无边框）
    html = re.sub(r"<table[^>]*>", '<table border="1" cellspacing="0" cellpadding="4">', html)
    # 图片缓存：立即返回（未缓存图先占位），后台下载完成后经 on_image 逐张替换
    try:
        html = _cache_md_images(html, base_url, session, cache_dir, on_image)
    except Exception:
        pass
    return html


def _cache_md_images(html, base_url, session, cache_dir, on_image=None):
    """把 <img> 的远程 src 换成本地缓存；未缓存的先以占位图显示并打上 data-mdimg 标记，
    后台线程池逐张下载，每成功一张就回调 on_image(full, local)，由调用方把该图替换为真实图。

    注意：本函数立即返回（不等待下载完成），下载线程为 daemon。
    """
    if cache_dir is None:
        cache_dir = getPath("BML/.tmp/mdimg")
    os.makedirs(cache_dir, exist_ok=True)
    fallback = getPath("src/assets/files/file-image.png")

    def _local_path(full):
        """url → 缓存文件路径（sha1 前 16 位 + 扩展名）"""
        ext = os.path.splitext(urlparse(full).path)[1]
        if not ext or len(ext) > 8:
            ext = ".png"
        name = hashlib.sha1(full.encode("utf-8")).hexdigest()[:16] + ext
        return os.path.join(cache_dir, name)

    def _download(full):
        """下载单张图片到缓存，返回 (full, 本地路径或 None)"""
        local = _local_path(full)
        if os.path.exists(local) and os.path.getsize(local) > 0:
            return full, local
        if session is None:
            return full, None
        try:
            resp = session.get(full, timeout=10, stream=True)
            if resp.status_code == 200:
                with open(local, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        f.write(chunk)
                if os.path.exists(local) and os.path.getsize(local) > 0:
                    return full, local
        except Exception:
            pass
        return full, None

    # 收集所有远程图片 URL；已缓存的直接用本地图，未缓存的先占位 + 后台下载。
    # 共享 githubAPI 的 session（trust_env=True），自动尊重系统代理（VPN/加速器）。
    remote = []
    for s in re.findall(r'<img\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        s = s.strip()
        if not s or s.startswith(("data:", "#", "file:")):
            continue
        if s.startswith(("http://", "https://")):
            full = s
        elif base_url:
            full = urljoin(base_url, s)
        else:
            continue
        remote.append(full)

    mapping = {}   # full → 本地路径（仅已缓存成功的）
    pending = []   # 需要后台下载的 URL
    for full in remote:
        local = _local_path(full)
        if os.path.exists(local) and os.path.getsize(local) > 0:
            mapping[full] = local
        else:
            pending.append(full)

    def _resolve_full(src):
        src = src.strip()
        if src.startswith(("http://", "https://")):
            return src
        if base_url:
            return urljoin(base_url, src)
        return None

    def _to_local(src):
        src = src.strip()
        if not src or src.startswith(("data:", "#", "file:")):
            return src
        full = _resolve_full(src)
        if not full:
            return QUrl.fromLocalFile(fallback).toString()
        local = mapping.get(full)
        if local is not None and os.path.exists(local):
            return QUrl.fromLocalFile(local).toString()
        return QUrl.fromLocalFile(fallback).toString()

    def _replace(m):
        tag = m.group(0)
        # 替换 src 为本地路径
        def _src(m2):
            return m2.group(1) + _to_local(m2.group(2)) + m2.group(3)
        new_tag = re.sub(r'(\bsrc\s*=\s*["\'])([^"\']+)(["\'])', _src, tag, flags=re.IGNORECASE)
        full = None
        ms = re.search(r'\bsrc\s*=\s*["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if ms:
            full = _resolve_full(ms.group(1))
        new_tag = re.sub(r'\s+(?:width|height)\s*=\s*["\'][^"\']*["\']', '', new_tag, flags=re.IGNORECASE)
        if full and full not in mapping:
            attrs = ' data-mdimg="%s" width="64" height="64"' % _html_escape(full)
        else:
            attrs = _img_size_attr(mapping.get(full)) if full else ""
        if attrs:
            if re.search(r'/\s*>$', new_tag):
                new_tag = re.sub(r'/\s*>$', attrs + '/>', new_tag)
            else:
                new_tag = re.sub(r'>$', attrs + '>', new_tag)
        return new_tag

    html = re.sub(r'<img\b[^>]*>', _replace, html, flags=re.IGNORECASE)

    # 后台下载未缓存图片：每成功一张回调 on_image(full, local)。
    # 回调在线程池线程触发，调用方需自行切回主线程（QThTimer 事件模式天然线程安全）。
    if pending and session is not None and on_image is not None:
        def _run():
            max_workers = min(len(pending), 8)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_download, full): full for full in pending}
                for fut in as_completed(futures):
                    full = futures[fut]
                    try:
                        _, local = fut.result()
                    except Exception:
                        local = None
                    if local is not None and os.path.exists(local):
                        mapping[full] = local
                        try:
                            on_image(full, local)
                        except Exception:
                            pass
        threading.Thread(target=_run, daemon=True).start()
    return html


def _html_escape(s):
    """字符串转义，可安全放入 HTML 双引号属性。"""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _img_size_attr(local):
    """按本地图片实际尺寸计算 width/height 属性字符串；空串表示不设置。

    只缩放部分过大图片：原始尺寸超过 500x400 的等比缩放到限内；
    普通大小图片保持原尺寸显示（不写 width/height，Qt 按原图大小渲染）。
    """
    try:
        q = QImage(local)
        if not q.isNull():
            w = q.width()
            h = q.height()
            # 只对过大图片缩放：超过最大宽/高时等比缩放
            MAX_W, MAX_H = 500, 400
            if w > MAX_W or h > MAX_H:
                scale = min(MAX_W / w, MAX_H / h)
                w = max(1, int(w * scale))
                h = max(1, int(h * scale))
                return ' width="%d" height="%d"' % (w, h)
    except Exception:
        pass
    return ""


def _apply_md_image(html, full, local):
    """把 HTML 中标记为 data-mdimg="full" 的图片换成本地缓存图，并重算尺寸。"""
    key = _html_escape(full)

    def _one(m):
        tag = m.group(0)
        # 换 src 为本地文件
        tag = re.sub(
            r'(\bsrc\s*=\s*["\'])[^"\']+(["\'])',
            lambda m2: m2.group(1) + QUrl.fromLocalFile(local).toString() + m2.group(2),
            tag, flags=re.IGNORECASE)
        # 去掉占位标记与旧尺寸
        tag = re.sub(r'\s+data-mdimg\s*=\s*["\'][^"\']*["\']', '', tag, flags=re.IGNORECASE)
        tag = re.sub(r'\s+(?:width|height)\s*=\s*["\'][^"\']*["\']', '', tag, flags=re.IGNORECASE)
        # 按本地图实际尺寸
        size_attr = _img_size_attr(local)
        if size_attr:
            if re.search(r'/\s*>$', tag):
                tag = re.sub(r'/\s*>$', size_attr + '/>', tag)
            else:
                tag = re.sub(r'>$', size_attr + '>', tag)
        return tag

    return re.sub(
        r'<img\b[^>]*\bdata-mdimg\s*=\s*["\']' + re.escape(key) + r'["\'][^>]*>',
        _one, html, flags=re.IGNORECASE)


class Leftw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(None)
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.left.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.left.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width

       
class Mainw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.parent.parent.main.addWidget(self)

class Rightw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.right.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.right.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width


class Main():
    def __init__(self,app):
        self.app = app
    
        # 全局拦截滚动条右键菜单
        class _ScrollBarFilter(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.ContextMenu and isinstance(obj, QScrollBar):
                    return True
                return super().eventFilter(obj, event)
        self._scroll_bar_filter = _ScrollBarFilter()
        self.app.installEventFilter(self._scroll_bar_filter)

        for i in [
            "BML",
            "BML/logs",
            "BML/.Mindustrys"
        ]:
            os.makedirs(getPath(i), exist_ok=True)
        self.signals = self.Signals(self,self)
        self.winreg = self.Winreg(self, self)
        self.logger = self.Logger(self, self)
        self.logger.info("\n------------Book MDT Launcher------------"
                        f"\n-time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
                        f"\n-version: {init['version']}"
                        f"\n-BuildVersion: {init['BuildCode']}"
                        "\n-----------------------------------------")
        self.defsettings = {
            "language": None,
            "theme": 0,
            "maxLogNum": 50,
            "closeByTray": True,
            "defaultGame": None,
            "javaPath": None,
            "github": {
                "token_enc":None,
                "token_key":None,
                "useful": None,
                "user":{
                    "name":None,
                    "headurl":None
                },
                "rate": {
                    "core":   {"remaining": None, "reset": []},
                    "search": {"remaining": None, "reset": []}
                }
            },
            "javaPaths": [],
            "gameList": {"<:|default|:>": []}
        }
        self.settings = copy.deepcopy(self.defsettings)
        app.aboutToQuit.connect(self.saveSettings)

        def deep_merge_settings(default, file_settings):
            for key, value in file_settings.items():
                if key not in default:
                    continue
                if isinstance(default[key], dict) and isinstance(value, dict):
                    deep_merge_settings(default[key], value)
                else:
                    default[key] = value

        try:
            settings_path = getPath("BML/settings.json")
            if not os.path.exists(settings_path):
                self.logger.warning("settings file not found, using default settings")
            else:
                with open(settings_path, "r", encoding="utf-8") as f:
                    self.logger.info("loading settings...")
                    file_settings = json.load(f)
                    deep_merge_settings(self.settings, file_settings)
        except Exception as e:
            self.logger.error("ERR:Fail to load settings, using default setting"
                              "\n--Exception: " + str(e), exc_info=True)
            self.settings = copy.deepcopy(self.defsettings)
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    self.logger.warning("Error setting: \n" + str(e), exc_info=True)
            except:
                pass

        self.langer = self.Langer(self, self)
        # 工具模块日志 i18n：注入 langer.get 翻译函数（未注入时日志回退为 key 本身）
        javaDownload.set_tr_func(self.langer.get)
        mdt_set_tr_func(self.langer.get)
        self.logger._cleanup_old_logs()

        self.saveSettings()


        self.launcher = mdtLauncher(self, self.settings)
        self.githubAPI = GithubAPI()
        if self.settings["github"]["token_enc"]:
            raw = self._decrypt_settings_token()
            if raw:
                self.githubAPI.setToken(raw)
            QThTimer.task(
                0,
                lambda e: self.githubAPI.checkToken(),
                result_callback=self._on_startup_rate_check,
                dedicated=True   # 网络任务走独立线程，避免阻塞 QThTimer 共享线程（卡死所有 taskP）
            )


        self.signals.register("tokenVerified", Signal(bool, str, object))
        self.signals.register("gameRenovated", Signal())
        QThTimer.taskP(2000, self.gameRenovate, events=[lambda:self.signals.emit("gameRenovated"),self.saveSettings])
        QThTimer.task(0, self.gameRenovate, events=[lambda:self.signals.emit("gameRenovated"),self.saveSettings])

        self.tray = self.Tray(self, self)
        self.window = self.Window(self, self)

        # 后台预加载所有游戏数据到缓存，加速后续切换
        QThTimer.task(100, lambda event: mdtScanner.preload_all())

        # 退出统一清理：先停下载/后台线程（避免退出挂起与崩溃弹窗）
        app.aboutToQuit.connect(self._cleanup_on_quit)

        # Java 自动下载：启动时检索未完成的 Java 下载（.tmp/javaDownload.json）
        self.java_flow = None      # 启动延续流程实例（run 触发的下载由 launcher 内置管理）
        self._java_flow_cancelled = False   # 启动延续流程是否被用户取消（决定显示"已取消"还是"失败"）
        # launcher 内置 Java 自动下载：其信号直接驱动 UI 切页与状态显示
        self.launcher.java_missing.connect(lambda: self._java_show_status("missing"))
        self.launcher.java_status.connect(self._on_java_status)
        self.launcher.java_progress.connect(self._on_java_progress)
        self.launcher.java_extract_progress.connect(self._on_java_extract_progress)
        self.launcher.java_done.connect(self._on_java_download_done)
        self.launcher.java_cancelled.connect(self._on_java_cancelled)
        self.launcher.java_paused.connect(self._on_java_paused_changed)
        if javaDownload.get_status() in ("downloading", "extracting"):
            QTimer.singleShot(300, self._java_startup_resume)

        # mdt 游戏下载：启动时通过 MdtScanner 获取 downloadingMdts，逐个续传并同步暂停状态
        QTimer.singleShot(400, self._resume_mdt_downloads)

        # appdataCopy：启动时续传未完成的游戏数据保存（step=1 删除 / step=2 重做第二步）
        QTimer.singleShot(500, self._resume_appdata_saves)

    def gameRenovate(self, event):
        mdts = mdtScanner.getMdts()
        games = copy.deepcopy(self.settings["gameList"])
        changed = False
        for key, game_list in games.items():
            for game in list(game_list):
                if game in mdts:
                    mdts.remove(game)
                else:
                    game_list.remove(game)
                    changed = True
        if mdts:
            games.setdefault("<:|default|:>", []).extend(mdts)
            changed = True
        if changed:
            self.settings["gameList"] = games
            event.lambdas[0].emit()
            event.lambdas[1].emit()

    def _cleanup_on_quit(self):
        """应用退出前的统一清理（aboutToQuit 时执行）。

        顺序：隐藏托盘 → 停止下载线程 → 停止 QThTimer 后台线程 → 清理图片缓存。
        QThTimer.shutdown() 在模块内也连接了 aboutToQuit，重复调用是幂等的。
        """
        try:
            self.tray.hide()
        except Exception:
            pass
        # 取消 Java 下载/解压流程（保留 javaDownload.json，下次启动续传）
        try:
            self._java_cancel_all()
        except Exception:
            pass
        try:
            from src.utils.QDownloader import shutdown_all as _qd_shutdown_all
            _qd_shutdown_all()
        except Exception:
            pass
        try:
            QThTimer.shutdown()
        except Exception:
            pass
        # 删除 markdown 图片缓存（mdimg），下次渲染时重新下载
        try:
            import shutil
            mdimg = getPath("BML/.tmp/mdimg")
            if os.path.isdir(mdimg):
                shutil.rmtree(mdimg, ignore_errors=True)
        except Exception:
            pass

    # ==================== Java 自动下载流程 ====================
    def _java_bottom(self):
        """Start 页左栏 Bottom（QStackedWidget）：0=Start 1=Mod 2=World 3=Launch 4=Suspend。"""
        return self.window.main.main.start.left.main

    def _java_stack(self):
        """Start 页主区 stack（QStackedWidget）：0=Start 1=Mod 2=World 3=Launch 4=Log。"""
        return self.window.main.main.start.main.stack

    def _java_startup_resume(self):
        """程序启动时发现未完成的 Java 下载：切页并同步状态，接管续传。

        左 stacked（left.bottom）显示"正在下载未完成的Java..."，
        主区（right.main）同步切到 Launch 页，等待一秒后
        切换"正在下载Java"并拉起 QDownloader 实例，继续流程。
        """
        status = javaDownload.get_status()
        if status not in ("downloading", "extracting"):
            return
        self.logger.info(t(self.langer.get("log.java.resume_takeover"), status), name="Java")
        info = javaDownload.load_info() or {}
        # 同时切 left.bottom 与 right.main 到 Launch 页（唯一状态 label）
        try:
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            if status == "downloading":
                bottom.launch.setStatus("resume")      # 正在下载未完成的Java...
            else:
                bottom.launch.setStatus("extracting")  # 正在解压/部署Java...
        except Exception:
            pass
        # 等待一秒后，切换"正在下载Java"并拉起 QDownloader 续传
        def _resume_once():
            # 防重入：已有延续流程或 launcher 内置流程在下载时，不重复创建
            # （相同 dest 的 QDownloader 会因 task_id 冲突抛错）
            if self.java_flow is not None:
                return
            try:
                if self.launcher._java_flow is not None:
                    return
            except Exception:
                pass
            self._java_begin(resume=True)
        QTimer.singleShot(1000, _resume_once)

    def _java_begin(self, resume=False):
        """拉起 Java 下载流程（仅启动延续流程使用）。

        resume=True: 从 javaDownload.json 续传（程序启动延续流程）；
        点击开始游戏触发的自动下载由 launcher 内置管理。
        """
        if self.java_flow is not None:
            return
        self.logger.info(t(self.langer.get("log.java.flow_create"), resume), name="Java")
        flow = javaDownload.JavaDownloadFlow(resume=resume)
        self.java_flow = flow
        flow.status_changed.connect(self._on_java_status)
        flow.progress.connect(self._on_java_progress)
        flow.extract_progress.connect(self._on_java_extract_progress)
        flow.finished.connect(self._on_java_finished)
        flow.cancelled.connect(self._on_java_flow_cancelled)
        flow.paused_changed.connect(self._on_java_paused_changed)
        flow.error.connect(lambda msg: self.logger.error(t(self.langer.get("log.java.dl_error_prefix"), str(msg))))
        flow.start()

    def _on_java_status(self, status):
        """Java 下载/解压状态变化：left.bottom 与 right.main 都切到 Launch 页并更新 label。"""
        try:
            self.logger.info(t(self.langer.get("log.java.status_change"), status), name="Java")
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            bottom.launch.setStatus(status)
        except Exception as e:
            print("[java_ui_status]", status, "ERR:", repr(e))

    def _on_java_progress(self, done, total):
        """下载字节进度 → label 显示百分比（如 正在下载Java... 45%）。"""
        try:
            pct = int(done * 100 / total) if total else 0
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            bottom.launch.setStatus("downloading", pct)
        except Exception as e:
            print("[java_ui_progress]", done, total, "ERR:", repr(e))

    def _on_java_extract_progress(self, done, total):
        """解压进度 → label 显示百分比（如 正在解压Java... 45%）。"""
        try:
            pct = int(done * 100 / total) if total else 0
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            bottom.launch.setStatus("extracting", pct)
        except Exception as e:
            print("[java_ui_extract]", done, total, "ERR:", repr(e))

    def _on_java_paused_changed(self, paused, pct):
        """Java 下载暂停/恢复 → label 显示"Java暂停下载 n%"或恢复"正在下载Java n%"。"""
        try:
            _state = self.langer.get("log.java.paused_state" if paused else "log.java.resumed_state")
            self.logger.info(t(self.langer.get("log.java.paused_change"), _state, pct), name="Java")
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            if paused:
                bottom.launch.setStatus("paused", pct)
            else:
                bottom.launch.setStatus("downloading", pct)
        except Exception as e:
            print("[java_ui_paused]", paused, pct, "ERR:", repr(e))

    def _on_java_flow_cancelled(self):
        """启动延续流程的下载被用户取消（下载列表页/退出）：记录标记。"""
        self.logger.info(self.langer.get("log.java.flow_cancelled"), name="Java")
        self._java_flow_cancelled = True

    def _on_java_cancelled(self):
        """launcher 内置 Java 下载被用户取消：显示"已取消"，一秒后回主界面。"""
        self.logger.info(self.langer.get("log.java.dl_cancelled_show"), name="Java")
        self._java_show_status("cancelled")
        QTimer.singleShot(1000, self._java_go_home)

    def _on_java_finished(self, ok):
        """启动延续流程结束：显示"Java部署完成/失败/已取消"，等待一秒后返回主界面。

        （run 触发的下载由 launcher 内置管理，其 java_done 信号走 _on_java_download_done）
        """
        flow = self.java_flow
        self.java_flow = None   # 释放流程引用（QDownloader 已完成并注销）
        if flow is not None:
            try:
                flow.shutdown()   # 确保下载/解压线程完全退出后再释放
            except Exception:
                pass
        cancelled = self._java_flow_cancelled
        self._java_flow_cancelled = False
        self.logger.info(t(self.langer.get("log.java.flow_finished"), ok, cancelled), name="Java")
        if ok:
            self._java_show_status("done")
        elif cancelled:
            self._java_show_status("cancelled")   # 用户主动取消，不误报"下载失败"
        else:
            self._java_show_status("error")
        QTimer.singleShot(1000, self._java_go_home)

    def _on_java_download_done(self, ok):
        """launcher 内置 Java 下载流程结束：显示结果，一秒后由 launcher 自动重新 run 或回主界面。

        ok=True：launcher 内部已刷新 Java 设置并重新启动游戏（game_launched 信号会切页）；
        ok=False：显示失败，一秒后回主界面。
        """
        self.logger.info(t(self.langer.get("log.java.dl_finished_show"), ok), name="Java")
        if ok:
            self._java_show_status("done")
        else:
            self._java_show_status("error")
            QTimer.singleShot(1000, self._java_go_home)

    def _java_show_status(self, status):
        """left.bottom 与 right.main 都切到 Launch 页并更新唯一状态 label。"""
        try:
            bottom = self._java_bottom()
            bottom.setCurrentIndex(3)
            self._java_stack().setCurrentIndex(3)
            bottom.launch.setStatus(status)
        except Exception as e:
            print("[java_ui_show]", status, "ERR:", repr(e))

    def _java_go_home(self):
        """返回主界面（左 stacked 与主区均回到 Start 页）。"""
        try:
            self._java_bottom().setCurrentIndex(0)
            self._java_stack().setCurrentIndex(0)
        except Exception:
            pass

    def _java_cancel_all(self):
        """取消当前 Java 下载流程（用户手动取消/退出时）。

        仅当确实存在流程时才打印日志并执行取消，避免退出时产生误导性日志。
        """
        flow = self.java_flow
        self.java_flow = None
        lf = None
        try:
            lf = self.launcher._java_flow
            self.launcher._java_flow = None
        except Exception:
            pass
        if flow is None and lf is None:
            # 没有任何流程，无需打印"取消全部流程"
            return
        self.logger.info(self.langer.get("log.java.cancel_all"), name="Java")
        if flow is not None:
            try:
                flow.cancel()
            except Exception:
                pass
        if lf is not None:
            try:
                lf.cancel()
            except Exception:
                pass

    def _resume_appdata_saves(self):
        """启动时续传未完成的 appdataCopy 保存任务（launcher 内部处理 step=1/step=2）。"""
        try:
            self.launcher.resume_appdata_saves()
        except Exception as e:
            self.logger.warning(t(self.langer.get("log.appdata.resume_scan_error"), repr(e)))

    def _resume_mdt_downloads(self):
        """启动续传所有未完成的 mdt 游戏下载（downloading.json 记录），并同步暂停状态。

        通过 mdtScanner.getDownloadingMdts() 获取下载中列表；
        有 .tmp/<task_id>/state.json → continue_task 续传；否则用 downloading.json
        的 url/dest 新建任务；downloading.json 记录 paused=true 时创建后立即暂停。
        """
        try:
            downloading = mdtScanner.getDownloadingMdts() or {}
        except Exception as e:
            self.logger.warning(t(self.langer.get("log.dl.mdt_scan_error"), repr(e)))
            return
        if not downloading:
            return
        if not hasattr(self, "_mdt_downloads"):
            self._mdt_downloads = []
        for name, info in downloading.items():
            dest = info.get("dest") or ""
            url = info.get("url") or ""
            if not (dest and url):
                continue
            task_id = hashlib.md5(dest.encode("utf-8")).hexdigest()
            paused = bool(info.get("paused"))
            try:
                if task_id in QDownloader.get_active_tasks():
                    continue
                try:
                    dl = QDownloader.continue_task(task_id)
                except Exception:
                    dl = QDownloader(url=url, dest_path=dest, num_threads=4, chunk_size_mb=4, title=info.get("title") or name)
                    dl.start()
                if paused:
                    dl.pause()   # 同步暂停状态：线程进入下载循环后在安全点等待
                dl.finished.connect(lambda ok, d=dl, n=name: self._on_mdt_download_finished(d, n, ok))
                self._mdt_downloads.append(dl)
                self.logger.info(t(self.langer.get("log.dl.mdt_resume_start"), name, paused))
            except Exception as e:
                self.logger.warning(t(self.langer.get("log.dl.mdt_resume_error"), name, repr(e)))

    def _on_mdt_download_finished(self, dl, name, ok):
        """启动续传任务收尾：释放 QDownloader；成功后刷新 BML.json 并删除 downloading.json。"""
        try:
            dl.wait_thread(5000)
            dl.deleteLater()
        except Exception:
            pass
        try:
            if dl in self._mdt_downloads:
                self._mdt_downloads.remove(dl)
        except Exception:
            pass
        if not ok:
            self.logger.error(t(self.langer.get("log.dl.mdt_finished_fail"), name))
            return
        try:
            mdtScanner._retrieve_mdt_data(name)
            dfile = getPath("BML/.Mindustrys/%s/downloading.json" % name)
            if os.path.isfile(dfile):
                os.remove(dfile)
            mdtScanner.invalidate_cache()
            self.logger.info(t(self.langer.get("log.dl.mdt_finished_ok"), name))
        except Exception as e:
            self.logger.error(t(self.langer.get("log.dl.mdt_finished_clean_err"), name, repr(e)))

    _OBF_BYTE = 0x5A

    @classmethod
    def _obf_store(cls, s):
        """固定 XOR → base64，settings 存储前混淆"""
        return base64.b64encode(
            bytes(b ^ cls._OBF_BYTE for b in s.encode())
        ).decode()

    @classmethod
    def _deobf_store(cls, s):
        """逆向：base64 解码 → XOR 还原"""
        b = base64.b64decode(s)
        return bytes(byte ^ cls._OBF_BYTE for byte in b).decode()

    def _encrypt_settings_token(self, raw):
        enc, key = GithubAPI._encrypt(raw)
        self.settings["github"]["token_enc"] = Main._obf_store(enc)
        self.settings["github"]["token_key"] = Main._obf_store(key)

    def _decrypt_settings_token(self):
        return GithubAPI._decrypt(
            Main._deobf_store(self.settings["github"]["token_enc"]),
            Main._deobf_store(self.settings["github"]["token_key"])
        )

    def _on_startup_rate_check(self, result):
        ok, error_type, data = result
        if ok:
            rate = self.githubAPI.rate
            s = self.settings["github"]
            s["rate"]["core"] = {"remaining": rate["core"]["remaining"], "reset": rate["core"]["reset"]}
            s["rate"]["search"] = {"remaining": rate["search"]["remaining"], "reset": rate["search"]["reset"]}
            s["useful"] = True
        elif error_type == "auth":
            self.githubAPI.setToken(None)
            s = self.settings["github"]
            s["token_enc"] = None
            s["token_key"] = None
            s["useful"] = None
            s["user"] = {"name": None, "headurl": None}
        self.saveSettings()
        self.signals.emit("tokenVerified", ok, error_type, data)

    def setTheme(self,theme):
        self.settings["theme"] = 1 if theme else 0
        self.apply_theme()

    def saveSettings(self):
        try:
            settings_path = getPath("BML/settings.json")
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, separators=(',', ':'), ensure_ascii=False)
            try:
                self.logger.info(self.langer.get("log.info.savesettings"))
            except:
                self.logger.info("Settings saved")
        except Exception as e:
            try:
                self.logger.error(self.langer.get("log.error.savesettings") + "\n--Exception: " + str(e), exc_info=True)
            except:
                self.logger.error("Failed to save settings\n--Exception: " + str(e), exc_info=True)

    def apply_theme(self):
        is_light = bool(self.settings["theme"])
        theme_file = "light.qss" if is_light else "dark.qss"

        qss = ""
        with open(getPath(f"src/resources/styles/{theme_file}"), "r", encoding="utf-8") as f:
            qss = f.read()

        app = QApplication.instance()
        if app:
            app.setStyleSheet(qss)
            self.logger.debug(f"Loading QtStyleSheet from {theme_file}:\n{qss} ")

        font = QFont()
        font.setFamily("Microsoft Yahei")
        font.setPointSize(8)
        app.setFont(font)

        # 递归调用所有子控件的 lighting 函数（图标换色）
        def notify_lighting(widget, state):
            if hasattr(widget, 'lighting') and callable(widget.lighting):
                try:
                    widget.lighting(state)
                except Exception as e:
                    self.logger.error(f"Error calling lighting on {widget}: {e}")
            for child in widget.children():
                notify_lighting(child, state)

        notify_lighting(self.window, is_light)
        self.logger.info(t(self.langer.get("log.info.changetheme"), "light" if is_light else "dark"))

    class Window(QWidget):
        def __init__(self, parent=None, root=None):
            super().__init__()
            self.parent = parent
            self.root = root



            self.server = QLocalServer(self)
            QLocalServer.removeServer("BookMdtLauncherMI")
            if self.server.listen("BookMdtLauncherMI"):
                self.server.newConnection.connect(self.showS)



            self.root.logger.debug("init QW.window")
            self.root.window = self
            self.setMinimumSize(QSize(600, 450))

            self.installEventFilter(self)

            self._last_window_state = Qt.WindowNoState

            self.init_ui()
            self.init_wid()

            self.root.apply_theme()

            self.root.logger.info(self.root.langer.get("log.info.windowLoad"))

        def init_ui(self):
            self.setWindowTitle("Book MDT Launcher")
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setGeometry(50, 50, 700, 500)

        def changeEvent(self, event):
            if event.type() == QEvent.WindowStateChange:
                if not self.isMinimized():
                    self._last_window_state = self.windowState()
                    # 同步最大化/还原按钮图标。
                    # 不依赖 nativeEvent（PySide6 下 eventType 是 QByteArray，
                    # Windows 消息分支不可靠），Qt 自身的窗口状态变化一定触发这里。
                    try:
                        tbt = self.main.top.tbt_max
                        maximized = self.isMaximized()
                        self.root.logger.debug(f"window state changed, maximized={maximized}")
                        tbt.setLogo(1 if maximized else 0)
                    except Exception:
                        pass
            super().changeEvent(event)

        def restore_from_tray(self):
            self.show()
            if self.isMinimized():
                # 最小化
                if self._last_window_state == Qt.WindowMaximized:
                    self.showMaximized()
                else:
                    self.showNormal()
            else:
                # 提层
                self.raise_()
            self.activateWindow()

        def showS(self):
            conn = self.server.nextPendingConnection()
            if conn:
                conn.readyRead.connect(self._on_read_data)
                conn.disconnected.connect(conn.deleteLater)

        def _on_read_data(self):
            conn = self.sender()
            data = conn.readAll()
            if data == QByteArray(b"MAINWINSHOW"):
                self.restore_from_tray()
            conn.disconnectFromServer()
            conn.deleteLater()

        def init_wid(self):
            self.floatingStack = self.FloatingStack(self, self.root)
            self.root.logger.debug("init QW.window.left")
            self.left = self.Left(self, self.root)
            self.root.logger.debug("init QW.window.lline")
            self.lline = self.LLine(self, self.root)

            self.root.logger.debug("init QW.windowL")
            self.layout = QHBoxLayout(self)
            self.layout.setAlignment(Qt.AlignLeft)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

            self.root.logger.debug("init QW.windowL.stren")
            self.stren = QWidget()
            self.stren.setFixedWidth(41)
            self.layout.addWidget(self.stren, 0)

            self.root.logger.debug("init QW.windowL.main")
            self.main = self.Main(self, self.root)
            self.layout.addWidget(self.main, 1)

            self.left.raise_()
            self.lline.raise_()

            self.floatingStack.raise_()

            self.githubSetting = self.GithubSetting(self, self.root)

        def eventFilter(self, obj, event):
            if obj is self and event.type() == QEvent.Resize:
                new_width = self.left.width()  # 假设宽度固定，或者从配置读取
                self.left.setGeometry(0, 0, new_width, self.height())
                self.lline.init_ui()

                self.root.logger.debug(f"Window resized via filter: {self.width()}x{self.height()}")

            return super().eventFilter(obj, event)

        def nativeEvent(self, eventType, message):
            """
            拦截 Windows 原生消息
            """
            # 判断是否是 Windows 消息
            # PySide6: eventType 是 QByteArray（b"windows_generic_MSG"）；PyQt5 是 str。
            # 直接比较 str 在 PySide6 下恒为 False，导致整个分支（含最大化检测）失效。
            if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
                # PySide6: message 已是 int（内存地址）；PyQt5 是 sip.voidptr，int() 两者通用
                msg = ctypes.wintypes.MSG.from_address(int(message))

                #
                if msg.message == 0x0084:
                    if not self.isMaximized() and not self.githubSetting.isVisible():
                        # 获取鼠标在屏幕上的坐标
                        pos = self.mapFromGlobal(QCursor.pos())
                        x, y = pos.x(), pos.y()
                        w, h = self.width(), self.height()

                        border_width = 5
                        result = 1

                        if x < border_width:
                            if y < border_width:
                                result = 13
                            elif y > h - border_width:
                                result = 16
                            else:
                                result = 10
                        elif x > w - border_width:
                            if y < border_width:
                                result = 14
                            elif y > h - border_width:
                                result = 17
                            else:
                                result = 11
                        elif y < border_width:
                            result = 12
                        elif y > h - border_width:
                            result = 15

                        return True, result

                # 托盘主题切换
                elif msg.message in (0x001A, 0x0320):
                    QTimer.singleShot(100, self.root.tray.setIcon_)

                # 最大化检测
                elif msg.message == 0x0005:
                    if msg.wParam == 2:
                        self.root.logger.debug("window maximized")
                        self.main.top.tbt_max.setLogo(1)
                    elif msg.wParam == 0:
                        self.root.logger.debug("window unmaximized")
                        self.main.top.tbt_max.setLogo(0)

            # 3. 其他消息交给默认处理
            return super().nativeEvent(eventType, message)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.githubSetting.setGeometry(0,0,self.width(),self.height())
            self.floatingStack.setGeometry(0,40,self.width(),self.height()-40)
            

        class GithubSetting(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.init_ui()
                self.init_wid()
                self.hide()

            def init_ui(self):
                self.setGeometry(self.geometry())
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setProperty("wid_", "_window.github")
                self.setStyleSheet('QWidget[wid_="_window.github"]{background-color: rgba(0,0,0,0.5);}')

            def init_wid(self):
                self.l = QHBoxLayout(self)
                self.l.setContentsMargins(0, 0, 0, 0)
                self.l.setSpacing(0)
                self.l.setAlignment(Qt.AlignCenter)

                self.panel = self.Panel(self, self.root)
                self.l.addWidget(self.panel,0)

            def showEvent(self, event):
                # 显示时提层，盖过 floatingStack 等覆盖控件
                super().showEvent(event)
                self.raise_()

            def _sync_rate_from_api(self):
                """将 GithubAPI 中的实时 rate 同步到 settings 内存（不写盘）。"""
                rate = self.root.githubAPI.rate
                s = self.root.settings["github"]
                s["rate"]["core"] = {
                    "remaining": rate["core"]["remaining"],
                    "reset": rate["core"]["reset"]
                }
                s["rate"]["search"] = {
                    "remaining": rate["search"]["remaining"],
                    "reset": rate["search"]["reset"]
                }

            def _clear_token_data(self):
                """清除 settings 中所有 token 相关数据（仅当 token 确认无效时调用）。"""
                self.root.githubAPI.setToken(None)
                s = self.root.settings["github"]
                s["token_enc"] = None
                s["token_key"] = None
                s["useful"] = None
                s["user"] = {"name": None, "headurl": None}

            def _debounce_save_settings(self):
                """延迟 500ms 写盘，合并高频写入。"""
                if hasattr(self, '_save_timer'):
                    self._save_timer.stop()
                else:
                    self._save_timer = QTimer(self)
                    self._save_timer.setSingleShot(True)
                    self._save_timer.timeout.connect(self.root.saveSettings)
                self._save_timer.start(500)

            class Panel(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.githubAPI = self.root.githubAPI
                    self.init_ui()
                    self.init_wid()
                    self.githubAPI.refreshed.connect(self._on_rate_refreshed)
                    

                def init_ui(self):
                    self.setFixedSize(520,365)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def _on_rate_refreshed(self):
                    self.parent._sync_rate_from_api()
                    if self.isVisible():
                        self.body.content._update_rate_section()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.top = self.Top(self, self.root)
                    self.layout.addWidget(self.top,0)
                    
                    self.line = QWidget(self)
                    self.line.setFixedHeight(1)
                    self.line.setProperty("wid","line")
                    self.layout.addWidget(self.line,0)

                    self.body = self.Body(self, self.root)
                    self.layout.addWidget(self.body,1)


                class Top(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedHeight(30)
                        self.setAttribute(Qt.WA_StyledBackground, True)

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(30, 0, 0, 0)
                        self.layout.setSpacing(0)
                        self.layout.setAlignment(Qt.AlignLeft)

                        self.title = QLabel("GitHub")
                        self.title.setProperty("wid", "title")
                        self.title.setStyleSheet("font-size: 16px;")
                        self.layout.addWidget(self.title,0)

                        self.layout.addStretch(1)

                        self.close = self.Close(self, self.root)
                        self.layout.addWidget(self.close,0)

                        self.close.clicked.connect(self.parent.parent.hide)

                    class Close(QPushButton):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.init_ui()

                        def init_ui(self):
                            self.setFixedSize(30, 30)
                            self.setProperty("wid", "tbtn")
                        
                        def lighting(self, light: bool):
                            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                            logo = change_color(getPath("src/assets/tribtns/close.png"),color)
                            icon = QIcon(logo.pixmap(30,30))

                            self.setIcon(icon)

                class Body(QWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.init_wid()

                    def init_wid(self):
                        self.layout = QVBoxLayout(self)
                        self.layout.setContentsMargins(0, 0, 0, 0)
                        self.layout.setSpacing(0)

                        self.scroll = QScrollArea(self)
                        self.scroll.setWidgetResizable(True)
                        self.scroll.setFrameShape(QFrame.NoFrame)
                        self.layout.addWidget(self.scroll)

                        self.content = self.Content(self, self.root)
                        self.scroll.setWidget(self.content)

                    class Content(QWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent)
                            self.parent = parent
                            self.root = root
                            self._gs = parent.parent.parent
                            self._editing = False
                            self.init_wid()
                            self.langing()

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(20,20,20,20)
                            self.layout.setSpacing(10)
                            self.layout.setAlignment(Qt.AlignTop)


                            self.l1w = QWidget()
                            self.l1w.setFixedHeight(84)
                            self.layout.addWidget(self.l1w,0)
                            
                            self.l1 =QHBoxLayout(self.l1w)
                            self.l1.setContentsMargins(0, 0, 0, 0)
                            self.l1.setSpacing(0)

                            self.headIcon = QLabel()
                            self.headIcon.setProperty("wid","png")
                            self.headIcon.setFixedSize(84,84)
                            self.headIcon.setStyleSheet("border-radius:42px;")
                            self.l1.addWidget(self.headIcon,0)

                            self.l1_l1w = QWidget()
                            self.l1.addWidget(self.l1_l1w,1)

                            self.l1_l1 = QVBoxLayout(self.l1_l1w)
                            self.l1_l1.setContentsMargins(10, 0, 0, 0)
                            self.l1_l1.setSpacing(5)
                            self.l1_l1.setAlignment(Qt.AlignTop)

                            self.userName = QLabel("User-Name")
                            self.userName.setProperty("wid","text")
                            self.userName.setStyleSheet("font-size: 22px;")
                            self.userName.setAlignment(Qt.AlignLeft)
                            self.userName.setFixedHeight(24)
                            self.l1_l1.addWidget(self.userName,0)

                            self.tokenStatus = QLabel("")
                            self.tokenStatus.setProperty("wid","title")
                            self.tokenStatus.setStyleSheet("font-size: 11px;")
                            self.tokenStatus.setAlignment(Qt.AlignLeft)
                            self.tokenStatus.setFixedHeight(14)
                            self.l1_l1.addWidget(self.tokenStatus,0)

                            self.l1_l1_l1w = QWidget()
                            self.l1_l1.addWidget(self.l1_l1_l1w,1)

                            self.l1_l1_l1 = QHBoxLayout(self.l1_l1_l1w)
                            self.l1_l1_l1.setContentsMargins(0, 0, 0, 0)
                            self.l1_l1_l1.setSpacing(5)

                            self.coreBadge = QLabel()
                            self.coreBadge.setProperty("wid","badge")
                            self.coreBadge.setFixedHeight(20)
                            self.l1_l1_l1.addWidget(self.coreBadge,0)

                            self.searchBadge = QLabel()
                            self.searchBadge.setProperty("wid","badge")
                            self.searchBadge.setFixedHeight(20)
                            self.l1_l1_l1.addWidget(self.searchBadge,0)

                            self.l1_l1_l1.addStretch(1)

                            self.layout.addSpacing(14)

                            self.tokenTips = QWidget()
                            self.tokenTips.setStyleSheet(
                                "QWidget#tokenTips{"
                                "background-color: rgba(255, 255, 0, 50);"
                                "border: 1px solid orange;"
                                "border-radius: 4px;"
                                "}"
                            )
                            self.tokenTips.setObjectName("tokenTips")
                            tips_l = QHBoxLayout(self.tokenTips)
                            tips_l.setContentsMargins(6, 5, 6, 5)
                            tips_l.setSpacing(6)

                            self.tokenTipsIcon = QLabel()
                            self.tokenTipsIcon.setFixedSize(18, 18)
                            self.tokenTipsIcon.setScaledContents(True)
                            tips_l.addWidget(self.tokenTipsIcon, 0, Qt.AlignTop)

                            self.tokenTipsText = QLabel()
                            self.tokenTipsText.setProperty("wid", "text")
                            self.tokenTipsText.setStyleSheet("font-size: 10px;")
                            self.tokenTipsText.setWordWrap(True)
                            tips_l.addWidget(self.tokenTipsText, 1)

                            self.layout.addWidget(self.tokenTips, 0)

                            self.layout.addSpacing(8)

                            self.tokenTitle = QLabel()
                            self.tokenTitle.setProperty("wid","text")
                            self.tokenTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                            self.tokenTitle.setFixedHeight(18)
                            self.layout.addWidget(self.tokenTitle,0)

                            self.tokenStack = QStackedWidget()
                            self.tokenStack.setFixedHeight(32)
                            self.layout.addWidget(self.tokenStack,0)

                            self.tokenInputW = QWidget()
                            self.tokenInputL = QHBoxLayout(self.tokenInputW)
                            self.tokenInputL.setContentsMargins(0, 0, 0, 0)
                            self.tokenInputL.setSpacing(5)

                            self.tokenInput = QLineEdit()
                            self.tokenInput.setProperty("wid","input")
                            self.tokenInput.setFixedHeight(28)
                            self.tokenInputL.addWidget(self.tokenInput,1)

                            self.tokenSaveBtn = QPushButton()
                            self.tokenSaveBtn.setProperty("wid","btn")
                            self.tokenSaveBtn.setFixedSize(44,28)
                            self.tokenSaveBtn.clicked.connect(self._save_token)
                            self.tokenInputL.addWidget(self.tokenSaveBtn,0)

                            self.tokenCancelBtn = QPushButton()
                            self.tokenCancelBtn.setProperty("wid","btn")
                            self.tokenCancelBtn.setFixedSize(54,28)
                            self.tokenCancelBtn.clicked.connect(self._cancel_edit)
                            self.tokenCancelBtn.setVisible(False)
                            self.tokenInputL.addWidget(self.tokenCancelBtn,0)

                            self.tokenStack.addWidget(self.tokenInputW)

                            self.tokenDisplayW = QWidget()
                            self.tokenDisplayL = QHBoxLayout(self.tokenDisplayW)
                            self.tokenDisplayL.setContentsMargins(0, 0, 0, 0)
                            self.tokenDisplayL.setSpacing(5)

                            self.tokenMaskedLabel = QLabel()
                            self.tokenMaskedLabel.setProperty("wid","title")
                            self.tokenMaskedLabel.setStyleSheet("font-size: 12px;")
                            self.tokenMaskedLabel.setFixedHeight(28)
                            self.tokenDisplayL.addWidget(self.tokenMaskedLabel,1)

                            self.tokenEditBtn = QPushButton()
                            self.tokenEditBtn.setProperty("wid","btn")
                            self.tokenEditBtn.setFixedSize(60,28)
                            self.tokenEditBtn.clicked.connect(self._start_edit)
                            self.tokenDisplayL.addWidget(self.tokenEditBtn,0)

                            self.tokenClearBtn = QPushButton()
                            self.tokenClearBtn.setProperty("wid","btn")
                            self.tokenClearBtn.setFixedSize(60,28)
                            self.tokenClearBtn.clicked.connect(self._clear_token)
                            self.tokenDisplayL.addWidget(self.tokenClearBtn,0)

                            self.tokenStack.addWidget(self.tokenDisplayW)

                            self.tokenMsg = QLabel()
                            self.tokenMsg.setProperty("wid","title")
                            self.tokenMsg.setStyleSheet("font-size: 10px;")
                            self.tokenMsg.setFixedHeight(14)
                            self.layout.addWidget(self.tokenMsg,0)

                            self.tokenTestBtnW = QWidget()
                            self.tokenTestBtnL = QHBoxLayout(self.tokenTestBtnW)
                            self.tokenTestBtnL.setContentsMargins(0, 0, 0, 0)
                            self.tokenTestBtnL.setSpacing(5)

                            self.tokenTestBtn = QPushButton()
                            self.tokenTestBtn.setProperty("wid","btn")
                            self.tokenTestBtn.setFixedSize(90,26)
                            self.tokenTestBtn.clicked.connect(self._test_token)
                            self.tokenTestBtnL.addWidget(self.tokenTestBtn,0)

                            self.tokenLatencyBtn = QPushButton()
                            self.tokenLatencyBtn.setProperty("wid","btn")
                            self.tokenLatencyBtn.setFixedSize(90,26)
                            self.tokenLatencyBtn.clicked.connect(self._test_latency)
                            self.tokenTestBtnL.addWidget(self.tokenLatencyBtn,0)

                            self.tokenTestBtnL.addStretch(1)
                            self.layout.addWidget(self.tokenTestBtnW,0)

                            self.layout.addSpacing(8)

                            self.rateTitle = QLabel()
                            self.rateTitle.setProperty("wid","text")
                            self.rateTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                            self.rateTitle.setFixedHeight(18)
                            self.layout.addWidget(self.rateTitle,0)

                            self.rateCoreW = QWidget()
                            self.rateCoreL = QHBoxLayout(self.rateCoreW)
                            self.rateCoreL.setContentsMargins(0, 0, 0, 0)
                            self.rateCoreL.setSpacing(10)

                            self.rateCoreLabel = QLabel()
                            self.rateCoreLabel.setProperty("wid","text")
                            self.rateCoreLabel.setStyleSheet("font-size: 11px;")
                            self.rateCoreLabel.setFixedHeight(16)
                            self.rateCoreL.addWidget(self.rateCoreLabel,0)

                            self.rateCoreValue = QLabel()
                            self.rateCoreValue.setProperty("wid","title")
                            self.rateCoreValue.setStyleSheet("font-size: 11px;")
                            self.rateCoreValue.setFixedHeight(16)
                            self.rateCoreL.addWidget(self.rateCoreValue,1)

                            self.layout.addWidget(self.rateCoreW,0)

                            self.rateSearchW = QWidget()
                            self.rateSearchL = QHBoxLayout(self.rateSearchW)
                            self.rateSearchL.setContentsMargins(0, 0, 0, 0)
                            self.rateSearchL.setSpacing(10)

                            self.rateSearchLabel = QLabel()
                            self.rateSearchLabel.setProperty("wid","text")
                            self.rateSearchLabel.setStyleSheet("font-size: 11px;")
                            self.rateSearchLabel.setFixedHeight(16)
                            self.rateSearchL.addWidget(self.rateSearchLabel,0)

                            self.rateSearchValue = QLabel()
                            self.rateSearchValue.setProperty("wid","title")
                            self.rateSearchValue.setStyleSheet("font-size: 11px;")
                            self.rateSearchValue.setFixedHeight(16)
                            self.rateSearchL.addWidget(self.rateSearchValue,1)

                            self.layout.addWidget(self.rateSearchW,0)

                            self.layout.addStretch(1)

                        def langing(self):
                            self.tokenTipsIcon.setPixmap(change_color(getPath("src/assets/actions/tips.png"), QColor(255, 165, 0)).pixmap(QSize(18, 18)))
                            self.tokenTipsText.setText(self.root.langer.get("github.settings.tokenTips"))
                            self.tokenTitle.setText(self.root.langer.get("github.settings.tokenTitle"))
                            self.tokenSaveBtn.setText(self.root.langer.get("text.save"))
                            self.tokenCancelBtn.setText(self.root.langer.get("text.cancel"))
                            self.tokenEditBtn.setText(self.root.langer.get("text.edit"))
                            self.tokenClearBtn.setText(self.root.langer.get("text.clear"))
                            self.tokenTestBtn.setText(self.root.langer.get("github.settings.testToken"))
                            self.tokenLatencyBtn.setText(self.root.langer.get("github.settings.testLatency"))
                            self.rateTitle.setText(self.root.langer.get("github.settings.rateTitle"))
                            self.rateCoreLabel.setText(self.root.langer.get("github.settings.rateCore"))
                            self.rateSearchLabel.setText(self.root.langer.get("github.settings.rateSearch"))
                            self._refresh_ui()

                        def showEvent(self, event):
                            super().showEvent(event)
                            self._refresh_ui()

                        def _refresh_ui(self):
                            token = self.root.settings["github"]["token_enc"]
                            self._update_user_section()
                            self._update_token_section(token)
                            self._update_rate_section()

                        def _update_user_section(self):
                            user = self.root.settings["github"]["user"]
                            name = user.get("name") if user else None
                            headurl = user.get("headurl") if user else None

                            if name:
                                self.userName.setText(name)
                                self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                if headurl:
                                    self._load_avatar(headurl)
                                else:
                                    self.headIcon.clear()
                            elif self.root.settings["github"]["token_enc"] and self.root.settings["github"]["useful"] is False:
                                self.userName.setText(self.root.langer.get("github.settings.notLoggedIn"))
                                self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.invalid"))
                                self.headIcon.clear()
                            elif self.root.settings["github"]["token_enc"]:
                                self.userName.setText(self.root.langer.get("text.loading"))
                                self.tokenStatus.setText("")
                                self.headIcon.clear()
                            else:
                                self.userName.setText(self.root.langer.get("github.settings.notLoggedIn"))
                                self.tokenStatus.setText(self.root.langer.get("github.settings.tokenStatus.none"))
                                self.headIcon.clear()

                        def _load_avatar(self, url):
                            def _fetch():
                                # 复用 githubAPI 的 session：走系统代理 + 合并 CA bundle
                                # （裸 requests.get 无法访问 avatars.githubusercontent.com）
                                try:
                                    session = getattr(self.root, "githubAPI", None)
                                    sess = getattr(session, "_session", None)
                                    if sess is not None:
                                        resp = sess.get(url, timeout=10)
                                    else:
                                        import requests as _req
                                        resp = _req.get(url, timeout=10)
                                    if resp.status_code == 200:
                                        return resp.content
                                except Exception:
                                    pass
                                return None
                            def _set_round(data):
                                # 主线程创建 QPixmap（QPixmap 是 GUI 类，禁止在子线程创建）
                                if not data:
                                    return
                                pix = QPixmap()
                                if not pix.loadFromData(data):
                                    return
                                scaled = pix.scaled(78, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                round_pix = QPixmap(78, 78)
                                round_pix.fill(Qt.transparent)
                                painter = QPainter(round_pix)
                                painter.setRenderHint(QPainter.Antialiasing)
                                path = QPainterPath()
                                path.addEllipse(0, 0, 78, 78)
                                painter.setClipPath(path)
                                offset_x = (78 - scaled.width()) // 2
                                offset_y = (78 - scaled.height()) // 2
                                painter.drawPixmap(offset_x, offset_y, scaled)
                                painter.end()
                                self.headIcon.setPixmap(round_pix)
                            QThTimer.task(0, lambda e,_url=url: _fetch(), result_callback=_set_round, dedicated=True)

                        def _update_token_section(self, token):
                            if self._editing:
                                return
                            if token:
                                self.tokenStack.setCurrentIndex(1)
                                masked = self.root.githubAPI.getMaskedToken()
                                self.tokenMaskedLabel.setText(masked if masked else "****")
                                self.tokenMsg.setText("")
                            else:
                                self.tokenStack.setCurrentIndex(0)
                                self.tokenInput.clear()
                                self.tokenMsg.setText("")

                        def _update_rate_section(self):
                            rate = self.root.githubAPI.rate
                            core = rate.get("core", {})
                            search = rate.get("search", {})

                            core_rem = core.get("remaining")
                            search_rem = search.get("remaining")
                            core_reset = core.get("reset", [])
                            search_reset = search.get("reset", [])

                            if core_rem is not None:
                                self.coreBadge.setText(f"Core: {core_rem}")
                                self.coreBadge.setVisible(True)
                                reset_str = ""
                                if len(core_reset) == 6:
                                    reset_str = f"{core_reset[0]}-{core_reset[1]:02d}-{core_reset[2]:02d} {core_reset[3]:02d}:{core_reset[4]:02d}:{core_reset[5]:02d}"
                                self.rateCoreValue.setText(
                                    f"{self.root.langer.get('github.settings.rateRemaining')}: {core_rem}   "
                                    f"{self.root.langer.get('github.settings.rateReset')}: {reset_str}"
                                )
                            else:
                                self.coreBadge.setVisible(False)
                                self.rateCoreValue.setText("")

                            if search_rem is not None:
                                self.searchBadge.setText(f"Search: {search_rem}")
                                self.searchBadge.setVisible(True)
                                reset_str = ""
                                if len(search_reset) == 6:
                                    reset_str = f"{search_reset[0]}-{search_reset[1]:02d}-{search_reset[2]:02d} {search_reset[3]:02d}:{search_reset[4]:02d}:{search_reset[5]:02d}"
                                self.rateSearchValue.setText(
                                    f"{self.root.langer.get('github.settings.rateRemaining')}: {search_rem}   "
                                    f"{self.root.langer.get('github.settings.rateReset')}: {reset_str}"
                                )
                            else:
                                self.searchBadge.setVisible(False)
                                self.rateSearchValue.setText("")

                        def _start_edit(self):
                            self._editing = True
                            self.tokenStack.setCurrentIndex(0)
                            self.tokenCancelBtn.setVisible(True)
                            self.tokenInput.clear()

                        def _cancel_edit(self):
                            self._editing = False
                            token = self.root.settings["github"]["token_enc"]
                            if token:
                                self.tokenStack.setCurrentIndex(1)
                            self.tokenInput.clear()

                        def _save_token(self):
                            new_token = self.tokenInput.text().strip()
                            if not new_token:
                                self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                return

                            self.root.githubAPI.setToken(new_token)
                            self.root._encrypt_settings_token(new_token)
                            new_token = None

                            self.tokenSaveBtn.setEnabled(False)
                            self.tokenMsg.setText(self.root.langer.get("github.settings.tokenChecking"))

                            def _on_checked(result):
                                ok, error_type, data = result
                                self.tokenSaveBtn.setEnabled(True)
                                if ok:
                                    self._gs._sync_rate_from_api()
                                    self.root.settings["github"]["useful"] = True
                                    self.root.saveSettings()
                                    self._editing = False
                                    self._refresh_ui()
                                    self._fetch_user()
                                    # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                elif error_type == "auth":
                                    self.root.settings["github"]["useful"] = False
                                    self.tokenMsg.setText(
                                        f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}"
                                    )
                                elif error_type == "network":
                                    self.tokenMsg.setText(
                                        f"{self.root.langer.get('github.settings.latencyConnError')}: {data}"
                                    )
                                else:
                                    self.tokenMsg.setText(f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}")

                            QThTimer.task(
                                0,
                                lambda e: self.root.githubAPI.checkToken(),
                                result_callback=_on_checked,
                                dedicated=True
                            )

                        def _clear_token(self):
                            self._gs._clear_token_data()
                            self.root.saveSettings()
                            self._editing = False
                            self._refresh_ui()

                        def _test_token(self):
                            if not self.root.settings["github"]["token_enc"]:
                                self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                return
                            self.tokenTestBtn.setEnabled(False)
                            self.tokenMsg.setText(self.root.langer.get("github.settings.tokenChecking"))
                            def _done(result):
                                self.tokenTestBtn.setEnabled(True)
                                ok, error_type, data = result
                                if ok:
                                    self._gs._sync_rate_from_api()
                                    self.root.settings["github"]["useful"] = True
                                    self._refresh_ui()
                                    # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.tokenStatus.valid"))
                                elif error_type == "auth":
                                    # 仅明确的认证失败才清除 token
                                    self._gs._clear_token_data()
                                    self.root.saveSettings()
                                    self._refresh_ui()
                                    self.tokenMsg.setText(
                                        f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}"
                                    )
                                elif error_type == "network":
                                    # 网络不通，保留 token
                                    self.tokenMsg.setText(
                                        f"{self.root.langer.get('github.settings.latencyConnError')}: {data}"
                                    )
                                else:
                                    self.tokenMsg.setText(f"{self.root.langer.get('github.settings.tokenStatus.invalid')}: {data}")
                            QThTimer.task(
                                0,
                                lambda e: self.root.githubAPI.checkToken(),
                                result_callback=_done,
                                dedicated=True
                            )

                        def _test_latency(self):
                            if not self.root.settings["github"]["token_enc"]:
                                self.tokenMsg.setText(self.root.langer.get("github.settings.tokenEmpty"))
                                return
                            self.tokenLatencyBtn.setEnabled(False)
                            self.tokenMsg.setText(self.root.langer.get("github.settings.latencyChecking"))
                            def _done(latency):
                                self.tokenLatencyBtn.setEnabled(True)
                                if latency > 0:
                                    self.tokenMsg.setText(
                                        self.root.langer.get("github.settings.latencyResult").replace("$1", str(latency))
                                    )
                                elif latency == -2:
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.latencyTimeout"))
                                elif latency == -3:
                                    self.tokenMsg.setText(self.root.langer.get("github.settings.latencyConnError"))
                                elif latency == -4:
                                    self.tokenMsg.setText("SSL 连接错误")
                                else:
                                    self.tokenMsg.setText(
                                        self.root.langer.get("github.settings.latencyError").replace("$1", str(latency))
                                    )
                            QThTimer.task(
                                0,
                                lambda e: self.root.githubAPI.checkConnection(),
                                result_callback=_done,
                                dedicated=True
                            )

                        def _fetch_user(self):
                            def _on_user(result):
                                ok, data = result
                                if ok:
                                    body = data.get("body", {})
                                    self.root.settings["github"]["user"] = {
                                        "name": body.get("login"),
                                        "headurl": body.get("avatar_url")
                                    }
                                    self.root.saveSettings()
                                    self._refresh_ui()
                                else:
                                    # 获取用户信息失败，但不影响 token 有效性
                                    self.root.settings["github"]["user"] = {"name": None, "headurl": None}
                                    self._refresh_ui()
                            QThTimer.task(
                                0,
                                lambda e: self.root.githubAPI.getUser(),
                                result_callback=_on_user,
                                dedicated=True
                            )


        class Left(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.isfold = True
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                self.setGeometry(0, 0, 40, self.parent.height())
                self.setAttribute(Qt.WA_StyledBackground, True)

            def init_wid(self):
                self.root.logger.debug("init QW.window.leftL")
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignTop)

                self.root.logger.debug("init QW.window.leftL.tline")
                self.tline = self.TLine(self, self.root)
                self.root.logger.debug("init QW.window.leftL.logo")
                self.logo = self.Logo(self, self.root)
                self.layout.addWidget(self.logo, 0)
                self.layout.addWidget(self.tline, 0)

                self.root.logger.debug("init QW.window.leftL.pages")
                self.pagebtns = self.PageBtns(self, self.root)
                self.layout.addWidget(self.pagebtns, 1)

            def fold(self, text=None):
                if text is None:
                    text = not self.isfold
                width = 40 if text else 180
                self.setGeometry(0, 0, width, self.height())
                self.root.window.lline.init_ui()
                self.root.logger.debug(f"Window left fold: {self.isfold}")
                self.isfold = text

            class Logo(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root

                    self.move_pressed = False
                    self.move_moving = False
                    self.move_winpos_ = None
                    self.move_mousepos_ = None

                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setFixedSize(180, 40)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.root.logger.debug("init QW.window.leftL.logoL")
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(5)
                    self.layout.setAlignment(Qt.AlignLeft)

                    self.logo = QLabel(self)

                    self.logo.setFixedSize(40, 40)
                    self.logo.setScaledContents(True)
                    self.layout.addWidget(self.logo, 0)

                    self.label = QLabel(self)
                    self.label.setText('Book MDT Launcher')
                    self.label.setFixedWidth(140)
                    self.label.setProperty('wid', 'title')
                    self.layout.addWidget(self.label, 1)

                def lighting(self, light: bool):
                    logo = getPath("src/assets/icons/" + ("dark.png" if light else "light.png"))
                    pix = QPixmap(logo)
                    if pix.isNull():
                        self.root.logger.error(f"Logo image not found: {logo}")
                    self.logo.setPixmap(pix)

                def mousePressEvent(self, event):
                    self.move_pressed = True
                    self.move_winpos_ = self.root.window.pos()
                    self.move_mousepos_ = event.globalPosition().toPoint()
                    super().mousePressEvent(event)

                def mouseMoveEvent(self, event):
                    if self.move_pressed:
                        if self.root.window.isMaximized():
                            self.root.window.showNormal()
                        self.move_mousepos = event.globalPosition().toPoint()
                        self.move_moving = True
                        screensize = QApplication.primaryScreen().availableGeometry()
                        movpos = self.move_winpos_ + self.move_mousepos - self.move_mousepos_
                        if movpos.x() < 0:
                            movpos.setX(0)
                        elif movpos.x() > screensize.width() - 40:
                            movpos.setX(screensize.width() - 40)
                        if movpos.y() < 0:
                            movpos.setY(0)
                        elif movpos.y() > screensize.height() - 40:
                            movpos.setY(screensize.height() - 40)
                        self.root.window.move(movpos)
                    super().mouseMoveEvent(event)

                def mouseReleaseEvent(self, event):
                    if self.move_pressed and self.move_moving:
                        self.root.logger.debug(t("Window moved via filter: ($1,$2)", self.root.window.pos().x(), self.root.window.pos().y()))
                    else:
                        self.parent.fold()
                    self.move_pressed = False
                    self.move_moving = False
                    super().mouseReleaseEvent(event)

            class TLine(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.root = root
                    self.parent = parent

                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setFixedHeight(1)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    self.line = QWidget(self)
                    self.line.setAttribute(Qt.WA_StyledBackground, True)
                    self.line.setProperty("wid", "line")

                def resizeEvent(self, event):
                    """
                    当 TLine 的大小发生变化时（由布局管理器决定），
                    重新计算内部 line 的位置和宽度
                    """
                    super().resizeEvent(event)

                    # 获取当前 TLine 的实际宽度
                    current_width = self.width()

                    # 确保宽度足够减去两边的 5px
                    if current_width > 10:
                        new_width = current_width - 10
                        new_x = 5
                    else:
                        new_width = current_width
                        new_x = 0

                    # 更新内部 line 的几何形状
                    self.line.setGeometry(new_x, 0, new_width, 1)

            class PageBtns(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self._btn = None
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setAttribute(Qt.WA_StyledBackground, False)
                    self.setFixedWidth(180)

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.btsGroup = QButtonGroup(self)
                    self.btns_ = []

                    self.chooser = QWidget(self)
                    self.chooser.setAttribute(Qt.WA_StyledBackground, True)
                    self.chooser.setStyleSheet("background: #6e4197;")
                    self.chooser.setFixedSize(3, 40)
                    self.chooser.move(-10, 0)

                    self.btsGroup.buttonClicked.connect(self.someone_clicked)

                def someone_clicked(self, btn):
                    if self._btn is not btn:
                        self.chooser.setGeometry(btn.x(), btn.y(), 3, 40)
                        self.root.logger.debug(t("Page changed to: $1", self.root.langer.get(btn.text_)))
                        self._btn = btn

                def add_btn(self, text=None, logo=None):
                    btn = self.Btns(logo, text, self, self.root)
                    self.btns_.append(btn)
                    self.layout.addWidget(btn)
                    self.btsGroup.addButton(btn)
                    return btn

                class Btns(QPushButton):
                    def __init__(self, logo=None, text=None, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.logo_ = logo
                        self.text_ = text
                        self.init_ui()
                        self.init_wid()

                    def init_ui(self):
                        self.setFixedSize(180, 40)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid", "lbtn")
                        self.setCheckable(True)

                    def init_wid(self):
                        self.layout = QHBoxLayout(self)
                        self.layout.setContentsMargins(3, 0, 0, 0)
                        self.layout.setSpacing(5)

                        self.logo = QLabel(self)
                        self.logo.setFixedSize(40, 40)
                        self.logo.setAttribute(Qt.WA_StyledBackground, False)
                        self.logo.setProperty("wid", "lbtn")
                        self.logo.setScaledContents(False)
                        self.layout.addWidget(self.logo)

                        self.text = QLabel(self)
                        self.text.setAttribute(Qt.WA_StyledBackground, False)
                        self.text.setFixedSize(140, 40)
                        self.text.setProperty("wid", "lbtn")
                        self.langing()
                        self.layout.addWidget(self.text)

                    def lighting(self, light: bool):
                        if self.logo_ is not None:
                            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                            logo = change_color(self.logo_, color)
                            pixmap = logo.pixmap(56,56)

                            if not pixmap.isNull():
                                smooth_pixmap = pixmap.scaled(
                                    30, 30,
                                    Qt.KeepAspectRatio,
                                    Qt.FastTransformation
                                )
                                self.logo.setPixmap(smooth_pixmap)
                            else:
                                self.root.logger.warning(f"Failed to load pixmap for {self.logo_}")

                    def langing(self):
                        if self.text_ is not None:
                            self.text.setText(self.root.langer.get(self.text_))
                            self.setToolTip(self.root.langer.get(self.text_))

                    def setText(self, _text):
                        self.text_ = _text
                        self.langing()

                    def setLogo(self, _logo):
                        self.logo_ = _logo
                        self.lighting()

        class LLine(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.init_ui()

            def init_ui(self):
                self.setProperty("wid", "line")
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.setGeometry(self.parent.left.width(), 0, 1, self.parent.height())


        class Main(QWidget):
            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                pass

            def init_wid(self):
                self.root.logger.debug("init QW.windowL.mainL")
                self.layout = QVBoxLayout(self)
                self.layout.setAlignment(Qt.AlignTop)
                self.layout.setSpacing(0)
                self.layout.setContentsMargins(0, 0, 0, 0)

                self.root.logger.debug("init QW.windowL.mainL.top")
                self.top = self.Top(self, self.root)
                self.layout.addWidget(self.top, 0)

                self.root.logger.debug("init QW.windowL.mainL.tline")
                self.tline = self.TLine(self, self.root)
                self.layout.addWidget(self.tline)

                self.root.logger.debug("init QW.windowL.mainL.main")
                self.main = self.Main(self, self.root)
                self.layout.addWidget(self.main, 1)

            class Top(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setFixedHeight(40)

                def init_wid(self):
                    self.root.logger.debug("init QW.windowL.mainL.topL")
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(7, 0, 5, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignRight)

                    self.github = self.GitHub(self, self.root)
                    self.layout.addWidget(self.github)

                    self.layout.addSpacing(8)

                    self.dlList = self.DlList(self, self.root)
                    self.layout.addWidget(self.dlList)

                    self.layout.addStretch(1)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_mini")
                    self.tbt_mini = self.TriBtn([getPath("src/assets/tribtns/minimize.png")], self, self.root)
                    self.tbt_mini.clicked.connect(lambda: self.root.window.showMinimized())
                    self.layout.addWidget(self.tbt_mini)
                    self.layout.addSpacing(5)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_max")
                    self.tbt_max = self.TriBtn(
                        [
                            getPath("src/assets/tribtns/maximize.png"),
                            getPath("src/assets/tribtns/maximize2.png")
                        ],
                        self, self.root)
                    self.tbt_max.clicked.connect(self.maxmize)
                    self.layout.addWidget(self.tbt_max)
                    self.layout.addSpacing(5)

                    self.root.logger.debug("init QW.windowL.mainL.topL.tbt_close")
                    self.tbt_close = self.TriBtn([getPath("src/assets/tribtns/close.png")], self, self.root)
                    self.tbt_close.clicked.connect(lambda: self.close_())
                    self.tbt_close.setStyleSheet("QPushButton:hover{background: red;}")
                    self.layout.addWidget(self.tbt_close)


                def maxmize(self):
                    if self.root.window.isMaximized():
                        self.root.window.showNormal()
                    else:
                        self.root.window.showMaximized()

                def close_(self):
                    if self.root.settings["closeByTray"]:
                        self.root.window.hide()
                    else:
                        self.root.window.close()

                class GitHub(QPushButton):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self._hover_pending = False
                        self.init_ui()
                        self.clicked.connect(lambda: self.root.window.githubSetting.show())
                        # refreshed 仅更新 tooltip，不触发后台请求
                        self.root.githubAPI.refreshed.connect(self._update_tooltip)

                    def init_ui(self):
                        self.setFixedSize(28, 28)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setStyleSheet("QPushButton {border-radius: 15px;}")

                    def lighting(self, light):
                        self.setIcon(QIcon(change_color(getPath("src/assets/brands/github.png"),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                        self.setIconSize(QSize(28, 28))

                    def _update_tooltip(self):
                        """仅更新 tooltip 文本，不触发网络请求。"""
                        token = self.root.settings["github"]["token_enc"]
                        live_rate = self.root.githubAPI.rate
                        rate = self.root.settings["github"]["rate"]

                        def _fmt_reset(entry):
                            r = entry.get("reset", [])
                            if len(r) == 6:
                                return f"{r[3]:02d}:{r[4]:02d}:{r[5]:02d}"
                            return "-"

                        def _get(entry, key, fallback_entry=None):
                            v = entry.get(key)
                            if v is not None and v != []:
                                return v
                            if fallback_entry is not None:
                                v = fallback_entry.get(key)
                                if v is not None and v != []:
                                    return v
                            return None

                        core_rem = _get(rate["core"], "remaining", live_rate["core"])
                        search_rem = _get(rate["search"], "remaining", live_rate["search"])
                        core_reset = _fmt_reset(
                            rate["core"] if rate["core"].get("reset") else live_rate["core"]
                        )
                        search_reset = _fmt_reset(
                            rate["search"] if rate["search"].get("reset") else live_rate["search"]
                        )

                        if token is None:
                            key = "github.token.none"
                        elif self.root.settings["github"]["useful"] is False:
                            key = "github.token.error"
                        else:
                            key = "github.token"
                        #   $1=剩余次数 $2=刷新时间 $3=剩余次数 $4=刷新时间
                        self.setToolTip(str(t(
                            self.root.langer.get(key),
                            search_reset, search_rem, core_reset, core_rem
                        )))

                    def _maybe_fetch_rate(self):
                        """hover 时数据缺失才触发一次 checkToken（防抖 2s）。"""
                        if self._hover_pending:
                            return
                        live = self.root.githubAPI.rate
                        core_rem = live["core"].get("remaining")
                        search_rem = live["search"].get("remaining")
                        if core_rem is not None and search_rem is not None:
                            return
                        self._hover_pending = True
                        QThTimer.task(0, lambda e: self.root.githubAPI.checkToken(), dedicated=True)
                        # 2 秒后允许下次 hover 触发
                        QTimer.singleShot(2000, lambda: setattr(self, '_hover_pending', False))

                    def enterEvent(self, event):
                        super().enterEvent(event)
                        self._update_tooltip()
                        if self.root.settings["github"]["token_enc"] is not None:
                            self._maybe_fetch_rate()

                class DlList(QPushButton):
                    def __init__(self, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.init_ui()
                        self.shown = True
                        self.hide()
                        self._active_state = None
                        # taskP 周期驱动：job 在 QThTimer 共享子线程检查任务表，
                        # 仅状态变化时 emit 回主线程刷新 UI——主线程零轮询、跨线程消息最少
                        self._dl_timer = QThTimer.taskP(
                            1000, self._check_state, [lambda v: self._apply_visible(v)]
                        )
                        self.destroyed.connect(self._stop_dl_timer)
                        self.clicked.connect(self._on_click)

                    def _on_click(self):
                        """打开下载列表页（floatingStack 导航页）。"""
                        self.root.window.floatingStack.add_page(self.DlListPage(self, self.root))

                    def _check_state(self, event):
                        """子线程：读取任务表，与本地状态比对，变化才 emit。"""
                        cur = bool(QDownloader.get_active_tasks())
                        if cur != self._active_state:
                            self._active_state = cur
                            event.lambdas[0].emit(cur)

                    def _apply_visible(self, visible):
                        """主线程：仅状态变化时被调用，更新 UI。"""
                        try:
                            self.setVisible(visible and self.shown)
                        except Exception:
                            pass

                    def update_shown(self):
                        """shown 变化（DlListPage 打开/关闭）后立即刷新，不等下一个周期。"""
                        try:
                            self.setVisible(self._active_state and self.shown)
                        except Exception:
                            pass

                    def _stop_dl_timer(self):
                        # 自身销毁时停掉周期任务，避免对已删除对象回调
                        try:
                            timer = getattr(self, "_dl_timer", None)
                            if timer is not None:
                                timer.destroy()
                                self._dl_timer = None
                        except Exception:
                            pass

                    def init_ui(self):
                        self.setFixedSize(30,30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setStyleSheet("QPushButton {border-radius: 15px;}")

                    def lighting(self, light):
                        self.setIcon(QIcon(change_color(getPath("src/assets/actions/dl_list.png"),QColor(255, 255, 255)if not light else QColor(0, 0, 0))))
                        self.setIconSize(QSize(30,30))

                    class DlListPage(QWidget):
                        def __init__(self, parent=None, root=None):
                            super().__init__()
                            self.parent = parent
                            self.root = root
                            self.parent.shown = False
                            self.parent.update_shown()
                            self.item_map = {}          # task_id -> Item
                            self._closed = False
                            self._timer = None
                            self._last_java_paused = None   # 检测循环上次看到的 Java 暂停状态（变化时记日志）
                            self.init_ui()
                            self.langing()
                            # 初始化时立即扫描一次，随后周期刷新
                            self._timer = QThTimer.taskP(1000, self._snapshot_tasks, result_callback=self._render_items)
                            QThTimer.task(0, self._snapshot_tasks, result_callback=self._render_items)

                        def on_close(self):
                            self._closed = True
                            self.parent.shown = True
                            self.parent.update_shown()
                            try:
                                if self._timer is not None:
                                    self._timer.destroy()
                                    self._timer = None
                            except Exception:
                                pass

                        def init_ui(self):
                            self.setAttribute(Qt.WA_StyledBackground, True)
                            self.setProperty("wid", "color2")
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)

                            # 标题栏：标题 + 返回
                            self.top_bar = QWidget()
                            self.top_bar.setFixedHeight(44)
                            self.layout.addWidget(self.top_bar, 0)
                            self.top_layout = QHBoxLayout(self.top_bar)
                            self.top_layout.setContentsMargins(15, 0, 10, 0)
                            self.top_layout.setSpacing(8)
                            self.title_label = QLabel()
                            self.title_label.setProperty("wid", "text")
                            self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
                            self.top_layout.addWidget(self.title_label, 1)

                            self.divider = QWidget()
                            self.divider.setProperty("wid", "line")
                            self.divider.setFixedHeight(1)
                            self.layout.addWidget(self.divider, 0)

                            # 任务列表滚动区
                            self.scroll = QScrollArea()
                            self.scroll.setWidgetResizable(True)
                            self.scroll.setFrameShape(QFrame.NoFrame)
                            self.layout.addWidget(self.scroll, 1)
                            self.list_container = QWidget()
                            self.list_container.setAttribute(Qt.WA_StyledBackground, True)
                            self.list_container.setStyleSheet("background: transparent")
                            self.list_layout = QVBoxLayout(self.list_container)
                            self.list_layout.setContentsMargins(12, 12, 12, 12)
                            self.list_layout.setSpacing(8)
                            self.list_layout.setAlignment(Qt.AlignTop)
                            self.scroll.setWidget(self.list_container)

                            # 空状态提示（始终位于列表末尾，任务卡片插入其前）
                            self.empty_label = QLabel()
                            self.empty_label.setProperty("wid", "title")
                            self.empty_label.setStyleSheet("font-size: 14px;")
                            self.empty_label.setAlignment(Qt.AlignCenter)
                            self.empty_label.setFixedHeight(120)
                            self.list_layout.addWidget(self.empty_label)

                        def langing(self):
                            self.title_label.setText(self.root.langer.get("wid.pages.downloadList.title"))
                            self.empty_label.setText(self.root.langer.get("wid.pages.downloadList.empty"))

                        def _snapshot_tasks(self, event):
                            """子线程：收集运行中/暂停中与可续传任务的快照（不触碰 UI）。"""
                            try:
                                actives = {}
                                for task_id, task in QDownloader.get_active_tasks().items():
                                    done, total = 0, 0
                                    try:
                                        done, total = task.get_progress()
                                    except Exception:
                                        pass
                                    actives[task_id] = {
                                        "id": task_id,
                                        "kind": "active",
                                        "dest": task.dest_path or "",
                                        "title": getattr(task, "title", "") or "",
                                        "done": done,
                                        "total": total,
                                        "paused": bool(getattr(task, "_is_paused", False)),
                                        "cancel_allowed": bool(getattr(task, "cancel_allowed", True)),
                                        "pause_allowed": bool(getattr(task, "pause_allowed", True)),
                                        "task": task,
                                    }
                                pendings = {}
                                for task_id, info in QDownloader.get_pending_tasks().items():
                                    pendings[task_id] = {
                                        "id": task_id,
                                        "kind": "pending",
                                        "dest": info.get("dest_path") or "",
                                        "title": info.get("title") or "",
                                        "done": info.get("done_bytes") or 0,
                                        "total": info.get("total_size") or 0,
                                        "paused": False,
                                        "task": None,
                                        "state_file": info.get("state_file") or "",
                                    }
                                return actives, pendings
                            except Exception as e:
                                return e

                        def _render_items(self, result):
                            if self._closed or isinstance(result, Exception):
                                return
                            actives, pendings = result
                            # Java 下载状态同步：检测循环轮询读取任务实时状态，驱动 Launch 页 label。
                            # 与 paused_changed 信号互补——信号丢失/时序错乱时，1 秒内轮询自动纠正，
                            # 避免暂停瞬间被 progress 覆盖成"正在下载"后卡住。
                            # 只更新 label 文本不切页，避免打断用户当前页面。
                            try:
                                for _t in actives.values():
                                    _dest = _t.get("dest") or ""
                                    if _dest.startswith(javaDownload.JAVA_TMP_DIR):
                                        _total = _t.get("total") or 0
                                        _done = _t.get("done") or 0
                                        _pct = min(100, int(_done * 100.0 / _total)) if _total > 0 else 0
                                        _paused = bool(_t.get("paused"))
                                        _bottom = self.root._java_bottom()
                                        if _paused:
                                            _bottom.launch.setStatus("paused", _pct)
                                        else:
                                            _bottom.launch.setStatus("downloading", _pct)
                                        # 检测循环日志：记录读取到的 Java 任务状态（含暂停/恢复切换），
                                        # 用于排查信号竞争导致的"暂停后被覆盖成正在下载"
                                        if _paused != self._last_java_paused:
                                            self.root.logger.info(t(self.root.langer.get("log.dl.java_state"),
                                                                    "paused" if _paused else "downloading",
                                                                    _pct,
                                                                    os.path.basename(_dest) or _dest))
                                            self._last_java_paused = _paused
                                        break
                            except Exception as e:
                                self.root.logger.warning(t(self.root.langer.get("log.dl.java_sync_error"), repr(e)))
                            all_tasks = dict(actives)
                            all_tasks.update(pendings)
                            # 移除已消失的任务卡片
                            for task_id in list(self.item_map.keys()):
                                if task_id not in all_tasks:
                                    item = self.item_map.pop(task_id)
                                    self.list_layout.removeWidget(item)
                                    item.deleteLater()
                            # 新增或刷新卡片
                            for task_id, task_info in all_tasks.items():
                                if task_id not in self.item_map:
                                    item = self.Item(self, self.root)
                                    item.continue_requested.connect(self._continue_task)
                                    item.delete_requested.connect(self._delete_task)
                                    self.item_map[task_id] = item
                                    self.list_layout.insertWidget(self.list_layout.count() - 1, item)
                                else:
                                    item = self.item_map[task_id]
                                item.set_data(task_info)
                            self.empty_label.setVisible(not bool(all_tasks))

                        def _continue_task(self, task_id):
                            try:
                                dl = QDownloader.continue_task(task_id)
                                if not hasattr(self.root, "_mdt_downloads"):
                                    self.root._mdt_downloads = []
                                self.root._mdt_downloads.append(dl)
                                # 用户主动续传：清除 downloading.json 中的暂停状态（恢复下载）
                                try:
                                    dest = getattr(dl, "dest_path", "") or ""
                                    if dest and _is_mdt_download(dest):
                                        dfile = os.path.join(os.path.dirname(dest), "downloading.json")
                                        if os.path.isfile(dfile):
                                            with open(dfile, "r", encoding="utf-8") as f:
                                                info = json.load(f)
                                            if info.get("paused"):
                                                info["paused"] = False
                                                info["updated_at"] = int(time.time())
                                                with open(dfile, "w", encoding="utf-8") as f:
                                                    json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                                except Exception:
                                    pass
                            except Exception as e:
                                self.root.logger.error(t(self.root.langer.get("log.dl.resume_failed"), task_id, e))

                        def _delete_task(self, state_file):
                            task_dir = os.path.dirname(state_file) if state_file else None
                            if task_dir and os.path.isdir(task_dir):
                                shutil.rmtree(task_dir, ignore_errors=True)
                            # 若是 mdt 游戏下载：同时删除目标文件夹（含 downloading.json），
                            # 避免残留记录导致下次启动又被续传
                            try:
                                dest = ""
                                if state_file and os.path.isfile(state_file):
                                    with open(state_file, "r", encoding="utf-8") as f:
                                        dest = (json.load(f) or {}).get("dest_path", "") or ""
                                if dest and _is_mdt_download(dest):
                                    mdir = os.path.dirname(dest)
                                    if os.path.isdir(mdir):
                                        shutil.rmtree(mdir, ignore_errors=True)
                                    self.root.logger.info(t(self.root.langer.get("log.dl.mdt_delete_cleaned"),
                                                            os.path.basename(mdir) or mdir))
                            except Exception:
                                pass
                            # 立即刷新一轮，不必等下一个周期
                            QThTimer.task(0, lambda e: self._snapshot_tasks(e), result_callback=self._render_items)

                        class Item(QWidget):
                            continue_requested = Signal(str)
                            delete_requested = Signal(str)

                            def __init__(self, parent=None, root=None):
                                super().__init__(parent)
                                self.parent = parent
                                self.root = root
                                self.task_id = ""
                                self.task = None      # 运行中任务的 QDownloader 实例（pending 为 None）
                                self.state_file = ""
                                self.task_info = {}
                                self.init_ui()

                            def init_ui(self):
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.setProperty("wid", "color2")
                                self.setStyleSheet("border-radius: 8px;")
                                layout = QVBoxLayout(self)
                                layout.setContentsMargins(12, 8, 12, 8)
                                layout.setSpacing(6)

                                # 第一行：文件名 + 状态
                                row1 = QHBoxLayout()
                                row1.setSpacing(8)
                                self.title_label = QLabel()
                                self.title_label.setProperty("wid", "text")
                                self.title_label.setStyleSheet("font-size: 13px;")
                                row1.addWidget(self.title_label, 1)
                                self.status_label = QLabel()
                                self.status_label.setProperty("wid", "title")
                                self.status_label.setStyleSheet("font-size: 11px;")
                                row1.addWidget(self.status_label, 0)
                                layout.addLayout(row1)

                                # 第二行：进度条 + 已下载/总大小
                                row2 = QHBoxLayout()
                                row2.setSpacing(8)
                                self.progress_bar = QProgressBar()
                                self.progress_bar.setProperty("wid", "progress")
                                self.progress_bar.setRange(0, 100)
                                self.progress_bar.setTextVisible(False)
                                self.progress_bar.setFixedHeight(14)
                                row2.addWidget(self.progress_bar, 1)
                                self.size_label = QLabel()
                                self.size_label.setProperty("wid", "title")
                                self.size_label.setStyleSheet("font-size: 11px;")
                                self.size_label.setFixedWidth(120)
                                row2.addWidget(self.size_label, 0)
                                layout.addLayout(row2)

                                # 第三行：主操作（暂停/继续/续传）+ 次操作（取消/删除）
                                row3 = QHBoxLayout()
                                row3.setSpacing(6)
                                row3.addStretch(1)
                                self.btn_primary = QPushButton()
                                self.btn_primary.setProperty("wid", "btn")
                                self.btn_primary.setFixedSize(64, 24)
                                row3.addWidget(self.btn_primary, 0)
                                self.btn_secondary = QPushButton()
                                self.btn_secondary.setProperty("wid", "btn")
                                self.btn_secondary.setFixedSize(64, 24)
                                row3.addWidget(self.btn_secondary, 0)
                                layout.addLayout(row3)

                                self.btn_primary.clicked.connect(self._on_primary_clicked)
                                self.btn_secondary.clicked.connect(self._on_secondary_clicked)

                            @staticmethod
                            def _fmt_size(size):
                                size = max(0, int(size or 0))
                                if size >= 1024 * 1024 * 1024:
                                    return "%.2f GB" % (size / (1024.0 ** 3))
                                if size >= 1024 * 1024:
                                    return "%.2f MB" % (size / (1024.0 ** 2))
                                if size >= 1024:
                                    return "%.1f KB" % (size / 1024.0)
                                return "%d B" % size

                            def set_data(self, task_info):
                                self.task_info = task_info
                                self.task_id = task_info.get("id") or ""
                                task = task_info.get("task")
                                if task is not self.task:
                                    self._disconnect_task_signals()
                                    self.task = task
                                    self._connect_task_signals()
                                self.state_file = task_info.get("state_file") or ""

                                # 名称（超长省略）：优先显示 title，回退文件名
                                name = task_info.get("title") or os.path.basename(task_info.get("dest") or "") or self.task_id
                                self.title_label.setText(QFontMetrics(self.title_label.font()).elidedText(name, Qt.ElideRight, 460))

                                # 进度条与大小文本
                                done = task_info.get("done") or 0
                                total = task_info.get("total") or 0
                                if total > 0:
                                    percent = min(100, int(done * 100.0 / total))
                                    self.progress_bar.setValue(percent)
                                    self.size_label.setText("%s / %s" % (self._fmt_size(done), self._fmt_size(total)))
                                else:
                                    self.progress_bar.setValue(0)
                                    self.size_label.setText(self._fmt_size(done))

                                # 状态文本与按钮语义
                                if task_info.get("kind") == "active":
                                    if task_info.get("paused"):
                                        self.status_label.setText(self.root.langer.get("wid.pages.downloadList.paused"))
                                        self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.resume"))
                                    else:
                                        self.status_label.setText(self.root.langer.get("wid.pages.downloadList.active"))
                                        self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.pause"))
                                    self.btn_secondary.setText(self.root.langer.get("wid.pages.downloadList.cancel"))
                                else:
                                    self.status_label.setText(self.root.langer.get("wid.pages.downloadList.pending"))
                                    self.btn_primary.setText(self.root.langer.get("wid.pages.downloadList.continue"))
                                    self.btn_secondary.setText(self.root.langer.get("wid.pages.downloadList.delete"))
                                self._update_buttons()

                            def _connect_task_signals(self):
                                """监听任务允许状态变化，即时刷新按钮。"""
                                if self.task is not None:
                                    try:
                                        self.task.cancel_allowed_changed.connect(self._on_cancel_allowed_changed)
                                    except Exception:
                                        pass
                                    try:
                                        self.task.pause_allowed_changed.connect(self._on_pause_allowed_changed)
                                    except Exception:
                                        pass

                            def _disconnect_task_signals(self):
                                if self.task is not None:
                                    try:
                                        self.task.cancel_allowed_changed.disconnect(self._on_cancel_allowed_changed)
                                    except Exception:
                                        pass
                                    try:
                                        self.task.pause_allowed_changed.disconnect(self._on_pause_allowed_changed)
                                    except Exception:
                                        pass

                            def _on_cancel_allowed_changed(self, allowed):
                                self.task_info["cancel_allowed"] = bool(allowed)
                                self._update_buttons()

                            def _on_pause_allowed_changed(self, allowed):
                                self.task_info["pause_allowed"] = bool(allowed)
                                self._update_buttons()

                            def _update_buttons(self):
                                """根据任务允许状态显示/隐藏操作按钮。"""
                                if self.task_info.get("kind") == "active":
                                    self.btn_primary.setVisible(bool(self.task_info.get("pause_allowed", True)))
                                    self.btn_secondary.setVisible(bool(self.task_info.get("cancel_allowed", True)))
                                else:
                                    self.btn_primary.setVisible(True)
                                    self.btn_secondary.setVisible(True)

                            def _on_primary_clicked(self):
                                # 运行中：暂停/继续；待续传：请求页面续传
                                if self.task_info.get("kind") == "active":
                                    if self.task is not None and self.task_info.get("pause_allowed", True):
                                        if self.task_info.get("paused"):
                                            self.task.resume()
                                            self._sync_mdt_paused(False)
                                        else:
                                            self.task.pause()
                                            self._sync_mdt_paused(True)
                                else:
                                    self.continue_requested.emit(self.task_id)

                            def _sync_mdt_paused(self, paused):
                                """暂停/恢复时把状态写入 .Mindustrys/<name>/downloading.json（仅 mdt 游戏下载）。

                                启动时通过 getDownloadingMdts 读取该状态同步暂停。
                                """
                                dest = getattr(self.task, "dest_path", "") or ""
                                if not _is_mdt_download(dest):
                                    return
                                dfile = os.path.join(os.path.dirname(dest), "downloading.json")
                                try:
                                    info = {}
                                    if os.path.isfile(dfile):
                                        with open(dfile, "r", encoding="utf-8") as f:
                                            info = json.load(f)
                                    info["paused"] = bool(paused)
                                    info["updated_at"] = int(time.time())
                                    os.makedirs(os.path.dirname(dfile), exist_ok=True)
                                    with open(dfile, "w", encoding="utf-8") as f:
                                        json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                                    _state = self.root.langer.get("log.java.paused_state" if paused else "log.java.resumed_state")
                                    self.root.logger.info(t(self.root.langer.get("log.dl.mdt_paused_state"),
                                                            _state,
                                                            os.path.basename(os.path.dirname(dest)) or ""))
                                except Exception as e:
                                    self.root.logger.warning(t(self.root.langer.get("log.dl.mdt_paused_error"), repr(e)))

                            def _on_secondary_clicked(self):
                                # 运行中：取消（子线程执行阻塞式取消，取消后删除 mdt 目标文件夹）；
                                # 待续传：请求页面删除
                                if self.task_info.get("kind") == "active":
                                    if self.task is not None and self.task_info.get("cancel_allowed", True):
                                        def _do_cancel(e, t=self.task, dest=self.task_info.get("dest") or ""):
                                            try:
                                                t.cancel(timeout=8)
                                            finally:
                                                # mdt 游戏下载：取消后删除目标文件夹（含 downloading.json）
                                                if dest and _is_mdt_download(dest):
                                                    mdir = os.path.dirname(dest)
                                                    try:
                                                        if os.path.isdir(mdir):
                                                            shutil.rmtree(mdir, ignore_errors=True)
                                                        self.root.logger.info(t(self.root.langer.get("log.dl.mdt_cancel_cleaned"),
                                                                                os.path.basename(mdir) or mdir))
                                                    except Exception:
                                                        pass
                                        QThTimer.task(0, _do_cancel, dedicated=True)
                                else:
                                    self.delete_requested.emit(self.state_file)

                class TriBtn(QPushButton):
                    def __init__(self, logo: list, parent=None, root=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.logo_ = logo
                        self.setLogo_ = 0
                        self.init_ui()

                    def init_ui(self):
                        self.setFixedSize(30,30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid", "tbtn")

                    def setLogo(self, l):
                        self.setLogo_ = l
                        self.lighting(self.root.settings["theme"])

                    def lighting(self, light: bool):
                        color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                        logo = change_color(self.logo_[self.setLogo_], color)
                        pixmap = QIcon(logo.pixmap(48,48))

                        self.setIcon(pixmap)

            class TLine(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.init_ui()
                    self.init_wid()

                def init_ui(self):
                    self.setProperty("wid", "line")
                    self.setFixedHeight(1)
                    self.setAttribute(Qt.WA_StyledBackground, True)

                def init_wid(self):
                    pass

            class Main(QWidget):
                def __init__(self, parent=None, root=None):
                    super().__init__()
                    self.parent = parent
                    self.root = root
                    self.pages = []
                    self.btns = []
                    self.init_wid()
                    self.pages[0].click()

                def init_wid(self):
                    self.layout = QHBoxLayout(self)
                    self.layout.setContentsMargins(0, 0, 0, 0)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop)

                    self.left = self.Left_(self,self.root)
                    self.layout.addWidget(self.left,0)
                    self.main = self.Main_(self,self.root)
                    self.layout.addWidget(self.main,1)
                    self.right = self.Right_(self,self.root)
                    self.layout.addWidget(self.right,0)

                    self.start = self.Start(self,self.root,"wid.pages.start",getPath("src/assets/buttons/start.png"))
                    self.download = self.Download(self,self.root,"wid.pages.download",getPath("src/assets/buttons/download.png"))
                    self.game = self.Game(self,self.root,"wid.pages.game",getPath("src/assets/buttons/game.png"))
                    self.setting = self.Setting(self,self.root,"wid.pages.setting",getPath("src/assets/buttons/setting.png"))

                class Left_(QStackedWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root


                class Main_(QStackedWidget):
                    def __init__(self, parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root

                class Right_(QStackedWidget):
                    def __init__(self,parent=None, root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root

            
                class Page():
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__()
                        self.parent = parent
                        self.root = root
                        self.text = text
                        self.logo = logo
                        self.init_wid()
                        self.id = len(self.parent.pages)
                        self.parent.pages.append(self)
                        self.btn = self.root.window.left.pagebtns.add_btn(self.text,self.logo)
                        self.parent.btns.append(self)
                        self.btn.clicked.connect(self.changePage)

                    def changePage(self):
                        self.parent.left.setCurrentWidget(self.left)
                        self.parent.main.setCurrentWidget(self.main)
                        self.parent.right.setCurrentWidget(self.right)
                        self.parent.left.setFixedWidth(self.left.width_)
                        self.parent.right.setFixedWidth(self.right.width_)

                    def click(self):
                        self.btn.click()

                    def init_wid(self):
                        cls_left = self.Left if hasattr(self, 'Left') else Leftw
                        self.left = cls_left(self, self.root)

                        cls_main = self.Main if hasattr(self, 'Main') else Mainw
                        self.main = cls_main(self, self.root)

                        cls_right = self.Right if hasattr(self, 'Right') else Rightw
                        self.right = cls_right(self, self.root)

                class Start(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        root.signals.register("start_gameChanged", Signal(object))
                        super().__init__(parent, root, text, logo)
                        QThTimer.taskP(1000, self.left.changeTimer, [self.left.sets])
                        QThTimer.task(0, self.left.changeTimer, [self.left.sets])
                        self.root.launcher.game_launched.connect(lambda: self.main.stack.setCurrentIndex(3))
                        self.root.launcher.game_launched.connect(lambda: self.left.main.setCurrentIndex(3))
                        self.root.launcher.game_started.connect(lambda: self.main.stack.setCurrentIndex(4))
                        self.root.launcher.game_started.connect(lambda: self.left.main.setCurrentIndex(4))
                        self.root.launcher.lifecycle_finished.connect(lambda: self.main.stack.setCurrentIndex(0))
                        self.root.launcher.lifecycle_finished.connect(lambda: self.left.main.setCurrentIndex(0))
                        self.root.launcher.appdata_save_step.connect(self._on_appdata_save_step)
                        self.root.launcher.appdata_save_done.connect(self._on_appdata_save_done)
                        self.root.launcher.appdata_import_started.connect(self._on_appdata_import_started)
                        self.root.launcher.appdata_import_done.connect(self._on_appdata_import_done)
                        self.root.launcher.log.connect(lambda dic: (self.root.logger.info("[launcher]"+dic["text"]) if dic["type"] == "info" else self.root.logger.error("[launcher]"+dic["text"])))

                    def changeGame(self, game=None):
                        mdts = mdtScanner.getMdts()
                        if game == self.root.settings["defaultGame"]: return
                        if game not in mdts:
                            if len(mdts) == 0:
                                self.root.settings["defaultGame"] = None
                            else:
                                self.root.settings["defaultGame"] = mdts[0]
                        else:
                            self.root.settings["defaultGame"] = game
                        self.root.signals.emit("start_gameChanged", game)
                        QThTimer.task(0, self.left.changeTimer, [self.left.sets])

                    def _on_appdata_save_step(self, step):
                        """appdataCopy 保存步骤：切换两个界面到 index 5 并设置 finished 文本。"""
                        try:
                            self.left.main.setCurrentIndex(5)
                            self.main.stack.setCurrentIndex(5)
                            self.left.main.finished.setStatus(step)
                            self.main.finished.setStatus(step)
                        except Exception:
                            pass

                    def _on_appdata_save_done(self):
                        """appdataCopy 保存完成：两个界面切回 index 0。"""
                        try:
                            self.main.stack.setCurrentIndex(0)
                            self.left.main.setCurrentIndex(0)
                        except Exception:
                            pass

                    def _on_appdata_import_started(self):
                        """appdataCopy 开始导入数据：两个界面切到 finished 页显示"正在导入数据"。"""
                        try:
                            text = self.root.langer.get("wid.pages.start.finished.importing")
                            self.left.main.finished.label.setText(text)
                            self.main.finished.label.setText(text)
                            self.left.main.setCurrentIndex(5)
                            self.main.stack.setCurrentIndex(5)
                        except Exception:
                            pass

                    def _on_appdata_import_done(self):
                        """appdataCopy 导入完成：切回 launch 页等待游戏启动。"""
                        try:
                            self.main.stack.setCurrentIndex(3)
                            self.left.main.setCurrentIndex(3)
                        except Exception:
                            pass

                            

                    class Left(Leftw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent, root)
                            self.resize_(250)
                            self.init_wid()
                            self.game = {
                                "icon": None,
                                "name": None,
                                "vers": None,
                                "icon_key": None
                            }

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0,0,0,0)
                            self.layout.setSpacing(0)
                            self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

                            self.layout.addSpacing(40)
                            self.icon = QLabel(self)
                            self.icon.setFixedSize(120,120)
                            self.icon.setScaledContents(True)
                            self.icon.setProperty("wid", "png")
                            self.layout.addWidget(self.icon, 0, Qt.AlignHCenter)
                            self.layout.addSpacing(20)

                            self.gameTxt = QLabel()
                            self.gameTxt.setProperty("wid","title")
                            self.gameTxt.setStyleSheet("font-size:20px")
                            self.layout.addWidget(self.gameTxt, 0, Qt.AlignHCenter)
                            self.gameTxt.setText("游戏名")

                            self.versTxt = QLabel()
                            self.versTxt.setProperty("wid","title")
                            self.versTxt.setStyleSheet("font-size:12px")
                            self.layout.addWidget(self.versTxt, 0, Qt.AlignHCenter)
                            self.versTxt.setText("版本")

                            self.layout.addSpacing(30)
                            self.main = self.Bottom(self,self.root)
                            self.layout.addWidget(self.main,1)

                        def sets(self,icon=(False,None),gameTxt=(False,None),versTxt=(False,None)):
                            if icon[0]:
                                pm = icon[1]
                                if pm and not pm.isNull():
                                    pm = pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.FastTransformation)
                                self.icon.setPixmap(pm)
                            if gameTxt[0]:
                                self.gameTxt.setText(QFontMetrics(self.gameTxt.font()).elidedText(gameTxt[1], Qt.ElideRight, 150))
                            if versTxt[0]:
                                self.versTxt.setText(QFontMetrics(self.versTxt.font()).elidedText(versTxt[1], Qt.ElideRight, 130))

                        def changeTimer(self,event):
                            i = [(False,None),(False,None),(False,None)]
                            mdts = mdtScanner.getMdts()
                            if len(mdts) == 0:
                                if self.root.settings["defaultGame"] is not None:
                                    self.root.settings["defaultGame"] = None
                            elif self.root.settings["defaultGame"] is None or self.root.settings["defaultGame"] not in mdts:
                                self.root.settings["defaultGame"] = mdts[0]
                            default_game = self.root.settings["defaultGame"]
                            game_msg = mdtScanner.getMdtMsg(default_game) if default_game else None
                            if self.game["name"] != default_game:
                                if default_game is None:
                                    i[1] = (True,self.root.langer.get("wid.pages.start.left.noGame"))
                                    i[2] = (True,self.root.langer.get("wid.pages.start.left.DGame"))
                                    self.game["name"] = self.game["vers"] = self.game["icon_key"] = None
                                else:
                                    self.game["name"] = default_game
                                    if game_msg:
                                        self.game["vers"] = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}"
                                    i[1] = (True,default_game)
                                    i[2] = (True,self.game["vers"])
                            elif self.game["name"] is not None and game_msg:
                                new_vers = f"v{game_msg['number']}.{game_msg['build']}{game_msg['modifier']}"
                                if self.game["vers"] != new_vers:
                                    self.game["vers"] = new_vers
                                    i[2] = (True,new_vers)
                            if self.game["name"] is not None and game_msg and game_msg["icon"]:
                                icon_path = game_msg["icon"]
                                try:
                                    icon_key = f"{icon_path}:{os.path.getmtime(icon_path)}:{os.path.getsize(icon_path)}"
                                except OSError:
                                    icon_key = None
                            else:
                                icon_key = None

                            if self.game.get("icon_key") != icon_key:
                                self.game["icon_key"] = icon_key
                                if icon_key is not None:
                                    i[0] = (True, QPixmap(game_msg["icon"]))
                                else:
                                    i[0] = (True, QPixmap())

                            if i[0][0] or i[1][0] or i[2][0]:
                                event.lambdas[0].emit(i[0],i[1],i[2])
                            
                        class Bottom(QStackedWidget):
                            def __init__(self, parent=None, root=None):
                                super().__init__()
                                self.root = root
                                self.parent = parent
                                self.init_wid()
                                
                            def init_wid(self):
                                self.start = self.Start(self,self.root)
                                self.mod = self.Mod(self,self.root)
                                self.world = self.World(self,self.root)
                                self.launch = self.Launch(self,self.root)
                                self.suspend = self.Suspend(self,self.root)
                                self.finished = self.Finished(self,self.root)

                            class Pages(QWidget):
                                def __init__(self, parent=None, root=None):
                                    super().__init__()
                                    self.root = root
                                    self.parent = parent
                                    self.index = self.parent.addWidget(self)

                                class Btn(QPushButton):
                                    def __init__(self, parent=None, root=None):
                                        super().__init__()
                                        self.root = root
                                        self.parent = parent
                                        self.setProperty("wid","btn")

                            class Start(Pages):
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)
                                    self.init_wid()
                                    self.langing()

                                def init_wid(self):
                                    self.layout = QVBoxLayout(self)
                                    self.layout.setContentsMargins(30,50,30,50)
                                    self.layout.setSpacing(10)
                                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                                    self.world =self.Btn(self,self.root)
                                    self.world.setFixedSize(QSize(170,50))
                                    self.layout.addWidget(self.world)

                                    self.world.clicked.connect(lambda: self.parent.setCurrentIndex(2))
                                    self.world.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(2))

                                def langing(self):
                                    self.world.setText(self.root.langer.get("wid.pages.start.gamebtn"))

                            class Mod(Pages):
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)
                                    self.init_wid()
                                    self.langing()

                                def init_wid(self):
                                    self.layout = QVBoxLayout(self)
                                    self.layout.setContentsMargins(30,50,30,50)
                                    self.layout.setSpacing(10)
                                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                                    self.cancle =self.Btn(self,self.root)
                                    self.cancle.setFixedSize(QSize(170,50))
                                    self.layout.addWidget(self.cancle)

                                    self.cancle.clicked.connect(lambda: self.parent.setCurrentIndex(0))
                                    self.cancle.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(0))

                                def langing(self):
                                    self.cancle.setText(self.root.langer.get("text.return"))

                            class World(Pages):
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)
                                    self.init_wid()
                                    self.langing()

                                def init_wid(self):
                                    self.layout = QVBoxLayout(self)
                                    self.layout.setContentsMargins(30,50,30,50)
                                    self.layout.setSpacing(10)
                                    self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)

                                    self.cancle =self.Btn(self,self.root)
                                    self.cancle.setFixedSize(QSize(170,50))
                                    self.layout.addWidget(self.cancle)

                                    self.cancle.clicked.connect(lambda: self.parent.setCurrentIndex(0))
                                    self.cancle.clicked.connect(lambda: self.parent.parent.parent.main.stack.setCurrentIndex(0))

                                def langing(self):
                                    self.cancle.setText(self.root.langer.get("text.return"))

                            class Launch(Pages):
                                """左 stacked 的启动/Java 下载状态页：只允许有一个 label 显示状态。"""
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)
                                    self.init_wid()
                                    self.langing()

                                def init_wid(self):
                                    self.layout = QVBoxLayout(self)
                                    self.layout.setContentsMargins(30,50,30,50)
                                    self.layout.setSpacing(10)
                                    self.layout.setAlignment(Qt.AlignCenter)
                                    self.label = QLabel(self)
                                    self.label.setProperty("wid", "title")
                                    self.label.setWordWrap(True)
                                    self.label.setAlignment(Qt.AlignCenter)
                                    self.label.setStyleSheet("font-size:14px;")
                                    self.layout.addWidget(self.label)

                                def langing(self):
                                    self.label.setText(self.root.langer.get("wid.pages.start.java.idle"))

                                def setStatus(self, status, pct=None):
                                    """唯一状态 label：resume/downloading/extracting/done/error/idle。

                                    pct 不为 None 时追加百分比（如 正在下载Java... 45%）。
                                    """
                                    key = "wid.pages.start.java." + status
                                    text = self.root.langer.get(key)
                                    if pct is not None:
                                        text = t(text, pct)
                                    else:
                                        # 无百分比时移除 $1 占位符（避免显示字面量）
                                        text = text.replace("$1%", "").replace("$1", "")
                                    self.label.setText(text)

                            class Suspend(Pages):
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)

                            class Finished(Pages):
                                """保存游戏数据进度页（index 5）。"""
                                def __init__(self, parent=None, root=None):
                                    super().__init__(parent,root)
                                    self.init_wid()

                                def init_wid(self):
                                    self.layout = QVBoxLayout(self)
                                    self.layout.setContentsMargins(30,50,30,50)
                                    self.layout.setSpacing(10)
                                    self.layout.setAlignment(Qt.AlignCenter)
                                    self.label = QLabel(self)
                                    self.label.setProperty("wid", "title")
                                    self.label.setWordWrap(True)
                                    self.label.setAlignment(Qt.AlignCenter)
                                    self.label.setStyleSheet("font-size:14px;")
                                    self.layout.addWidget(self.label)

                                def setStatus(self, step):
                                    self.label.setText(self.root.langer.get("wid.pages.start.finished.save%d" % step))

                    class Main(Mainw):
                        def __init__(self,parent=None,root=None):
                            super().__init__(parent,root)
                            self.init_wid()

                        def init_wid(self):
                            self.layout = QStackedLayout(self)
                            self.layout.setStackingMode(QStackedLayout.StackAll)

                            self.backg = self.Backg(self,self.root)
                            self.layout.addWidget(self.backg)

                            self.stack = QStackedWidget()
                            self.layout.addWidget(self.stack)

                            self.layout.setCurrentIndex(1)

                            self.start = self.Start(self,self.root)
                            self.mod = self.Mod(self,self.root)
                            self.world = self.World(self,self.root)
                            self.launch = self.Launch(self,self.root)
                            self.log = self.Log(self,self.root)
                            self.finished = self.Finished(self,self.root)




                        class _Main(QWidget):
                            def __init__(self,parent=None,root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.setProperty("wid","color2")
                                self.index = self.parent.stack.addWidget(self)

                            def showEvent(self,event):
                                super().showEvent(event)
                                self.parent.backg.setVisible(not self.testAttribute(Qt.WA_StyledBackground))
                                self.parent.stack.setStyleSheet(""if self.testAttribute(Qt.WA_StyledBackground) else "background:transparent;")


                        class Start(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.init_wid()
                                self.langing()
                                self.setAttribute(Qt.WA_StyledBackground,False)

                            def init_wid(self):
                                self.layout = QGridLayout(self)
                                self.layout.setContentsMargins(30,30,30,30)
                                self.layout.setSpacing(5)

                                self.layout.setColumnStretch(0,1)
                                self.layout.setColumnStretch(1,0)
                                self.layout.setColumnStretch(2,0)
                                self.layout.setRowStretch(0,1)
                                self.layout.setRowStretch(1,0)
                                self.layout.setRowStretch(2,0)

                                self.start = self.Btn(self,self.root,"255,184, 0")
                                self.start.setFixedSize(180,50)
                                self.layout.addWidget(self.start,1,1,1,2)

                                self.settings = self.Btn(self,self.root,"110,65,151")
                                self.settings.setFixedSize(50,50)
                                self.settings.setIconSize(QSize(25,25))
                                self.settings.setIcon(QIcon(QPixmap(getPath("src/assets/buttons/setting.png")).scaled(50,50,Qt.KeepAspectRatio,Qt.FastTransformation)))
                                self.layout.addWidget(self.settings,2,2,1,1)

                                self.mod = self.Btn(self,self.root,"52, 152, 219")
                                self.mod.setFixedHeight(50)
                                self.layout.addWidget(self.mod,2,1,1,1)

                                self.start.clicked.connect(self.on_start_clicked)

                            def on_start_clicked(self):
                                """开始游戏：无可用 Java 时自动触发下载流程（launcher 会发 java_missing）。"""
                                root = self.root
                                if root.java_flow is not None:
                                    return  # 已有 Java 下载流程在运行
                                # 手动指定了 Java 则直接用，否则 launcher 内部自动选择并校验
                                root.launcher.run(root.settings["defaultGame"])

                            def langing(self):
                                self.start.setText(self.root.langer.get("wid.pages.start.startbtn"))
                                self.mod.setText(self.root.langer.get("wid.pages.start.modbtn"))
                                

                            class Btn(QPushButton):
                                def __init__(self,parent=None,root=None,color="0,0,0"):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.color = color
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.setStyleSheet(f"""
                                        QPushButton{{
                                            background-color:rgba({self.color},0.4);
                                            color:white;
                                            border-radius:10px;
                                            font-size:16px;

                                        }}
                                        QPushButton:hover{{
                                            background-color:rgba({self.color},1);
                                        }}
                                    """)

                        class Mod(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.setAttribute(Qt.WA_StyledBackground,True)

                        class World(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.setAttribute(Qt.WA_StyledBackground,True)
                                self.games = {}
                                self.init_wid()
                                self.renovate()
                                self.games["<:|default|:>"].gameW.show()
                                self.root.signals.connect("gameRenovated", self.renovate)

                            def init_wid(self):
                                self.layout = QVBoxLayout(self)
                                self.layout.setContentsMargins(0, 0, 0, 0)
                                self.layout.setSpacing(0)

                                self.scroll = QScrollArea(self)
                                self.scroll.setWidgetResizable(True)
                                self.scroll.setFrameShape(QFrame.NoFrame)
                                self.layout.addWidget(self.scroll)

                                self.main = QWidget()
                                self.main.setProperty("wid","color2")
                                self.scroll_layout = QVBoxLayout(self.main)
                                self.scroll_layout.setContentsMargins(10,10,10,10)
                                self.scroll_layout.setSpacing(10)
                                self.scroll_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
                                self.scroll.setWidget(self.main)

                            def renovate(self):
                                games = copy.deepcopy(self.root.settings["gameList"])
                                keys_to_delete = []
                                for key, value in list(self.games.items()):
                                    if key not in games:
                                        value.deleteLater()
                                        keys_to_delete.append(key)
                                    else:
                                        if set(value.games) != set(games[key]):
                                            value.renovate(key)
                                        del games[key]
                                for key in keys_to_delete:
                                    del self.games[key]
                                for key, value in games.items():
                                    self.games[key] = self.Lists(self, self.root)
                                    self.games[key].renovate(key)
                                

                            class Lists(QWidget):
                                def __init__(self,parent=None,root=None):
                                    super().__init__()
                                    self.parent = parent
                                    self.root = root
                                    self.light = None
                                    self.game = ""
                                    self.btnPix = [QPixmap(),QPixmap()]
                                    self.setAttribute(Qt.WA_StyledBackground, True)
                                    self.games = {}
                                    self.launch = False
                                    self.setStyleSheet("border-radius:10px;max-width:600px;")
                                    self.init_wid()
                                    
                                    self.parent.scroll_layout.addWidget(self)

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

                                    self.gameW = VisiWidget()
                                    self.gameW.visibled.connect(lambda i:self.button.setIcon(QIcon(self.btnPix[int(i)])))
                                    self.layout.addWidget(self.gameW)
                                    self.gameW.hide()

                                    self.gameL = QVBoxLayout(self.gameW)
                                    self.gameL.setContentsMargins(0,0,0,0)
                                    self.gameL.setSpacing(5)
                                    self.line = QWidget()
                                    self.line.setFixedHeight(1)
                                    self.line.setProperty("wid","line")
                                    self.gameL.addWidget(self.line)

                                    self.button.clicked.connect(lambda:self.gameW.setVisible(not self.gameW.isVisible()))


                                def renovate(self, games):
                                    self.game = games
                                    gamelist = copy.deepcopy(self.root.settings["gameList"][games])
                                    for key, value in list(self.games.items()):
                                        value.deleteLater()
                                    self.games.clear()
                                    for game_name in gamelist:
                                        self.games[game_name] = self.Item(self, self.root, game_name)
                                    self.langing()
                                    self.label2.setText(f"({len(gamelist)})")

                                def langing(self):
                                    self.label.setText(self.game if self.game != "<:|default|:>" else self.root.langer.get("text.default"))

                                def lighting(self,light):
                                    if self.light != light:
                                        self.light = light
                                        self.btnPix[1] = change_color(getPath("src/assets/actions/eye.png"),QColor(25,25,25) if light else QColor(220,220,220))
                                        self.btnPix[0] = change_color(getPath("src/assets/actions/eye-off.png"),QColor(25,25,25) if light else QColor(220,220,220))
                                    self.button.setIcon(QIcon(self.btnPix[int(self.gameW.isVisible())]))

                                class Item(QPushButton):
                                    def __init__(self,parent=None,root=None,game=None):
                                        super().__init__()
                                        self.parent = parent
                                        self.root = root
                                        self.game = game
                                        self.parent.gameL.addWidget(self)
                                        self.setFixedHeight(40)
                                        self.setProperty("wid","lbtn")
                                        self.init_wid()
                                        self.clicked.connect(lambda:self.parent.parent.parent.parent.changeGame(self.game))

                                    def init_wid(self):
                                        self.layout = QHBoxLayout(self)
                                        self.layout.setContentsMargins(5,5,5,5)
                                        self.layout.setSpacing(10)

                                        self.pixmap = QLabel()
                                        self.pixmap.setFixedSize(30,30)
                                        self.pixmap.setStyleSheet("width:30px;")
                                        self.pixmap.setScaledContents(True)
                                        self.layout.addWidget(self.pixmap,0)

                                        self.textW = QWidget()
                                        self.textW.setStyleSheet("background:transparent;")
                                        self.layout.addWidget(self.textW)

                                        self.textL = QVBoxLayout(self.textW)
                                        self.textL.setContentsMargins(0,0,0,0)
                                        self.textL.setSpacing(0)

                                        self.text = QLabel()
                                        self.text.setStyleSheet("background:transparent;font-size:14px;")
                                        self.text.setProperty("wid","text")
                                        self.textL.addWidget(self.text,0)
                                        self.text.setFixedHeight(20)

                                        self.version = QLabel()
                                        self.version.setStyleSheet("background:transparent;")
                                        self.version.setProperty("wid","lbtn")
                                        self.textL.addWidget(self.version)
                                        self.version.setFixedHeight(10)

                                        self.layout.addStretch(1)

                                    def showEvent(self,event):
                                        super().showEvent(event)
                                        vers = mdtScanner.getMdtMsg(self.game)
                                        if vers:
                                            pngPath = vers.get("icon")
                                            if pngPath is not None:
                                                self.pixmap.setPixmap(QPixmap(pngPath))
                                            self.text.setText(self.game)
                                            self.version.setText(f"v{vers['number']}.{vers['build']}{vers['modifier']}")



                        class Launch(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.setAttribute(Qt.WA_StyledBackground,True)

                        class Log(_Main):
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.setAttribute(Qt.WA_StyledBackground,True)

                        class Finished(_Main):
                            """保存游戏数据进度页（index 5）。"""
                            def __init__(self,parent=None,root=None):
                                super().__init__(parent,root)
                                self.setAttribute(Qt.WA_StyledBackground,True)
                                self.init_wid()

                            def init_wid(self):
                                self.layout = QVBoxLayout(self)
                                self.layout.setContentsMargins(30,30,30,30)
                                self.layout.setSpacing(10)
                                self.layout.setAlignment(Qt.AlignCenter)
                                self.label = QLabel(self)
                                self.label.setProperty("wid", "title")
                                self.label.setWordWrap(True)
                                self.label.setAlignment(Qt.AlignCenter)
                                self.label.setStyleSheet("font-size:16px;")
                                self.layout.addWidget(self.label)

                            def setStatus(self, step):
                                self.label.setText(self.root.langer.get("wid.pages.start.finished.save%d" % step))




                        class Backg(QWidget):
                            def __init__(self,parent=None,root=None):
                                super().__init__()
                                self.parent = parent
                                self.root = root
                                self.setAttribute(Qt.WA_StyledBackground, True)
                                self.png = 0
                                self.pixs = [None,None]
                                self.init_wid()
                                self.setPixmap(QPixmap(getPath("src/assets/backg/1.png")))

                            def init_wid(self):
                                self.pngs = [QLabel(self),QLabel(self)]
                                

                                self.shadow = QWidget(self)
                                self.shadow.setAttribute(Qt.WA_StyledBackground, True)
                                self.shadow.setProperty("wid", "shadow")

                                self.pngs[1].hide()
                                self.resizeEvent(None)
                                
                            def setPixmap(self,pix=None):
                                self.pixs[1-self.png] = pix
                                self.pngs[1-self.png].hide()
                                pix = self.pixs[1-self.png].scaled(
                                    self.size(),
                                    Qt.KeepAspectRatioByExpanding,
                                    Qt.SmoothTransformation
                                ) if self.pixs[1-self.png] is not None else QPixmap()
                                self.pngs[1-self.png].setPixmap(pix)
                                self.pngs[1-self.png].stackUnder(self.shadow)
                                self.pngs[1-self.png].show()
                                self.png = 1-self.png
                                

                            def resizeEvent(self,event):
                                for i,n in enumerate(self.pngs,start=0):
                                    n.setFixedSize(self.size())
                                    pix = self.pixs[i].scaled(
                                            self.size(),
                                            Qt.KeepAspectRatioByExpanding,
                                            Qt.SmoothTransformation
                                    ) if self.pixs[i] is not None else QPixmap()
                                    n.setPixmap(pix)
                                self.shadow.setGeometry(0,0,200,self.height())
                                super().resizeEvent(event)


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
                                        
                                    
                #TODO: 游戏管理界面
                class Game(Page):
                    def __init__(self, parent=None, root=None, text=None, logo=None):
                        super().__init__(parent, root, text, logo)

                    class Main(Mainw):
                        def __init__(self, parent=None, root=None):
                            super().__init__(parent, root)
                            self.init_wid()

                        def init_wid(self):
                            self.layout = QVBoxLayout(self)
                            self.layout.setContentsMargins(0, 0, 0, 0)
                            self.layout.setSpacing(0)

                            self.todoText = QLabel("UNFINISHED")
                            self.todoText.setProperty("wid", "text")
                            self.todoText.setAlignment(Qt.AlignCenter)
                            self.todoText.setStyleSheet("font-size: 20px;")
                            self.layout.addWidget(self.todoText,1)


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

        class FloatingStack(QWidget):
            def __init__(self,parent=None,root=None):
                super().__init__(parent)
                self.parent = parent
                self.root = root
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.init_wid()
                self.refresh()

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0,0,0,0)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignTop)

                self.line = QWidget()
                self.line.setProperty("wid","line")
                self.line.setFixedHeight(1)
                self.layout.addWidget(self.line)

                self.l2w = QWidget()
                self.layout.addWidget(self.l2w,1)

                self.l2 = QHBoxLayout(self.l2w)
                self.l2.setContentsMargins(0,0,0,0)
                self.l2.setSpacing(0)
                self.l2.setAlignment(Qt.AlignLeft)

                self.left = self.Left(self,self.root)
                self.l2.addWidget(self.left,0)

                self.line2 = QWidget()
                self.line2.setProperty("wid","line")
                self.line2.setFixedWidth(1)
                self.l2.addWidget(self.line2,0)

                self.main = self.Main(self,self.root)
                self.l2.addWidget(self.main,1)

            def refresh(self):
                # 栈空时隐藏整个浮层，否则显示并提层
                if self.main.count() <= 0:
                    self.hide()
                else:
                    self.show()
                    self.raise_()
                self.left.refresh()

            def add_page(self,wid):
                # 入栈：添加页面并切换到栈顶
                self.main.addWidget(wid)
                self.main.setCurrentWidget(wid)
                self.refresh()

            def pop_page(self):
                # 出栈：移除栈顶并销毁
                if self.main.count() <= 0:
                    return
                wid = self.main.currentWidget()
                self.main.removeWidget(wid)
                on_close = getattr(wid, "on_close", None)
                if on_close is not None:
                    on_close()
                wid.deleteLater()
                if self.main.count() > 0:
                    self.main.setCurrentIndex(self.main.count() - 1)
                self.refresh()

            def clear(self):
                while self.main.count() > 0:
                    wid = self.main.widget(0)
                    self.main.removeWidget(wid)
                    on_close = getattr(wid, "on_close", None)
                    if on_close is not None:
                        on_close()
                    wid.deleteLater()
                self.refresh()

            class Left(QWidget):
                def __init__(self,parent=None,root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.setFixedWidth(40)
                    self.init_wid()

                def init_wid(self):
                    self.layout = QVBoxLayout(self)
                    self.layout.setContentsMargins(5,5,5,5)
                    self.layout.setSpacing(0)
                    self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

                    # 内置退出按钮（左箭头，返回上一页）
                    self.back = self.Back(self,self.root)
                    self.layout.addWidget(self.back,0,Qt.AlignHCenter)

                    # 清空整个栈按钮（叉号）
                    self.btn_close = self.Close(self,self.root)
                    self.layout.addWidget(self.btn_close,0,Qt.AlignHCenter)

                def refresh(self):
                    # 栈空时禁用两个按钮
                    enabled = self.parent.main.count() > 0
                    self.back.setEnabled(enabled)
                    self.btn_close.setEnabled(enabled)

                class Back(QPushButton):
                    def __init__(self,parent=None,root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.setFixedSize(30,30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid","tbtn")
                        self.langing()
                        self.lighting(self.root.settings["theme"])
                        self.clicked.connect(self.parent.parent.pop_page)

                    def lighting(self, light: bool):
                        color = QColor(120,120,120) if light else QColor(200,200,200)
                        logo = change_color("src/assets/nav/back.png", color)
                        self.setIcon(QIcon(logo.pixmap(48,48)))

                    def langing(self):
                        self.setToolTip(self.root.langer.get("text.return"))

                class Close(QPushButton):
                    def __init__(self,parent=None,root=None):
                        super().__init__(parent)
                        self.parent = parent
                        self.root = root
                        self.setFixedSize(30,30)
                        self.setAttribute(Qt.WA_StyledBackground, False)
                        self.setProperty("wid","tbtn")
                        self.langing()
                        self.lighting(self.root.settings["theme"])
                        self.clicked.connect(self.parent.parent.clear)

                    def lighting(self, light: bool):
                        color = QColor(120,120,120) if light else QColor(200,200,200)
                        logo = change_color("src/assets/tribtns/close.png", color)
                        self.setIcon(QIcon(logo.pixmap(48,48)))

                    def langing(self):
                        self.setToolTip(self.root.langer.get("wid.top.close"))

            class Main(QStackedWidget):
                def __init__(self,parent=None,root=None):
                    super().__init__(parent)
                    self.parent = parent
                    self.root = root
                    self.init_wid()

                def init_wid(self):
                    # QStackedWidget 内部自带 QStackedLayout 管理页面，无需（也不能）再设置 layout
                    pass


    class Tray(QSystemTrayIcon):
        def __init__(self, parent=None, root=None):
            super().__init__()
            self.parent = parent
            self.root = root
            self.theme = None
            self.init_ui()
            self.init_wid()
            self.activated.connect(self.on_tray_activated)
            self.root.logger.info(self.root.langer.get("log.info.trayLoad"))

        def on_tray_activated(self, reason):
            if reason == QSystemTrayIcon.ActivationReason.Trigger:
                self.root.logger.debug("Tray clicked by L-mouse button")
                self.root.window.restore_from_tray()

        def init_ui(self):
            self.setToolTip("Book Mdt Launcher")
            self.setIcon_()
            self.show()

        def init_wid(self):
            self.menu = QMenu()

            self.menu_title = QAction("Book Mdt Launcher", self)
            self.menu_title.triggered.connect(lambda: QTimer.singleShot(0, self.root.window.restore_from_tray))
            self.menu.addAction(self.menu_title)

            self.menu.addSeparator()  # 添加分隔线

            self.menu_close = QAction("", self)
            self.menu_close.triggered.connect(QApplication.quit)
            self.menu.addAction(self.menu_close)

            self.langing()
            self.setContextMenu(self.menu)

        def langing(self):
            self.menu_close.setText(self.root.langer.get("tray.menu.close"))

        def setIcon_(self):
            """根据系统主题设置托盘图标"""
            theme = "light" if self.root.winreg.taskbar_theme() == "dark" else "dark"
            if self.theme != theme:
                self.theme = theme
                icon_path = getPath(f"src/assets/icons/{theme}.png")

                # 检查文件是否存在，防止路径错误导致无图标
                if not os.path.exists(icon_path):
                    self.root.logger.warning(t(self.root.langer.get("log.warning.trayIconPath"), icon_path))

                icon = QIcon(icon_path)
                self.setIcon(icon)
                self.root.logger.info(t(self.root.langer.get("log.info.trayTheme"), "light" if theme == "light" else "dark"))

    class Logger():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root
            # 缓存已创建的 logger 实例，避免重复创建
            self._loggers = {}
            # 初始化基础配置
            self._setup_base_logging()

        def _setup_base_logging(self):
            """
            配置根 Logger ("Main") 的 Handler 和格式。
            其他子 Logger 将共享这些 Handler。
            """
            loglevel = logging.INFO
            self.base_logger_name = "Main"

            # 获取或创建主 logger
            main_logger = logging.getLogger(self.base_logger_name)
            main_logger.setLevel(loglevel)

            # 防止重复添加 handler
            if main_logger.handlers:
                self._loggers[self.base_logger_name] = main_logger
                return

            # 控制台 handler
            console = logging.StreamHandler()
            console.setLevel(loglevel)

            # 文件 handler 配置
            self.log_dir = getPath("BML/logs")
            os.makedirs(self.log_dir, exist_ok=True)

            now = datetime.now()
            timestamp = now.strftime("%Y%m%d%H%M%S") + f".{now.microsecond // 1000:03d}"
            timestamp_file = os.path.join(self.log_dir, f"{timestamp}.log")
            latest_file = os.path.join(self.log_dir, "latest.log")

            file_handler_timestamp = logging.FileHandler(timestamp_file, encoding="utf-8")
            file_handler_latest = logging.FileHandler(latest_file, mode='w', encoding="utf-8")

            file_handler_timestamp.setLevel(loglevel)
            file_handler_latest.setLevel(loglevel)

            # 设置日志格式：包含 %(name)s 以区分不同模块
            formatter = logging.Formatter('[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s')
            console.setFormatter(formatter)
            file_handler_timestamp.setFormatter(formatter)
            file_handler_latest.setFormatter(formatter)

            # 将 handler 添加到主 logger
            main_logger.addHandler(console)
            main_logger.addHandler(file_handler_timestamp)
            main_logger.addHandler(file_handler_latest)

            self._loggers[self.base_logger_name] = main_logger

        def _get_logger(self, name=None):
            """
            获取指定名称的 logger。
            如果 name 为 None 或 "Main"，返回主 logger。
            否则返回 "Main.{name}" 的子 logger。
            """
            if not name or name == "Main":
                target_name = self.base_logger_name
            else:
                # 使用层级命名，例如 "Main.Cmd"，这样它们会共享 Main 的 Handler
                target_name = f"{self.base_logger_name}.{name}"

            if target_name not in self._loggers:
                logger = logging.getLogger(target_name)
                # 子 logger 默认继承父 logger 的级别和 handler，无需额外配置
                # 但如果需要单独控制级别，可以在此设置：
                # logger.setLevel(logging.DEBUG)
                self._loggers[target_name] = logger

            return self._loggers[target_name]

        def _cleanup_old_logs(self):
            max_num = self.root.settings["maxLogNum"]
            if not os.path.exists(self.log_dir):
                return
            files = [f for f in os.listdir(self.log_dir) if f.endswith('.log') and f != 'latest.log']
            files.sort()
            while len(files) > max_num:
                oldest = files.pop(0)
                try:
                    os.remove(os.path.join(self.log_dir, oldest))
                    # 清理日志时使用主 logger 记录
                    self._loggers[self.base_logger_name].info(t(self.root.langer.get("log.info.cleanoldlogs"), oldest))
                except Exception as e:
                    pass

        # 修改日志方法，增加 name 参数，默认为 None (即 Main)
        def debug(self, msg, name=None):
            self._get_logger(name).debug(msg)

        def info(self, msg, name=None):
            self._get_logger(name).info(msg)

        def warning(self, msg, name=None):
            self._get_logger(name).warning(msg)

        def error(self, msg, name=None, exc_info=False):
            self._get_logger(name).error(msg, exc_info=exc_info)

        def critical(self, msg, name=None):
            self._get_logger(name).critical(msg)

    class Langer():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root

            # 确定最终使用的语言
            final_lang = self.root.settings["language"]

            # 1. 检查配置的语言是否可用
            if final_lang not in self.get_langs():
                if final_lang is not None:
                    self.root.logger.warning(f"Language '{final_lang}' not found, using system display language: " + str(self.root.winreg.display_language()))

                # 2. 尝试使用系统语言
                sys_lang = self.root.winreg.display_language()
                if sys_lang and sys_lang in self.get_langs():
                    final_lang = sys_lang
                else:
                    # 3.  fallback 到 en-US
                    if sys_lang:
                        self.root.logger.warning(f"System display language '{sys_lang}' not found, using: en-US")
                    else:
                        self.root.logger.warning("System display language detection failed, using: en-US")
                    final_lang = "en-US"

                # 更新设置中的语言为最终确定的语言
                self.root.settings["language"] = final_lang
                self.root.saveSettings()

            self.current_lang = final_lang
            self.default_lang = "en-US"  # 定义默认回退语言

            self.load(self.current_lang)

        def load(self, lang):
            """加载语言文件并自动刷新所有支持多语言的控件"""
            lang_path = getPath(f"src/lang/{lang}.json")
            default_lang_path = getPath(f"src/lang/{self.default_lang}.json")

            try:
                with open(lang_path, "r", encoding="utf-8") as f:
                    self.langs = json.load(f)
                self.parent.settings["language"] = lang
            except Exception as e:
                self.root.logger.error(f"Failed to load language file {lang_path}: {e}")
                self.langs = {}

            # 预加载默认语言以便快速回退，避免每次get都读取文件
            try:
                if lang != self.default_lang:
                    with open(default_lang_path, "r", encoding="utf-8") as f:
                        self.default_langs = json.load(f)
                else:
                    self.default_langs = self.langs
            except Exception as e:
                self.root.logger.warning(f"Failed to load default language file {default_lang_path}: {e}")
                self.default_langs = {}

            # 自动加载每个控件里的 langing 模块
            try:
                self._refresh_all_widgets()
                self.root.tray.langing()
            except:
                pass

        def _refresh_all_widgets(self):
            """递归查找所有控件并调用 langing 方法"""
            def notify_langing(widget):
                # 检查是否有 langing 方法且可调用
                if hasattr(widget, 'langing') and callable(widget.langing):
                    try:
                        widget.langing()
                    except Exception as e:
                        # 避免因为某个控件翻译失败导致整个程序崩溃
                        self.root.logger.debug(f"Error calling langing on {widget}: {e}")

                # 递归处理子控件
                for child in widget.children():
                    notify_langing(child)

            # 从主窗口开始遍历
            if hasattr(self.root, 'window') and self.root.window:
                QTimer.singleShot(0, lambda: notify_langing(self.root.window))
            self.root.logger.info(self.get("init.load"))

        def get(self, key):
            """
            获取翻译文本，支持三级回退：
            1. 当前语言 (zh-CN)
            2. 默认语言 (en-US)
            3. 原键名
            """
            if key in self.langs:
                return self.langs[key]
            if key in self.default_langs:
                return self.default_langs[key]
            return key

        def get_langs(self):
            langs = []
            lang_dir = getPath("src/lang")
            try:
                if not os.path.exists(lang_dir):
                    return langs
                for file in os.listdir(lang_dir):
                    if file.endswith(".json"):
                        langs.append(file.replace(".json", ""))
            except Exception as e:
                self.root.logger.error(f"Failed to list language files: {e}")
            return langs

        def get_langs_info(self):
            """
            获取所有语言文件的名称及 init 信息。
            返回字典：键为语言文件名（不带后缀），值为列表 [init, init.en]
            """
            info = {}
            lang_dir = getPath("src/lang")
            try:
                if not os.path.exists(lang_dir):
                    return info
                for file in os.listdir(lang_dir):
                    if file.endswith(".json"):
                        lang_name = file.replace(".json", "")
                        lang_path = os.path.join(lang_dir, file)
                        try:
                            with open(lang_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            info[lang_name] = [
                                data.get("init", lang_name),
                                data.get("init.en", lang_name)
                            ]
                        except Exception as e:
                            self.root.logger.error(f"Failed to read language file {lang_path}: {e}")
                            info[lang_name] = [lang_name, lang_name]
            except Exception as e:
                self.root.logger.error(f"Failed to list language files: {e}")
            return info

    class Signals(QObject):
        """
        动态信号管理器 —— 所有信号都是真正的 PySide6 Signal。

        用法:
            signals = Signals()
            signals.register("dataReady", Signal(str, int))
            signals.connect("dataReady", lambda s, i: print(s, i))
            signals.emit("dataReady", "hello", 42)
            signals.disconnect("dataReady", callback)
            signals.cancel("dataReady")  # 完全移除
        """

        def __init__(self, parent=None, root=None):
            super().__init__()
            self.parent = parent
            self.root = root
            # name → _SignalHolder 实例
            self._holders = {}

        @staticmethod
        def _make_holder_cls(sig):
            """根据 Signal 签名动态创建一个 QObject 子类，携带一个 signal 属性。"""
            return type('_SigHolder', (QObject,), {'signal': sig})

        def register(self, name, sig=None):
            """
            注册一个信号。
            sig: Signal 实例，如 Signal(), Signal(str), Signal(int, bool)
            返回该 Signal，可直接 connect。
            若同名已存在则返回已有信号。
            """
            if sig is None:
                sig = Signal()
            if name in self._holders:
                return self._holders[name].signal
            HolderCls = self._make_holder_cls(sig)
            holder = HolderCls(self)
            self._holders[name] = holder
            return holder.signal

        def connect(self, name, callback):
            """连接到已注册信号。若未注册则自动以无参信号注册。"""
            if name not in self._holders:
                self.register(name)
            self._holders[name].signal.connect(callback)

        def emit(self, name, *args):
            """触发指定信号。"""
            if name in self._holders:
                self._holders[name].signal.emit(*args)

        def disconnect(self, name=None, callback=None):
            """
            断开连接。
            - disconnect(name, callback): 断开指定回调
            - disconnect(name): 断开该信号所有连接
            - disconnect(): 断开所有信号所有连接
            """
            if name is None:
                for h in self._holders.values():
                    try:
                        h.signal.disconnect()
                    except TypeError:
                        pass
                return
            if name not in self._holders:
                return
            sig = self._holders[name].signal
            if callback is not None:
                try:
                    sig.disconnect(callback)
                except TypeError:
                    pass
            else:
                try:
                    sig.disconnect()
                except TypeError:
                    pass

        def cancel(self, name):
            """完全移除指定信号及其所有连接。"""
            if name in self._holders:
                self._holders[name].signal.disconnect()
                self._holders[name].deleteLater()
                del self._holders[name]

        def clear(self, name):
            """清除指定信号的所有回调（不删除信号本身）。"""
            if name in self._holders:
                try:
                    self._holders[name].signal.disconnect()
                except TypeError:
                    pass

    class Winreg():
        def __init__(self, parent=None, root=None):
            self.parent = parent
            self.root = root

        def display_language(self):
            try:
                dll = ctypes.windll.kernel32
                langId = dll.GetUserDefaultUILanguage()
                langStr = locale.windows_locale.get(langId)
                if langStr:
                    return langStr.replace("_", "-")
            except Exception as e:
                self.root.logger.error(f"Failed to get language, using en-US: {e}")
            return "en-US"

        def taskbar_theme(self):
            """
            获取 Windows 系统外壳主题颜色 (light/dark)
            """
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
                return "light" if value == 1 else "dark"
            except Exception as e:
                self.root.logger.warning(f"Failed to get system theme: {e}")
                return "light"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    socket = QLocalSocket()
    socket.connectToServer("BookMdtLauncherMI")

    if socket.waitForConnected(200):
        socket.write(b"MAINWINSHOW")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        sys.exit(0)
    else:
        socket.deleteLater()

        try:
            main = Main(app)
            main.window.show()
            code = app.exec()
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(code)
        except Exception as e:
            err_msg = traceback.format_exc()

            print(err_msg)

            dialog = QDialog()
            dialog.setWindowTitle("Book MDT Launcher - Error")
            dialog.setMinimumSize(550, 400)
            dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

            layout = QVBoxLayout(dialog)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)

            info_label = QLabel(
                "启动器貌似出现了一点问题，请带上下面这段错误信息前往 "
                "https://github.com/ch-BookBanana/BookMdtLauncher/issues 提交反馈\n\n"
                "The launcher seems to have encountered a problem. Please take the"
                "following error message and submit feedback at "
                "https://github.com/ch-BookBanana/BookMdtLauncher/issues \n"
            )
            info_label.setWordWrap(True)
            info_label.setStyleSheet("font-size: 13px;")
            layout.addWidget(info_label)

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(err_msg)
            text_edit.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
            layout.addWidget(text_edit, 1)

            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            skip_btn = QPushButton("跳转 Skip")
            skip_btn.setFixedWidth(120)
            skip_btn.clicked.connect(lambda: webbrowser.open(
                "https://github.com/ch-BookBanana/BookMdtLauncher/issues"
            ))
            btn_layout.addWidget(skip_btn)

            cancel_btn = QPushButton("取消 Cancel")
            cancel_btn.setFixedWidth(120)
            cancel_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(cancel_btn)

            layout.addLayout(btn_layout)

            dialog.rejected.connect(QApplication.quit)
            dialog.exec()
            # 出错分支同样强制退出，避免残留线程导致挂起/崩溃弹窗
            os._exit(1)

