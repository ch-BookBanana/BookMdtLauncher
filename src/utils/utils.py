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
import re
from urllib.parse import urljoin, urlparse

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

import hashlib

from concurrent.futures import ThreadPoolExecutor, as_completed
import markdown
import threading

from .mdtScanner import mdtScanner
from .path_utils import getPath


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