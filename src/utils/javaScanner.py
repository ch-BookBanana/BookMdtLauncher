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

import os, re, asyncio, string, time, random, threading
from typing import List, Optional, Set



class javaScanner:
    """Windows 全异步 Java 嗅探器（智能优先扫描 + 毫秒级超时终止）"""

    # ---------- 配置参数 ----------
    _COMMON_DIRS = [
        os.path.expandvars(r"%ProgramFiles%\Java"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Java"),
        os.path.expandvars(r"%ProgramW6432%\Java"),
        r"C:\Program Files\Java",
        r"C:\Program Files (x86)\Java",
    ]
    _MAX_DISK_SCAN_DEPTH = 8          # 全盘扫描最大深度
    _VERSION_CONCURRENCY = 32         # 版本检测最大并发
    _DISK_WORKERS = 6                 # 扫描 Worker 协程数
    _DISK_SCAN_TOTAL_TIMEOUT = 30     # 全盘扫描总超时（秒）
    _VERSION_TIMEOUT = 8              # java -version 超时
    _CACHE_TTL = 300                  # 结果缓存秒数

    # 目录黑名单（小写）
    _BLACKLIST_DIRS = {
        'windows', 'system32', 'syswow64', 'winsxs', 'servicing',
        'softwaredistribution', 'temp', 'perflogs', '$recycle.bin',
        'system volume information', 'recovery', 'documents and settings',
        'config.msi', 'msocache', '$windows.~ws', '$windows.~bt',
        'package cache', 'amd64', 'i386', 'x86',
    }

    _cache: Optional[List[List[str]]] = None
    _cache_time: float = 0.0

    # ==================== 版本获取 ====================
    @classmethod
    async def _get_java_version_async(cls, java_path: str) -> Optional[str]:
        if not os.path.isfile(java_path):
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                java_path, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=cls._VERSION_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass
                return None
            output = (stderr or stdout).decode('utf-8', errors='ignore')
            match = re.search(r'"([^"]+)"', output)
            return match.group(1) if match else None
        except Exception:
            return None

    # ==================== 扫描源：PATH ====================
    @classmethod
    async def _scan_env_async(cls) -> Set[str]:
        def _sync():
            paths = set()
            for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
                clean_dir = raw_dir.strip('"').strip()
                if not clean_dir:
                    continue
                candidate = os.path.join(clean_dir, "java.exe")
                if os.path.isfile(candidate):
                    paths.add(candidate)
            return paths
        return await asyncio.to_thread(_sync)

    # ==================== 扫描源：注册表 ====================
    @classmethod
    async def _scan_registry_async(cls) -> Set[str]:
        def _sync():
            import winreg
            paths = set()
            reg_roots = {
                winreg.HKEY_LOCAL_MACHINE: [
                    r"SOFTWARE\JavaSoft\JDK",
                    r"SOFTWARE\JavaSoft\Java Runtime Environment",
                    r"SOFTWARE\JavaSoft\Java Development Kit",
                ],
                winreg.HKEY_CURRENT_USER: [
                    r"SOFTWARE\JavaSoft\JDK",
                    r"SOFTWARE\JavaSoft\Java Runtime Environment",
                ],
            }
            for reg_view in [winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                             winreg.KEY_READ | winreg.KEY_WOW64_32KEY]:
                for root, subkeys in reg_roots.items():
                    for subkey in subkeys:
                        try:
                            with winreg.OpenKey(root, subkey, access=reg_view) as key:
                                i = 0
                                while True:
                                    try:
                                        ver_name = winreg.EnumKey(key, i)
                                        i += 1
                                        with winreg.OpenKey(key, ver_name, access=reg_view) as ver_key:
                                            java_home, _ = winreg.QueryValueEx(ver_key, "JavaHome")
                                            candidate = os.path.join(java_home, "bin", "java.exe")
                                            if os.path.isfile(candidate):
                                                paths.add(candidate)
                                    except OSError:
                                        break
                        except OSError:
                            continue
            return paths
        try:
            return await asyncio.to_thread(_sync)
        except Exception:
            return set()

    # ==================== 扫描源：常见目录 ====================
    @classmethod
    async def _scan_common_dirs_async(cls) -> Set[str]:
        async def scan_one(root_dir: str) -> Set[str]:
            if not os.path.isdir(root_dir):
                return set()
            def _walk_sync():
                found = set()
                try:
                    for current, dirs, files in os.walk(root_dir):
                        depth = current[len(root_dir):].count(os.sep)
                        if depth > 4:
                            dirs.clear()
                            continue
                        if 'java.exe' in files and os.path.basename(current).lower() == 'bin':
                            found.add(os.path.join(current, 'java.exe'))
                except PermissionError:
                    pass
                return found
            return await asyncio.to_thread(_walk_sync)

        tasks = [scan_one(d) for d in cls._COMMON_DIRS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_paths: Set[str] = set()
        for r in results:
            if isinstance(r, set):
                all_paths.update(r)
        return all_paths

    # ==================== 扫描源：用户主目录 ====================
    @classmethod
    async def _scan_user_dir_async(cls) -> Set[str]:
        user_root = os.path.expanduser("~")
        if not os.path.isdir(user_root):
            return set()
        def _walk_sync():
            found = set()
            try:
                for current, dirs, files in os.walk(user_root):
                    depth = current[len(user_root):].count(os.sep)
                    if depth > 4:
                        dirs.clear()
                        continue
                    dirs[:] = [d for d in dirs if d.lower() not in cls._BLACKLIST_DIRS]
                    if 'java.exe' in files and os.path.basename(current).lower() == 'bin':
                        found.add(os.path.join(current, 'java.exe'))
            except PermissionError:
                pass
            return found
        return await asyncio.to_thread(_walk_sync)

    # ==================== 智能优先全盘扫描 ====================
    @classmethod
    async def _scan_all_drives_async(cls) -> Set[str]:
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        if not drives:
            return set()

        # 全局优先级队列 (priority, directory_path)
        queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        for d in drives:
            queue.put_nowait((10, d))   # 盘根优先级 10

        pending_lock = asyncio.Lock()
        pending_count = len(drives)
        found: Set[str] = set()
        visited: Set[str] = set()
        known_jdk_roots: Set[str] = set()   # 已发现 JDK 根目录（小写规范化路径）

        stop_event = threading.Event()
        worker_count = cls._DISK_WORKERS

        async def inc_pending(delta: int):
            nonlocal pending_count
            async with pending_lock:
                pending_count += delta

        def is_under_known_root(path: str) -> bool:
            """检查路径是否位于已知 JDK 根目录内部（含根目录自身）"""
            norm = os.path.normpath(path).lower()
            for root in known_jdk_roots:
                if norm == root or norm.startswith(root + '\\'):
                    return True
            return False

        def sync_scan_dir(task_dir: str):
            """在独立线程中执行 os.scandir，受 stop_event 控制"""
            if stop_event.is_set():
                return [], [], False
            subdirs = []
            java_files = []
            is_bin = os.path.basename(task_dir).lower() == 'bin'
            try:
                with os.scandir(task_dir) as entries:
                    for entry in entries:
                        if stop_event.is_set():
                            break
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if entry.name.lower() not in cls._BLACKLIST_DIRS:
                                    subdirs.append(entry.path)
                            elif entry.is_file() and entry.name.lower() == 'java.exe':
                                if is_bin:   # 只在 bin 目录内记录 java.exe
                                    java_files.append(entry.path)
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                pass
            return subdirs, java_files, is_bin

        async def worker():
            while not stop_event.is_set():
                try:
                    prio, task_dir = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    async with pending_lock:
                        if pending_count == 0:
                            return
                    continue

                await inc_pending(-1)

                # 跳过已知 JDK 内部
                if is_under_known_root(task_dir):
                    continue

                norm = os.path.normpath(task_dir).lower()
                if norm in visited:
                    continue
                visited.add(norm)

                subdirs, java_files, is_bin = await asyncio.to_thread(sync_scan_dir, task_dir)

                if is_bin and java_files:
                    # 发现 JDK 的 bin 目录
                    for jf in java_files:
                        found.add(jf)

                    jdk_root = os.path.dirname(task_dir)   # JDK 根目录
                    jdk_root_norm = os.path.normpath(jdk_root).lower()
                    known_jdk_roots.add(jdk_root_norm)

                    # ---- 附近优先扩散：兄弟目录 (优先级 0) ----
                    parent_of_root = os.path.dirname(jdk_root)
                    if parent_of_root and not stop_event.is_set():
                        try:
                            with os.scandir(parent_of_root) as it:
                                for e in it:
                                    if stop_event.is_set():
                                        break
                                    if e.is_dir(follow_symlinks=False) and e.name.lower() not in cls._BLACKLIST_DIRS:
                                        sibling = e.path
                                        if not is_under_known_root(sibling):
                                            queue.put_nowait((0, sibling))
                                            await inc_pending(1)
                        except (PermissionError, OSError):
                            pass

                    # ---- 附近优先扩散：祖父目录下的其他子目录 (优先级 1) ----
                    grand_parent = os.path.dirname(parent_of_root) if parent_of_root else None
                    if grand_parent and not stop_event.is_set():
                        try:
                            with os.scandir(grand_parent) as it:
                                for e in it:
                                    if stop_event.is_set():
                                        break
                                    if e.is_dir(follow_symlinks=False) and e.name.lower() not in cls._BLACKLIST_DIRS:
                                        uncle = e.path
                                        if uncle != parent_of_root and not is_under_known_root(uncle):
                                            queue.put_nowait((1, uncle))
                                            await inc_pending(1)
                        except (PermissionError, OSError):
                            pass
                    # bin 目录本身已处理完毕，不再深入子目录
                else:
                    # 普通目录：将子目录按深度优先级入队
                    depth = task_dir.rstrip('\\').count('\\')
                    next_prio = depth * 10 + 10
                    for sub in subdirs:
                        if stop_event.is_set():
                            break
                        if not is_under_known_root(sub):
                            queue.put_nowait((next_prio, sub))
                            await inc_pending(1)

        # 启动所有 Worker
        worker_tasks = [asyncio.create_task(worker()) for _ in range(worker_count)]

        try:
            await asyncio.wait_for(
                asyncio.gather(*worker_tasks),
                timeout=cls._DISK_SCAN_TOTAL_TIMEOUT
            )
        except asyncio.TimeoutError:
            pass
        finally:
            stop_event.set()
            for t in worker_tasks:
                t.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        return found

    # ==================== 主异步流程 ====================
    @classmethod
    async def _async_get_javas(cls) -> List[List[str]]:
        start = time.time()

        results = await asyncio.gather(
            cls._scan_env_async(),
            cls._scan_registry_async(),
            cls._scan_common_dirs_async(),
            cls._scan_user_dir_async(),
            cls._scan_all_drives_async(),
            return_exceptions=True
        )

        candidates: Set[str] = set()
        for r in results:
            if isinstance(r, set):
                candidates.update(r)

        scan_time = time.time() - start

        semaphore = asyncio.Semaphore(cls._VERSION_CONCURRENCY)
        async def version_task(p: str) -> Optional[tuple]:
            async with semaphore:
                ver = await cls._get_java_version_async(p)
                return (p, ver) if ver else None

        ver_coros = [version_task(p) for p in candidates]
        ver_results = await asyncio.gather(*ver_coros, return_exceptions=True)

        final = []
        for item in ver_results:
            if isinstance(item, tuple) and item[1]:
                final.append([item[0], item[1]])
        final.sort(key=lambda x: x[0].lower())

        return final

    # ==================== 公共接口 ====================
    @classmethod
    def getJavas(cls, force: bool = False) -> List[List[str]]:
        """
        同步获取系统中所有 Java 路径及版本。
        :param force: 是否强制刷新缓存
        :return: 列表，形如 [["C:\\...\\java.exe", "21.0.1"], ...]
        """
        if not force and cls._cache is not None and (time.time() - cls._cache_time) < cls._CACHE_TTL:
            return cls._cache
        result = asyncio.run(cls._async_get_javas())
        cls._cache = result
        cls._cache_time = time.time()
        return result

    @classmethod
    def getJavaVersion(cls, java_path: str) -> Optional[str]:
        """同步获取单个 Java 可执行文件的版本号"""
        return asyncio.run(cls._get_java_version_async(java_path))
