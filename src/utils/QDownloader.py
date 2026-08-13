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
QDownloader 模块文档说明
========================

本模块提供了一个支持多线程、断点续传和代理配置的文件下载器类。
它基于 PyQt5 的信号槽机制设计，适合在 GUI 应用程序中异步执行下载任务。

主要特性:
1. **多线程下载**: 支持将文件分块，使用线程池并行下载，提高大文件下载速度。
2. **断点续传**: 自动保存下载状态到本地 JSON 文件，意外中断后可从上次进度恢复。
3. **代理支持**: 未手动指定代理时，自动检测系统代理（加速器/VPN），也兼容环境变量代理（HTTP_PROXY / HTTPS_PROXY）。
4. **原子性写入**: 下载完成后先合并到临时文件，再原子性移动到目标路径，避免产生损坏的目标文件。
5. **暂停/恢复/取消**: 提供完整的生命周期控制接口（暂停后可随时恢复，取消则清理并放弃）。

使用示例:
    downloader = QDownloader(
        url="https://example.com/largefile.zip",
        dest_path="./downloads/largefile.zip",
        num_threads=4,
        chunk_size_mb=2
    )
    
    # 连接信号
    downloader.progress.connect(lambda current, total: print(f"Progress: {current}/{total}"))
    downloader.finished.connect(lambda success: print("Download finished" if success else "Download failed"))
    downloader.error.connect(lambda err: print(f"Error: {err}"))
    
    # 开始下载
    downloader.start()

注意事项:
- 请确保目标路径所在的目录具有写入权限。
- 未手动指定代理时，会自动检测系统代理（环境变量或 Windows 系统代理设置），加速器开启后即可自动生效。
- 如果服务器不支持 'Accept-Ranges: bytes'，下载将失败。

最后，感谢d老师！
"""


import os
import sys
import json
import time
import hashlib
import shutil
import threading
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed, wait

import requests
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal

from .path_utils import getPath


# 默认 User-Agent：使用下载工具 UA（curl/wget/aria2 风格）。
# 清华等国内镜像站对 python-requests / 浏览器 UA 返回 403（反爬白名单只放行下载工具），
# 统一伪装为 curl 可被正常放行；对 GitHub 等其他源无副作用。
_DEFAULT_USER_AGENT = "curl/8.5.0"


# ==================== SSL 证书验证容错 ====================
# Watt Toolkit（Steam++）等加速器会注入自签根证书，Python 的 certifi 不信任，
# 导致 SSLError: CERTIFICATE_VERIFY_FAILED。默认走证书验证（安全），
# 遇 SSLError 自动降级为 verify=False 重试一次并抑制 InsecureRequestWarning。
def _ssl_retry_request(sess, method, url, **kwargs):
    """带 SSL 降级重试的请求。正常环境走证书验证，证书异常时降级 verify=False。"""
    try:
        return getattr(sess, method)(url, **kwargs)
    except requests.exceptions.SSLError:
        try:
            import warnings
            try:
                from requests.packages.urllib3.exceptions import InsecureRequestWarning
            except Exception:
                from urllib3.exceptions import InsecureRequestWarning
            warnings.simplefilter("ignore", InsecureRequestWarning)
        except Exception:
            pass
        kwargs["verify"] = False
        return getattr(sess, method)(url, **kwargs)


# ==================== 1. 系统代理检测（支持加速器/VPN） ====================
def _detect_system_proxy():
    """
    自动检测系统代理，用于支持加速器（Clash、v2rayN 等）。
    优先级: 环境变量 (HTTPS_PROXY/HTTP_PROXY) > Windows 系统代理设置（注册表）。
    返回代理字符串（如 http://127.0.0.1:7890），未检测到时返回 None。
    """
    # 1. 环境变量（requests 的 trust_env 也会读取，这里优先显式获取）
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var)
        if val:
            return val

    # 2. Windows 系统代理（加速器开启后通常会自动写入注册表）
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            )
            try:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            except OSError:
                return None
            if not proxy_enable:
                return None
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if not proxy_server:
                return None
            # 可能包含多协议配置，如 "http=127.0.0.1:7890;https=127.0.0.1:7890"
            if "=" in proxy_server:
                for part in proxy_server.split(";"):
                    if part.lower().startswith("https="):
                        return part.split("=", 1)[1]
                return proxy_server.split(";")[0].split("=", 1)[-1]
            return proxy_server
        except Exception:
            return None

    return None


# ==================== 2. 全局任务注册表（防重复） ====================
_TASK_REGISTRY = {}
_REGISTRY_LOCK = Lock()

TMP_PATH = getPath(os.path.join("BML", ".tmp", "QDownloader"))

# 全局退出标志：应用退出时置位，工作线程据此快速结束网络请求
_ABORT_EVENT = threading.Event()


def _interruptible_sleep(seconds):
    """可被全局退出打断的休眠（替代 time.sleep，避免退出时被重试等待卡住）。"""
    end = time.time() + seconds
    while time.time() < end:
        if _ABORT_EVENT.is_set():
            return
        time.sleep(0.1)


def shutdown_all(timeout=5):
    """停止所有活动下载任务（应用退出时调用）。

    置位全局退出标志 → 逐个取消任务（有界等待）→ 等待注册表清空。
    若有线程仍在网络请求中未能及时退出，由进程退出兜底处理。
    """
    _ABORT_EVENT.set()
    with _REGISTRY_LOCK:
        tasks = list(_TASK_REGISTRY.values())
    deadline = time.time() + timeout
    for task in tasks:
        try:
            task.cancel(timeout=3)
        except Exception:
            pass
    while time.time() < deadline:
        with _REGISTRY_LOCK:
            alive = bool(_TASK_REGISTRY)
        if not alive:
            break
        time.sleep(0.05)

def get_active_task(task_id):
    with _REGISTRY_LOCK:
        return _TASK_REGISTRY.get(task_id)

def get_active_tasks():
    """返回所有活动任务的快照。

    返回: {task_id: QDownloader实例}
    （运行中 + 暂停中，均已注册到路由表）
    """
    with _REGISTRY_LOCK:
        return dict(_TASK_REGISTRY)

def register_task(task_id, instance):
    with _REGISTRY_LOCK:
        if task_id in _TASK_REGISTRY:
            raise RuntimeError(f"任务 {task_id} 已在运行中，不能重复创建")
        _TASK_REGISTRY[task_id] = instance

def unregister_task(task_id):
    with _REGISTRY_LOCK:
        _TASK_REGISTRY.pop(task_id, None)


# ==================== 3. 下载器主类 ====================
class QDownloader(QObject):
    """
    多线程断点续传下载器（全程运行在子线程 QThread 中，外部只能通过信号槽交互）

    信号：
        started()                    - 下载开始
        finished(bool)               - 下载完成（True 成功 / False 失败）
        cancelled()                  - 下载被取消（与失败区分，不再发射 finished）
        progress(done, total)        - 总体进度（已下载字节量, 总字节）
        thread_progress(id, idx, %)  - 单块进度
        source_selected(str)         - 多源竞速后选定的下载源 URL
        error(str)                   - 错误信息

    多源竞速：
        传入 urls 列表时，启动前对每个源进行 5 秒或 1MB 的限时测速
        （先到先停），选择速度最高的源作为实际下载地址，
        通过 source_selected 信号通知。

    任务信息：
        运行时在 tmp 目录目标任务文件夹（BML/.tmp/QDownloader/<task_id>/）
        下写入 download.json：块数量、每块状态
        （p: 100 完成 / 1~99 未完成百分比 / 0 未开始）与已下载字节（b），
        以及总进度 done_bytes，供界面展示与下次续传使用。

    进度汇总：
        下载线程每 1 秒遍历各分线程实时更新的已下载字节量，
        汇总为总进度发射 progress 信号；get_progress() 返回字节进度。
    """
    started = pyqtSignal()
    finished = pyqtSignal(bool)
    cancelled = pyqtSignal()
    progress = pyqtSignal(int, int)
    thread_progress = pyqtSignal(int, int, int)
    source_selected = pyqtSignal(str)
    error = pyqtSignal(str)

    # ---------- 初始化 ----------
    def __init__(self, url=None, urls=None, dest_path=None, num_threads=4, chunk_size_mb=2, headers=None, proxy=None):
        super().__init__()
        # 支持单源（url）与多源（urls 列表，启动时竞速选优）
        if urls:
            self.urls = [u for u in urls if u]
        elif isinstance(url, (list, tuple)):
            self.urls = [u for u in url if u]
        else:
            self.urls = [url] if url else []
        self.url = self.urls[0] if len(self.urls) == 1 else None   # 多源时竞速后确定
        self.dest_path = os.path.abspath(dest_path) if dest_path else None
        self.num_threads = max(1, min(num_threads, 8))
        self.chunk_size = chunk_size_mb * 1024 * 1024
        self.headers = headers or {}
        # 未显式指定代理时，自动检测系统代理（加速器/VPN）
        self.proxy = proxy if proxy else _detect_system_proxy()

        # 内部状态
        self.total_size = 0
        self.block_count = 0
        self.block_size = 0
        self.completed_blocks = set()
        self._block_bytes = []             # 每块已下载字节量（分线程写入，主下载线程汇总）
        self._block_bytes_lock = Lock()
        self._lock = Lock()
        self._save_counter = 0
        self._json_save_counter = 0
        self._is_paused = False
        self._is_cancelled = False
        self._is_running = False
        self._pause_event = threading.Event()
        self._pause_event.set()   # 默认未暂停

        # 停滞监控（供诊断/看门狗）
        self._watch_tick = 0               # 主下载线程轮询次数
        self._stall_checks = 0             # 停滞检测计数
        self._last_activity = time.monotonic()
        self._active_responses = {}        # {block_idx: response} 进行中的网络响应

        # 任务ID（由目标路径哈希生成）
        self.task_id = None
        self.temp_root = None
        self.temp_dir = None
        self.state_file = None
        self.merged_temp = None

        if self.dest_path:
            self._init_task_id()

        # 内部线程：run/下载逻辑只在子线程执行，外部只能通过信号槽交互
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        # finished / cancelled 均需退出线程并注销任务。
        # quit 用 DirectConnection：信号在下载线程发射，若默认 AutoConnection 会
        # 排队到主线程事件循环，而持有方可能在主线程阻塞等待本线程退出（wait），
        # 导致 quit 永远处理不到、线程无法退出，随后销毁运行中的 QThread 崩溃。
        # QThread::quit 线程安全，可在任意线程直接调用。
        # 删除对象统一由持有方（JavaDownloadFlow）在 wait_thread 确保线程退出后执行。
        self.finished.connect(self._thread.quit, Qt.DirectConnection)
        self.finished.connect(lambda: unregister_task(self.task_id) if self.task_id else None)
        self.cancelled.connect(self._thread.quit, Qt.DirectConnection)
        self.cancelled.connect(lambda: unregister_task(self.task_id) if self.task_id else None)

    def _init_task_id(self):
        """根据目标路径生成任务ID，并创建对应的临时目录结构"""
        if not self.dest_path:
            return
        self.task_id = hashlib.md5(self.dest_path.encode()).hexdigest()
        self.temp_root = os.path.join(TMP_PATH, self.task_id)
        self.temp_dir = self.temp_root
        self.state_file = os.path.join(self.temp_root, "state.json")
        self.merged_temp = os.path.join(self.temp_root, os.path.basename(self.dest_path))
        # 自动注册到路由表
        register_task(self.task_id, self)

    # ---------- 公共接口 ----------
    def set(self, **kwargs):
        """手动配置下载参数（链式调用），运行中拒绝修改"""
        if self._is_running:
            raise RuntimeError("任务正在运行，无法修改配置")
        if 'url' in kwargs:
            self.url = kwargs['url']
        if 'dest_path' in kwargs:
            # 注销旧任务，重新初始化
            if self.task_id:
                unregister_task(self.task_id)
            self.dest_path = os.path.abspath(kwargs['dest_path'])
            self._init_task_id()   # 重新生成ID并注册
        if 'num_threads' in kwargs:
            self.num_threads = max(1, min(kwargs['num_threads'], 8))
        if 'headers' in kwargs:
            self.headers = kwargs['headers']
        if 'proxy' in kwargs:
            self.proxy = kwargs['proxy'] if kwargs['proxy'] else _detect_system_proxy()
        return self

    def start(self):
        """启动下载（非阻塞）"""
        if self._is_running:
            return
        if not self.dest_path:
            self.error.emit("未设置目标路径")
            return
        # 多源模式允许 url 暂为 None：启动后在子线程中竞速确定
        if not self.url and not self.urls:
            self.error.emit("未设置下载链接")
            return
        if not self._thread.isRunning():
            self._thread.start()

    def pause(self):
        """暂停下载（线程在安全点等待，可 resume 恢复）"""
        self._is_paused = True
        self._pause_event.clear()

    def resume(self):
        """恢复暂停的下载"""
        self._is_paused = False
        self._pause_event.set()

    def cancel(self, timeout=None):
        """取消下载并清理临时文件（不可恢复）。

        timeout: 等待工作线程退出的秒数；None 表示无限等待（默认）。
        线程未能及时退出时保留临时文件（下次可断点续传），不强行删除。
        """
        self._is_cancelled = True
        self._pause_event.set()   # 唤醒暂停等待中的线程，使其退出
        stopped = True
        if self._thread.isRunning():
            stopped = self._thread.wait(timeout)
        if stopped:
            self._cleanup(keep_state=False)
        # 线程从未启动（未 start 即 cancel）：finished/cancelled 信号不会发射，
        # 需要手动注销，避免僵尸任务残留在注册表中
        unregister_task(self.task_id)

    def wait_thread(self, timeout=None):
        """等待内部下载线程完全退出（返回是否已退出）。

        在释放/删除本对象前调用，确保 QThread 不再运行，
        避免销毁运行中的线程导致 Qt 致命崩溃。
        """
        t = self._thread
        if t is not None and t.isRunning():
            return t.wait(timeout)
        return True

    def __del__(self):
        """兜底：对象被 GC 时若线程仍在运行，先等待其退出再销毁。"""
        try:
            t = getattr(self, "_thread", None)
            if t is not None and t.isRunning():
                t.wait(3000)
        except Exception:
            pass

    def get_progress(self):
        """获取总进度（已下载字节量, 总字节）。"""
        with self._block_bytes_lock:
            done = sum(self._block_bytes) if self._block_bytes else len(self.completed_blocks) * self.block_size
        return min(done, self.total_size), self.total_size

    # ---------- 字节进度与任务信息 ----------
    def _init_block_bytes(self):
        """初始化每块已下载字节：从临时块文件实际大小 + 已完成块推断。"""
        with self._block_bytes_lock:
            self._block_bytes = [0] * self.block_count
        for i in range(self.block_count):
            tmp = os.path.join(self.temp_dir, f"block_{i}.tmp")
            if os.path.isfile(tmp):
                try:
                    size = os.path.getsize(tmp)
                except OSError:
                    size = 0
                with self._block_bytes_lock:
                    self._block_bytes[i] = size
        with self._lock:
            completed = list(self.completed_blocks)
        for i in completed:
            if 0 <= i < self.block_count:
                with self._block_bytes_lock:
                    self._block_bytes[i] = self._block_size_of(i)

    def _emit_progress(self):
        """汇总各分线程的已下载字节量并发射总进度信号。"""
        with self._block_bytes_lock:
            done = sum(self._block_bytes)
        self.progress.emit(min(done, self.total_size), self.total_size)

    def _save_download_json(self):
        """把任务信息写入 tmp 目标任务文件夹下的 download.json。

        块状态 p：100 完成 / 1~99 未完成（百分比）/ 0 未开始；b 为该块已下载字节。
        """
        try:
            with self._block_bytes_lock:
                block_bytes = list(self._block_bytes)
            with self._lock:
                completed = set(self.completed_blocks)
            blocks = []
            done_total = 0
            for i in range(self.block_count):
                b = block_bytes[i] if i < len(block_bytes) else 0
                done_total += b
                if i in completed:
                    p = 100
                elif b > 0:
                    total_b = self._block_size_of(i)
                    p = max(1, min(99, int(b * 100 / total_b))) if total_b else 0
                else:
                    p = 0
                blocks.append({"p": p, "b": b})
            data = {
                "url": self.url,
                "urls": self.urls,
                "dest_path": self.dest_path,
                "total_size": self.total_size,
                "block_count": self.block_count,
                "block_size": self.block_size,
                "blocks": blocks,
                "done_bytes": min(done_total, self.total_size),
                "updated_at": int(time.time())
            }
            os.makedirs(self.temp_root, exist_ok=True)
            with open(os.path.join(self.temp_root, "download.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _save_download_json_if_needed(self):
        """节流写 download.json（约每 5 秒一次）。"""
        self._json_save_counter += 1
        if self._json_save_counter >= 5:
            self._json_save_counter = 0
            self._save_download_json()

    def _race_sources(self, sess):
        """多源竞速：对每个 URL 限时 5 秒或 1MB 测速，返回速度最高的 URL。

        每个源先到先停：下载满 1MB 或耗时达到 5 秒即停止测速，
        以平均速度比较，选择最快的源作为正式下载地址。
        """
        probe_size = 1024 * 1024
        timeout = 5.0
        best_url = self.urls[0] if self.urls else None
        best_speed = -1.0
        for url in self.urls:
            if self._is_cancelled or _ABORT_EVENT.is_set():
                break
            t0 = time.monotonic()
            got = 0
            try:
                resp = _ssl_retry_request(sess, "get", url,
                                          headers={"Range": "bytes=0-%d" % (probe_size - 1)},
                                          stream=True, timeout=10)
                resp.raise_for_status()
                try:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self._is_cancelled or _ABORT_EVENT.is_set():
                            break
                        got += len(chunk)
                        if got >= probe_size or time.monotonic() - t0 >= timeout:
                            break
                finally:
                    resp.close()
                cost = time.monotonic() - t0
                speed = got / cost if cost > 0 else 0.0
                if speed > best_speed:
                    best_speed = speed
                    best_url = url
            except Exception:
                continue
        return best_url

    # ---------- 内部核心 ----------
    def _run(self):
        if self._is_running:
            return
        self._is_running = True
        self.started.emit()

        try:
            # 创建带代理的 Session（trust_env 兜底读取环境变量代理）
            sess = requests.Session()
            sess.trust_env = True
            sess.headers.update({"User-Agent": _DEFAULT_USER_AGENT})
            if self.proxy:
                sess.proxies.update({"http": self.proxy, "https": self.proxy})

            # 多源竞速：对每个 URL 限时 5s 或 1MB 测速，选择速度最高的源
            if not self.url and len(self.urls) > 1:
                picked = self._race_sources(sess)
                if picked:
                    self.url = picked
                    self.source_selected.emit(picked)
            elif not self.url and self.urls:
                self.url = self.urls[0]
            if not self.url:
                self.error.emit("未设置下载链接")
                self.finished.emit(False)
                return

            # 准备下载（获取文件大小，检查断点支持）
            if not self._prepare():
                self.finished.emit(False)
                return
            if self._is_cancelled:
                self.cancelled.emit()
                return

            # 创建临时目录，加载断点状态，初始化每块字节进度
            self._prepare_temp_files()
            self._load_state()
            self._init_block_bytes()

            # 写入任务信息 download.json（块数量/每块状态/已下载字节）
            self._save_download_json()

            # 构建待下载块列表
            pending = [i for i in range(self.block_count) if i not in self.completed_blocks]
            if not pending:
                self._merge_files()
                self._cleanup(keep_state=False)
                self.finished.emit(True)
                return

            # 多线程执行（不用 with：__exit__ 会 shutdown(wait=True)，取消时会被网络超时阻塞）
            executor = ThreadPoolExecutor(max_workers=self.num_threads)
            try:
                futures = {executor.submit(self._download_block, sess, idx): idx for idx in pending}
                pending_futures = set(futures.keys())

                # 主下载线程每 1 秒轮询：遍历各分线程的字节进度并汇总为总进度，
                # 同时节流写 download.json，供界面展示与下次续传
                while pending_futures:
                    if self._is_cancelled:
                        self.cancelled.emit()
                        return
                    done_set, pending_futures = wait(pending_futures, timeout=1.0)
                    self._watch_tick += 1
                    self._emit_progress()
                    self._save_download_json_if_needed()
                    # 简单停滞监控：长时间无字节写入且任务未完成则计数（供诊断/看门狗）
                    if self._last_activity is not None and time.monotonic() - self._last_activity > 20:
                        self._stall_checks += 1

                    for fut in done_set:
                        idx = futures[fut]
                        try:
                            ok = fut.result()
                            if ok:
                                with self._lock:
                                    self.completed_blocks.add(idx)
                                    with self._block_bytes_lock:
                                        self._block_bytes[idx] = self._block_size_of(idx)
                                    self._save_state_if_needed()
                            else:
                                if self._is_cancelled:
                                    self.cancelled.emit()
                                else:
                                    self.error.emit(f"块 {idx} 下载失败（重试耗尽）")
                                    self.finished.emit(False)
                                return
                        except Exception as e:
                            self.error.emit(str(e))
                            self.finished.emit(False)
                            return
            finally:
                # wait=False：不阻塞等待正在进行的网络请求，工作线程自然结束
                executor.shutdown(wait=False, cancel_futures=True)

            # 完成所有块（暂停只作用于块下载阶段，合并阶段不再阻塞，避免静默结束）
            if not self._is_cancelled:
                self._merge_files()
                self._cleanup(keep_state=False)
                self.finished.emit(True)

        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)
        finally:
            self._is_running = False
            unregister_task(self.task_id)

    def _prepare(self):
        """
        获取文件大小并探测断点续传支持。
        HEAD 失败时用 GET + Range 探测兜底；部分服务器不返回 accept-ranges
        头但仍支持 Range，此时以 Range 探测（206）为准，避免误判失败。
        """
        resp = None
        try:
            sess = requests.Session()
            sess.trust_env = True  # 兜底读取环境变量代理（加速器）
            sess.headers.update({"User-Agent": _DEFAULT_USER_AGENT})
            if self.proxy:
                sess.proxies.update({"http": self.proxy, "https": self.proxy})

            # 优先 HEAD；部分服务器（如某些 CDN）禁用 HEAD，退化为 GET + Range 探测
            supports_range = False
            try:
                resp = _ssl_retry_request(sess, "head", self.url, allow_redirects=True, timeout=30)
                resp.raise_for_status()
            except requests.exceptions.RequestException:
                resp = _ssl_retry_request(sess, "get", self.url,
                                          headers={"Range": "bytes=0-0"},
                                          stream=True, timeout=30)
                resp.raise_for_status()
                # GET + Range 探测返回 206 说明服务器支持断点续传
                supports_range = resp.status_code == 206

            # 解析文件大小（GET 探测返回 206 时从 Content-Range 头取总大小）
            if resp.status_code == 206:
                content_range = resp.headers.get('content-range', '')
                total_str = content_range.rsplit('/', 1)[-1] if content_range else '0'
                self.total_size = int(total_str) if total_str.isdigit() else 0
                supports_range = True
            else:
                self.total_size = int(resp.headers.get('content-length', 0))
                # HEAD 成功且显式声明支持 Range
                if resp.headers.get('accept-ranges') == 'bytes':
                    supports_range = True

            if self.total_size <= 0:
                self.error.emit("无法获取文件大小")
                return False

            # HEAD 成功但未确认支持 Range 时，用 GET + Range 探测二次确认
            if not supports_range:
                try:
                    probe = _ssl_retry_request(sess, "get", self.url,
                                               headers={"Range": "bytes=0-0"},
                                               stream=True, timeout=30)
                    supports_range = probe.status_code == 206
                    probe.close()
                except requests.exceptions.RequestException:
                    supports_range = False

            if not supports_range:
                self.error.emit("服务器不支持断点续传")
                return False

            self.block_size = self.chunk_size
            self.block_count = (self.total_size + self.block_size - 1) // self.block_size
            return True

        except Exception as e:
            self.error.emit(f"准备失败: {e}")
            return False
        finally:
            if resp is not None:
                resp.close()

    def _prepare_temp_files(self):
        os.makedirs(self.temp_root, exist_ok=True)

    def _block_size_of(self, idx):
        """计算第 idx 块的预期字节数"""
        start = idx * self.block_size
        end = min(start + self.block_size - 1, self.total_size - 1)
        return end - start + 1

    def _load_state(self):
        """
        从状态文件恢复已下载块（校验块文件完整性）。
        状态记录为完成但临时文件缺失/不完整的块会被移除，重新下载；
        完整的块保留临时文件，供后续合并使用（合并时统一消费并删除）。
        """
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            if data.get('total_size') == self.total_size:
                self.completed_blocks = set(data.get('completed_blocks', []))
                # 仅保留临时文件完整可用的块，其余重新下载
                valid = set()
                for idx in self.completed_blocks:
                    tmp = os.path.join(self.temp_dir, f"block_{idx}.tmp")
                    if os.path.isfile(tmp) and os.path.getsize(tmp) >= self._block_size_of(idx):
                        valid.add(idx)
                self.completed_blocks = valid
        except Exception:
            pass

    def _save_state(self):
        """保存当前进度到状态文件"""
        data = {
            'total_size': self.total_size,
            'block_count': self.block_count,
            'block_size': self.block_size,
            'completed_blocks': list(self.completed_blocks),
            'url': self.url,
            'dest_path': self.dest_path
        }
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    def _save_state_if_needed(self):
        # 状态文件节流保存（每 10 块一次，避免频繁磁盘写入）
        self._save_counter += 1
        if self._save_counter >= 10:
            self._save_counter = 0
            self._save_state()
        # 总体进度：每完成一个块就发射一次，保证 UI 平滑
        done = len(self.completed_blocks) * self.block_size
        self.progress.emit(min(done, self.total_size), self.total_size)

    def _download_block(self, session, block_idx, max_retries=5):
        """下载单个块，带指数退避重试"""
        if self._is_cancelled or _ABORT_EVENT.is_set():
            return False

        start = block_idx * self.block_size
        end = min(start + self.block_size - 1, self.total_size - 1)
        tmp_path = os.path.join(self.temp_dir, f"block_{block_idx}.tmp")

        # 检查已下载部分
        if os.path.exists(tmp_path):
            cur = os.path.getsize(tmp_path)
            expected = end - start + 1
            if cur >= expected:
                return True
            resume_from = start + cur
            mode = 'ab'
        else:
            cur = 0
            resume_from = start
            mode = 'wb'

        for attempt in range(max_retries):
            if self._is_cancelled or _ABORT_EVENT.is_set():
                return False
            # 暂停时阻塞等待（resume 或 cancel 时唤醒），不返回失败
            self._pause_event.wait()

            try:
                local_headers = self.headers.copy()
                local_headers['Range'] = f'bytes={resume_from}-{end}'
                resp = _ssl_retry_request(session, "get", self.url,
                                          headers=local_headers, stream=True, timeout=60)
                resp.raise_for_status()

                total_block = end - start + 1
                with self._lock:
                    self._active_responses[block_idx] = resp
                try:
                    with open(tmp_path, mode) as f:
                        downloaded = cur
                        for chunk in resp.iter_content(chunk_size=8192):
                            # 暂停时阻塞等待（线程不退出，resume 后继续）
                            self._pause_event.wait()
                            if self._is_cancelled or _ABORT_EVENT.is_set():
                                return False
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                # 实时记录本块已下载字节（供主下载线程汇总总进度）
                                with self._block_bytes_lock:
                                    self._block_bytes[block_idx] = downloaded
                                self._last_activity = time.monotonic()
                                if downloaded % (512 * 1024) == 0 or downloaded >= total_block:
                                    percent = int((downloaded / total_block) * 100)
                                    self.thread_progress.emit(
                                        block_idx % self.num_threads,
                                        block_idx,
                                        min(percent, 100)
                                    )
                finally:
                    with self._lock:
                        self._active_responses.pop(block_idx, None)
                return True

            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                # 网络抖动/断流：指数退避重试，并从断点位置继续
                if attempt < max_retries - 1:
                    _interruptible_sleep(2 ** attempt)
                    if os.path.exists(tmp_path):
                        cur = os.path.getsize(tmp_path)
                        resume_from = start + cur
                    continue
                else:
                    raise  # 最后一次失败，抛出异常

            except requests.exceptions.HTTPError as e:
                # 服务器 5xx / 429 限流可重试，其余（4xx）直接失败
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    _interruptible_sleep(2 ** attempt)
                    continue
                raise

        return False

    def _merge_files(self):
        """
        合并所有分块到目标文件（先合到临时目录，再原子性移动）。
        合并前校验所有块完整性，缺失/不完整的块直接抛异常，避免产生损坏文件。
        """
        # 合并前校验所有块完整性
        for i in range(self.block_count):
            tmp = os.path.join(self.temp_dir, f"block_{i}.tmp")
            expected = self._block_size_of(i)
            if not os.path.isfile(tmp) or os.path.getsize(tmp) < expected:
                raise RuntimeError(f"块 {i} 不完整或缺失（预期 {expected} 字节），无法合并")

        self._save_state()
        self.progress.emit(self.total_size, self.total_size)

        # 在临时目录合并（分块复制，避免大文件一次性读入内存）
        with open(self.merged_temp, 'wb') as outfile:
            for i in range(self.block_count):
                tmp = os.path.join(self.temp_dir, f"block_{i}.tmp")
                with open(tmp, 'rb') as infile:
                    shutil.copyfileobj(infile, outfile, length=1024 * 1024)
                os.remove(tmp)

        # 确保目标文件夹存在
        os.makedirs(os.path.dirname(self.dest_path), exist_ok=True)
        # 原子性移动（同盘符下极快）
        shutil.move(self.merged_temp, self.dest_path)

        # 删除空临时目录
        try:
            os.rmdir(self.temp_root)
        except OSError:
            pass

    def _cleanup(self, keep_state=False):
        """清理所有临时文件"""
        if os.path.exists(self.temp_root):
            shutil.rmtree(self.temp_root, ignore_errors=True)
        if not keep_state and os.path.exists(self.state_file):
            os.remove(self.state_file)

    # ---------- 类方法：任务扫描与接管 ----------
    @classmethod
    def get_pending_tasks(cls):
        """
        扫描磁盘上的未完成任务（不在路由表中的）。
        返回: {task_id: {url, dest_path, total_size, block_count,
                        completed_blocks, done_bytes, progress_percent, state_file}}
        """
        pending = {}
        temp_root_dir = TMP_PATH
        if not os.path.exists(temp_root_dir):
            return pending

        for task_id in os.listdir(temp_root_dir):
            task_dir = os.path.join(temp_root_dir, task_id)
            state_file = os.path.join(task_dir, "state.json")
            if not os.path.isfile(state_file):
                continue

            # 跳过已在路由表中的任务（正在运行）
            if get_active_task(task_id):
                continue

            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                total = state.get('total_size', 0)
                blocks = state.get('completed_blocks', [])
                block_size = state.get('block_size', 1)
                # 优先取 download.json 的实时字节进度，否则按完成块数估算
                done = 0
                try:
                    with open(os.path.join(task_dir, "download.json"), 'r', encoding='utf-8') as df:
                        djson = json.load(df)
                    done = djson.get('done_bytes', 0)
                    urls = djson.get('urls') or None
                except Exception:
                    urls = None
                    done = len(blocks) * block_size
                percent = (done / total * 100) if total > 0 else 0.0

                pending[task_id] = {
                    "url": state.get('url', ''),
                    "urls": urls or [state.get('url', '')],
                    "dest_path": state.get('dest_path', ''),
                    "total_size": total,
                    "block_count": state.get('block_count', 0),
                    "completed_blocks": blocks,
                    "done_bytes": min(done, total),
                    "progress_percent": round(percent, 2),
                    "state_file": state_file
                }
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        return pending

    @classmethod
    def continue_task(cls, task_id, headers=None, num_threads=4, proxy=None):
        """
        强制接管一个未完成的任务（忽略当前运行状态检查）。
        如果任务已在路由表中，抛出 RuntimeError。
        如果状态文件不存在，抛出 FileNotFoundError。
        返回一个新的 QDownloader 实例（已自动 start）。
        """
        if get_active_task(task_id):
            raise RuntimeError(f"任务 {task_id} 已在运行中，无法重复接管")

        temp_root = os.path.join(TMP_PATH, task_id)
        state_file = os.path.join(temp_root, "state.json")
        if not os.path.exists(state_file):
            raise FileNotFoundError(f"未找到任务 {task_id} 的状态文件")

        with open(state_file, 'r') as f:
            state = json.load(f)

        # 优先读取 download.json 的多源列表（含竞速结果），否则退回单源 url
        urls = None
        try:
            with open(os.path.join(temp_root, "download.json"), 'r', encoding='utf-8') as df:
                djson = json.load(df)
            urls = djson.get('urls') or None
        except Exception:
            urls = None
        if not urls:
            urls = [state['url']]

        # 创建新实例（多源续传同样在子线程中竞速选优），自动注册
        downloader = cls(
            urls=urls,
            dest_path=state['dest_path'],
            num_threads=num_threads,
            headers=headers or {},
            proxy=proxy
        )
        # 强制覆盖已完成块
        downloader.completed_blocks = set(state.get('completed_blocks', []))
        downloader.total_size = state['total_size']
        downloader.block_count = state['block_count']
        downloader.block_size = state['block_size']
        # 启动
        downloader.start()
        return downloader

    @classmethod
    def clean_orphan_tasks(cls):
        """
        删除所有未在路由表中的临时任务目录（谨慎使用）
        返回被清理的任务数量
        """
        pending = cls.get_pending_tasks()
        count = 0
        for task_id in pending.keys():
            task_dir = os.path.join(TMP_PATH, task_id)
            try:
                shutil.rmtree(task_dir, ignore_errors=True)
                count += 1
            except Exception:
                pass
        return count

    @classmethod
    def get_active_tasks(cls):
        return get_active_tasks()