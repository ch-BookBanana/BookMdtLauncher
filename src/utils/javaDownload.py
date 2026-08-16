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

"""Java 自动下载流程管理。

- javaDownload.json（BML/.tmp/javaDownload.json）记录 Java 下载信息与状态：
    status: downloading / extracting / done / error
    urls  : 多源下载列表（QDownloader 竞速选优）
    dest  : jdk zip 下载目标路径（BML/.tmp/Java/）
- 下载：QDownloader 全程子线程运行并注册到全局路由表；
- 解压：解压到 BML/.Java/<version>/bin/java.exe（zip 顶层目录自动剥离）。
- 中断续传：下载/解压中断时保留 javaDownload.json，
  程序下次启动读取并继续流程（resume=True）。
"""

import os
import json
import time
import threading
import zipfile
import shutil
import logging
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal

from .path_utils import getPath
from .QDownloader import QDownloader

_log = logging.getLogger("Main.JavaDownload")

# i18n：日志文本来自语言文件（main.py 初始化 langer 后注入翻译函数）。
# 未注入时回退为 key 本身，日志仍可读、不影响运行。
_tr_func = None


def set_tr_func(fn):
    """注入语言翻译函数（langer.get），供本模块日志 i18n。"""
    global _tr_func
    _tr_func = fn


def _tr(key, *args):
    """取翻译文本并替换 $1/$2 占位符；未注入翻译函数时原样返回 key。"""
    text = _tr_func(key) if _tr_func is not None else key
    try:
        for i, arg in enumerate(reversed(args), start=1):
            text = text.replace("$%d" % i, str(arg))
    except Exception:
        pass
    return text


# ---------------- 路径与默认版本 ----------------
TMP_DIR = getPath(os.path.join("BML", ".tmp"))
JAVA_TMP_DIR = os.path.join(TMP_DIR, "Java")
JAVA_ROOT = getPath(os.path.join("BML", ".Java"))
JAVA_INFO_PATH = os.path.join(TMP_DIR, "javaDownload.json")

DEFAULT_MAJOR = 17
DEFAULT_VERSION = "17.0.20"
DEFAULT_BUILD = 8


def _build_urls(major=DEFAULT_MAJOR, version=DEFAULT_VERSION, build=DEFAULT_BUILD):
    """构建 JDK 多源下载列表（清华镜像 + GitHub Adoptium 官方），用于竞速选优。"""
    return [
        "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/%d/jdk/x64/windows/OpenJDK%dU-jdk_x64_windows_hotspot_%s_%d.zip" % (major, major, version, build),
        "https://github.com/adoptium/temurin%d-binaries/releases/download/jdk-%s%%2B%d/OpenJDK%dU-jdk_x64_windows_hotspot_%s_%d.zip" % (major, version, build, major, version, build),
    ]


def get_status():
    """返回 javaDownload.json 记录的状态：downloading/extracting/done/error，无记录返回 None。"""
    info = load_info()
    return info.get("status") if info else None


def load_info():
    """读取 javaDownload.json 内容，失败返回 None。"""
    try:
        if not os.path.isfile(JAVA_INFO_PATH):
            return None
        with open(JAVA_INFO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_info(info):
    """写入 javaDownload.json（失败静默）。"""
    try:
        os.makedirs(TMP_DIR, exist_ok=True)
        with open(JAVA_INFO_PATH, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, separators=(',', ':'))
    except Exception:
        pass


class _ExtractWorker(QObject):
    """解压线程：把 jdk zip 解压到 BML/.Java/<version>/（在 QThread 中运行）。

    自动剥离 zip 顶层目录（如 jdk-17.0.20/），确保最终路径为
    BML/.Java/<version>/bin/java.exe。
    """
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool)

    def __init__(self, zip_path, target_dir, version, parent=None):
        super().__init__(parent)
        self.zip_path = zip_path
        self.target_dir = target_dir
        self.version = version
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def run(self):
        try:
            ok = self._extract()
        except Exception:
            ok = False
        self.finished.emit(ok)

    def _extract(self):
        extract_root = os.path.join(JAVA_TMP_DIR, "extract_" + self.version)
        if os.path.isdir(extract_root):
            shutil.rmtree(extract_root, ignore_errors=True)
        os.makedirs(extract_root, exist_ok=True)

        # 解压（跳过 zip 顶层目录，进度按已解压字节汇报）
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            infos = zf.infolist()
            total = sum(i.file_size for i in infos) or 1
            done = 0
            for info in infos:
                if self._cancelled.is_set():
                    return False
                parts = info.filename.split("/", 1)
                name = parts[1] if len(parts) > 1 else ""
                if not name:
                    continue
                target = os.path.join(extract_root, name)
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                done += info.file_size
                self.progress.emit(done, total)

        # 定位 java.exe 所在 JDK 根目录（.../bin/java.exe → JDK 根）
        jdk_root = None
        for current, dirs, files in os.walk(extract_root):
            if "java.exe" in files:
                jdk_root = os.path.dirname(current)
                break
        if not jdk_root or not os.path.isfile(os.path.join(jdk_root, "bin", "java.exe")):
            return False

        # 移动为 BML/.Java/<version>/（必须满足 <version>/bin/java.exe 约定）
        target = self.target_dir
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.abspath(jdk_root) != os.path.abspath(target):
            shutil.move(jdk_root, target)

        if not os.path.isfile(os.path.join(target, "bin", "java.exe")):
            return False

        shutil.rmtree(extract_root, ignore_errors=True)
        try:
            os.remove(self.zip_path)
        except OSError:
            pass
        return True


class JavaDownloadFlow(QObject):
    """Java 自动下载/解压流程。

    信号：
        status_changed(str)       downloading / extracting / done / error
        progress(int, int)        下载进度（已下载字节, 总字节）
        extract_progress(int,int) 解压进度（已解压字节, 总字节）
        finished(bool)            流程结束（True 成功 / False 失败或取消）
        error(str)                错误信息
        cancelled()               下载被用户取消/退出（UI 据此显示"已取消"而非"失败"）

    resume=True 时从 BML/.tmp/javaDownload.json 读取信息继续
    （程序启动延续流程）；否则创建新的 javaDownload.json 并开始下载。
    QDownloader 由本流程创建并管理，流程结束（无论成败）都会删除 QDownloader。
    """
    status_changed = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    extract_progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()                 # 下载被用户取消/退出（UI 据此显示"已取消"而非"失败"）
    paused_changed = pyqtSignal(bool, int)   # (是否暂停, 当前百分比)，UI 据此显示"Java暂停下载 n%"

    def __init__(self, parent=None, resume=False, urls=None, version=None, build=None, major=None):
        super().__init__()
        self.resume = resume
        self.major = major or DEFAULT_MAJOR
        self.version = version or DEFAULT_VERSION
        self.build = build or DEFAULT_BUILD
        self.urls = urls or _build_urls(self.major, self.version, self.build)
        self.dest = os.path.join(JAVA_TMP_DIR, "jdk%d_%s.zip" % (self.major, self.version))
        self.target_dir = os.path.join(JAVA_ROOT, self.version)
        self._downloader = None
        self._extract_thread = None
        self._extract_worker = None
        self._is_cancelled = False
        self._is_paused = False    # 下载是否被用户暂停（暂停中不转发进度，避免覆盖暂停提示）
        self._info = {}
        self._last_status = None   # 已发射的状态（没变不重发）
        self._last_pct = -1        # 已发射的进度百分比（取整后没变不重发）

    # ---------- 公开接口 ----------
    def start(self):
        """开始 Java 下载/解压流程（非阻塞，结果通过信号返回）。"""
        _log.info(_tr("log.java.flow_start", self.resume, self.dest))
        if self.resume:
            info = load_info() or {}
            status = info.get("status")
            if status in ("downloading", "extracting"):
                self._info = info
                self._apply_info(info)
                if status == "downloading":
                    self._start_download()
                else:
                    self._start_extract()
                return
        # 全新流程：创建 javaDownload.json
        self._info = {
            "status": "downloading",
            "urls": self.urls,
            "url": None,
            "dest": self.dest,
            "target_dir": self.target_dir,
            "version": self.version,
            "major": self.major,
            "build": self.build,
            "updated_at": int(time.time()),
        }
        save_info(self._info)
        self._start_download()

    def cancel(self):
        """取消流程：停止 QDownloader 与解压线程（保留 javaDownload.json 供续传）。"""
        _log.info(_tr("log.java.cancel"))
        self._is_cancelled = True
        self.shutdown()

    def shutdown(self):
        """停止并等待所有内部子线程退出（下载线程 + 解压线程）。

        幂等：可在流程结束、取消、销毁前多次调用。
        调用后所有 QThread 均已退出，可安全释放引用而不触发
        "QThread: Destroyed while thread is still running"。
        """
        _log.info(_tr("log.java.shutdown"))
        # 1. 下载线程
        dl = self._downloader
        self._downloader = None
        if dl is not None:
            try:
                dl.cancel(timeout=3)
                dl.wait_thread(5000)
                dl.deleteLater()
            except Exception:
                pass
        # 2. 解压线程
        thread = self._extract_thread
        self._extract_thread = None
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                thread.wait(5000)
            except Exception:
                pass
        self._extract_worker = None

    # ---------- 内部流程 ----------
    def _emit_status(self, status):
        """状态没变就不重发（downloading/extracting/done/error）。"""
        if status != self._last_status:
            self._last_status = status
            self._last_pct = -1   # 换阶段后第一个进度帧必发
            _log.info(_tr("log.java.status", status))
            self.status_changed.emit(status)

    def _emit_progress(self, done, total):
        """下载进度：百分比取整后没变化就不发（1% 才发一次）。

        暂停中只更新内部百分比（供恢复时显示），不发射 progress——
        否则暂停瞬间的在途数据会让百分比跳动，把"Java暂停下载 n%"
        覆盖回"正在下载Java n%"（进度不再变化时就会卡在错误提示上）。
        """
        pct = int(done * 100 / total) if total else 0
        if pct == self._last_pct:
            return
        self._last_pct = pct
        if self._is_paused:
            _log.info(_tr("log.java.progress_suppressed", pct))
            return
        self.progress.emit(done, total)

    def _emit_extract_progress(self, done, total):
        """解压进度：百分比取整后没变化就不发（1% 才发一次）。"""
        pct = int(done * 100 / total) if total else 0
        if pct == self._last_pct:
            return
        self._last_pct = pct
        self.extract_progress.emit(done, total)

    def _apply_info(self, info):
        self.urls = info.get("urls") or self.urls
        self.dest = info.get("dest") or self.dest
        self.version = info.get("version") or self.version
        self.major = info.get("major") or self.major
        self.build = info.get("build") or self.build
        self.target_dir = os.path.join(JAVA_ROOT, self.version)

    def _start_download(self):
        """创建 QDownloader（子线程运行、注册到全局路由表、多源竞速）并开始下载。"""
        if self._is_cancelled:
            self.finished.emit(False)
            return
        self._is_cancelled = False
        self._emit_status("downloading")
        try:
            os.makedirs(JAVA_TMP_DIR, exist_ok=True)
            dl = QDownloader(urls=self.urls, dest_path=self.dest,
                             num_threads=4, chunk_size_mb=4,
                             title="Java %s" % (self.version or ""))
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)
            return
        self._downloader = dl
        dl.source_selected.connect(self._on_source_selected)
        dl.progress.connect(self._emit_progress)
        dl.finished.connect(self._on_download_finished)
        dl.cancelled.connect(self._on_download_cancelled)
        dl.paused_changed.connect(self._on_download_paused_changed)
        dl.error.connect(self.error)
        dl.start()

    def _on_source_selected(self, url):
        _log.info(_tr("log.java.source_selected", url))
        self._info["url"] = url
        self._info["updated_at"] = int(time.time())
        save_info(self._info)

    def _on_download_paused_changed(self, paused):
        """下载暂停/恢复：记录暂停状态并转发给 UI（带当前百分比）。"""
        self._is_paused = bool(paused)
        pct = self._last_pct if self._last_pct >= 0 else 0
        _log.info(_tr("log.java.dl_paused" if paused else "log.java.dl_resumed", pct))
        self.paused_changed.emit(paused, pct)

    def _on_download_cancelled(self):
        """下载被取消（用户取消/退出时）：善后释放 QDownloader 并结束流程。

        保留 javaDownload.json（status 保持 downloading），下次启动续传；
        发 cancelled 信号让 UI 显示"已取消"，不误报"下载失败"。
        """
        self._is_cancelled = True
        _log.info(_tr("log.java.dl_cancelled"))
        dl = self._downloader
        self._downloader = None
        if dl is not None:
            try:
                dl.wait_thread(5000)
                dl.deleteLater()
            except Exception:
                pass
        self.cancelled.emit()
        self.finished.emit(False)

    def _on_download_finished(self, ok):
        _log.info(_tr("log.java.dl_finished", ok, self._is_cancelled))
        # 无论成功失败都释放并删除 QDownloader。
        # 必须先 wait_thread 确保下载线程完全退出，否则销毁仍运行的 QThread
        # 会触发 Qt 致命错误（QThread: Destroyed while thread is still running）。
        dl = self._downloader
        self._downloader = None
        if dl is not None:
            try:
                dl.wait_thread(5000)
                dl.deleteLater()
            except Exception:
                pass
        if not ok or self._is_cancelled:
            if not self._is_cancelled:
                self._info["status"] = "error"
                save_info(self._info)
            self.finished.emit(False)
            return
        self._start_extract()

    def _start_extract(self):
        """进入解压阶段：QThread 中执行，进度通过 extract_progress 汇报。"""
        if self._is_cancelled:
            self.finished.emit(False)
            return
        self._is_cancelled = False
        _log.info(_tr("log.java.extract_start", self.dest))
        if not os.path.isfile(self.dest):
            self.error.emit(_tr("log.java.extract_missing", self.dest))
            self._info["status"] = "error"
            save_info(self._info)
            self._emit_status("error")
            self.finished.emit(False)
            return
        self._info["status"] = "extracting"
        self._info["updated_at"] = int(time.time())
        save_info(self._info)
        self._emit_status("extracting")

        worker = _ExtractWorker(self.dest, self.target_dir, self.version)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._emit_extract_progress)
        worker.finished.connect(self._on_extract_finished)
        # 关键：DirectConnection 让 thread.quit 在 worker 线程直接调用（QThread.quit 线程安全），
        # 若用默认 AutoConnection，quit 会排队到主线程事件循环，而 _on_extract_finished
        # 先入队并阻塞主线程执行 thread.wait()，quit 永远处理不到 → 线程无法退出 →
        # 之后销毁仍在运行的 QThread 崩溃。
        worker.finished.connect(thread.quit, Qt.DirectConnection)
        # 不用 worker.deleteLater/thread.deleteLater 自动连接：
        # worker 的 deleteLater 排队到即将退出的事件循环会被丢弃；
        # thread 的 deleteLater 与 Python 引用释放存在跨线程竞态。
        # 线程退出与对象销毁统一由 shutdown()/_on_extract_finished 显式管理。
        self._extract_worker = worker
        self._extract_thread = thread
        thread.start()

    def _on_extract_finished(self, ok):
        # 线程已通过 DirectConnection 的 quit 开始退出，这里等待其完全终止后再释放引用
        thread = self._extract_thread
        worker = self._extract_worker
        self._extract_worker = None
        self._extract_thread = None
        if thread is not None:
            try:
                thread.wait(5000)
            except Exception:
                pass
        _log.info(_tr("log.java.extract_finished", ok, self._is_cancelled))
        if not ok or self._is_cancelled:
            if not self._is_cancelled:
                self._info["status"] = "error"
                save_info(self._info)
                self._emit_status("error")
            self.finished.emit(False)
            return
        self._info["status"] = "done"
        self._info["updated_at"] = int(time.time())
        save_info(self._info)
        self._emit_status("done")
        self.finished.emit(True)
