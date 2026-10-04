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
"""系统已装 Java 的发现与校验（带缓存，不扫用户目录）。

- 不执行 java.exe，不扫全盘
- 候选来源：PATH、常见安装目录，以及注册表登记过的 JavaHome
  （注册表那批可能装在常见目录之外，只认 PATH + 常见目录会把它们漏掉）
- 版本来源：注册表 > release 文件（若两者都无，则忽略该 JDK）
- 结果带 TTL 缓存；界面显示期间用 watch() 起一条低频子线程轮询，候选表变了才发
  changed。调用方不必自己开线程，也不该在 GUI 线程里同步扫盘
"""

import os
import asyncio
import time
import winreg
from typing import List, Optional, Set, Dict

from PySide6.QtCore import QObject, Signal

from .QThTimer import QThTimer
from .path_utils import getPath


class _JavaManager(QObject):
    """系统已装 Java 的发现与校验（带缓存，不扫用户目录）。"""

    changed = Signal(list)     # 候选表变了：在主线程发出，携带新表

    TTL = 30.0       # 缓存有效期（秒）：新鲜就直接用，省掉反复扫盘
    POLL_MS = 5000   # 关注期间的重扫间隔（毫秒）：够灵敏，又不至于一直啃盘

    # ---------- 扫描路径配置 ----------
    _COMMON_DIRS = [
        r'C:\Program Files\Java',
        r'C:\Program Files (x86)\Java',
        r'C:\Program Files\Eclipse Adoptium',
        r'C:\Program Files\Eclipse Foundation',
        r'C:\Program Files\Amazon Corretto',
        r'C:\Program Files\Azul',
        r'C:\Program Files\GraalVM',
        r'C:\Java',
        os.path.expandvars(r'%USERPROFILE%\.jdks'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\AdoptOpenJDK'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\Eclipse Adoptium'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\Eclipse Foundation'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\Amazon Corretto'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\Azul'),
        getPath('BML/.Java'),
    ]

    def __init__(self):
        super().__init__()
        self.settings = None      # main 挂进来的 settings：里面存着用户手动加过的 Java
        self._cache = None        # 最近一次扫描结果
        self._cache_at = 0.0      # 最近一次扫描时间（time.monotonic）
        self._last = None         # 上次广播出去的候选表：一样就不重复发信号
        self._scanning = False    # 扫描在路上：慢盘下别把共享线程的同一件事堆起来
        self._watchers = 0        # 关注者计数：归零就停轮询
        self._poll = None

    # ==================== 关注：界面显示期间低频轮询 ====================
    def watch(self):
        """开始关注候选表：先子线程扫一遍，之后每 POLL_MS 复扫；有变化发 changed。

        与 unwatch() 成对，用在「界面显示期间」：有人看才轮询，没人看就停，
        不常驻扫盘。关注后第一趟结果一定会广播（_last 清空），界面据此填下拉框。
        """
        self._watchers += 1
        self._last = None
        self.scan()
        if self._poll is None:
            self._poll = QThTimer.timer(self.POLL_MS, [self.scan])

    def unwatch(self):
        """取消关注：最后一个关注者离开后停掉轮询。"""
        if self._watchers <= 0:
            return
        self._watchers -= 1
        if self._watchers == 0 and self._poll is not None:
            self._poll.destroy()
            self._poll = None

    def scan(self):
        """在子线程重扫一遍；扫完回主线程落缓存并广播（结果没变就不广播）。"""
        if self._scanning:
            return   # 上一趟还没回来（盘慢/网络盘），跳过这一拍
        self._scanning = True

        def job(event):
            return asyncio.run(self._async_get_javas())

        def done(result):
            self._scanning = False
            if isinstance(result, Exception):
                return   # 扫失败保持旧缓存，免得界面被一次抖动清空
            self._publish(result)

        QThTimer.task(0, job, result_callback=done)

    # ---------- 版本获取：从 release 文件 ----------
    def _get_version_from_release(self, java_path: str) -> Optional[str]:
        """
        从 JDK 根目录的 release 文件中读取 JAVA_VERSION。
        若文件不存在或解析失败，返回 None。
        """
        jdk_root = os.path.dirname(os.path.dirname(java_path))  # .../bin/java.exe -> 根目录
        release_file = os.path.join(jdk_root, "release")
        if not os.path.isfile(release_file):
            return None
        try:
            with open(release_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith("JAVA_VERSION="):
                        ver = line.split('=', 1)[1].strip().strip('"')
                        return ver if ver else None
        except Exception:
            return None
        return None

    # ---------- 扫描源：PATH ----------
    async def _scan_env_async(self) -> Set[str]:
        """从 PATH 环境变量中查找 java.exe"""
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

    # ---------- 扫描源：注册表（同时获取版本） ----------
    async def _scan_registry_async(self) -> Dict[str, str]:
        """
        从 Windows 注册表读取已安装的 JDK。
        返回 {java.exe路径: 版本号}，版本号来自注册表 'Version' 值。
        """
        def _sync():
            result = {}
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
                                                version = None
                                                try:
                                                    version, _ = winreg.QueryValueEx(ver_key, "Version")
                                                except OSError:
                                                    pass
                                                if version:
                                                    result[candidate] = version
                                    except OSError:
                                        break
                        except OSError:
                            continue
            return result

        try:
            return await asyncio.to_thread(_sync)
        except Exception:
            return {}

    # ---------- 扫描源：常见安装目录（限深3层） ----------
    async def _scan_common_dirs_async(self) -> Set[str]:
        async def scan_one(root_dir: str) -> Set[str]:
            if not os.path.isdir(root_dir):
                return set()
            def _walk_sync():
                found = set()
                try:
                    for current, dirs, files in os.walk(root_dir):
                        depth = current[len(root_dir):].count(os.sep)
                        if depth > 3:
                            dirs.clear()
                            continue
                        if 'java.exe' in files and os.path.basename(current).lower() == 'bin':
                            found.add(os.path.join(current, 'java.exe'))
                except PermissionError:
                    pass
                return found
            return await asyncio.to_thread(_walk_sync)

        tasks = [scan_one(d) for d in self._COMMON_DIRS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_paths = set()
        for r in results:
            if isinstance(r, set):
                all_paths.update(r)
        return all_paths

    # ---------- 主异步流程 ----------
    async def _async_get_javas(self) -> List[List[str]]:
        # 并行执行各扫描源（不再扫描用户目录）
        env_paths = await self._scan_env_async()
        reg_map = await self._scan_registry_async()
        common_paths = await self._scan_common_dirs_async()

        # 合并所有路径：注册表登记的 JavaHome 也算候选——JDK 可能装在 _COMMON_DIRS
        # 之外的自定义盘符/目录，只认 PATH + 常见目录会漏；再深的目录不去追
        # （全盘遍历的代价远大于收益，这是刻意的取舍）
        # 用户手动加过的（settings["javaPaths"]）是知道的目录，一并带上：它们多半就装在
        # 常见目录之外，扫描源找不到；路径已失效的会因取不到版本在下面被剔掉
        saved_paths = {self.resolve(item[0]) for item in ((self.settings or {}).get("javaPaths") or []) if item}
        all_paths = env_paths | common_paths | set(reg_map) | saved_paths

        final = []
        for p in all_paths:
            # 优先使用注册表版本
            ver = reg_map.get(p)
            if ver is None:
                # 注册表没有，尝试读取 release 文件
                ver = self._get_version_from_release(p)
            # 如果两者都未提供版本，则忽略该路径
            if not ver:
                continue
            # 同一个 java.exe 常常从 PATH、注册表、常见目录、候选表几路一起进来，写法还各自不同
            # （大小写、斜杠、相对/绝对）：按真身去掉重复，再统一成 record() 的记法
            path = self.record(p)
            if any(self.sameJava(path, item[0]) for item in final):
                continue
            final.append([path, ver])

        final.sort(key=lambda x: x[0].lower())
        return final

    # ==================== 公共接口 ====================
    def getJavas(self, force=False) -> List[List[str]]:
        """
        同步获取系统中所有可确定版本的 Java 路径（缓存新鲜就直接给）。

        :param force: True 时无视缓存当场重扫（启动前定 Java、下载完重挑 Java 用）。
        :return: 列表，形如 [["C:\\...\\java.exe", "17.0.2"], ...]
                 只包含能通过注册表或 release 文件获取版本的 JDK。

        只给「马上就要一个结果」的地方用，会阻塞调用线程；界面显示一律走 watch()，
        别在 GUI 线程里扫盘。
        """
        cached = self._fresh()
        if cached is not None and not force:
            return [list(java) for java in cached]
        try:
            javas = asyncio.run(self._async_get_javas())
        except Exception:
            return []
        return [list(java) for java in self._publish(javas)]

    def _fresh(self):
        """缓存还新鲜就返回它，否则 None。"""
        if self._cache is None or time.monotonic() - self._cache_at >= self.TTL:
            return None
        return self._cache

    def _publish(self, javas):
        """落缓存；候选表真的变了才广播（轮询不能每次都把下拉框重填一遍）。"""
        self._cache = javas
        self._cache_at = time.monotonic()
        if javas != self._last:
            self._last = javas
            self.changed.emit([list(java) for java in javas])
        return javas

    def resolve(self, java_path: str) -> str:
        """候选表里允许存相对启动器目录的路径（打包分发时能跟着走），这里解析回绝对。"""
        if java_path and not os.path.isabs(java_path):
            return os.path.normpath(os.path.join(getPath(""), java_path))
        return java_path

    def record(self, java_path: str) -> str:
        """候选表里的记法：装在启动器目录里就记相对路径（整个启动器文件夹能整体搬走），
        否则记绝对路径；统一正斜杠，免得同一个 java.exe 被记成两条。"""
        full = self.resolve(java_path)
        try:
            rel = os.path.relpath(full, getPath(""))
        except ValueError:
            rel = None   # 跨盘：相对路径算不出来，只能记绝对
        if rel and rel != ".." and not rel.startswith(".." + os.sep):
            return rel.replace("\\", "/")
        return full.replace("\\", "/")

    def sameJava(self, java_a: str, java_b: str) -> bool:
        """这两个记法是不是同一个 java.exe：大小写、斜杠、相对/绝对写法不同也算同一个。

        文件在盘上就比真身（samefile）；不在盘上（已失效）时退回按路径比。
        """
        java_a = self.resolve(java_a)
        java_b = self.resolve(java_b)
        if not java_a or not java_b:
            return False
        try:
            return os.path.samefile(java_a, java_b)
        except OSError:
            return os.path.normcase(os.path.normpath(java_a)) == os.path.normcase(os.path.normpath(java_b))

    def getJavaVersion(self, java_path: str) -> Optional[str]:
        """
        同步获取单个 Java 可执行文件的版本号（仅尝试读取 release 文件）。
        若失败则返回 None。
        """
        return self._get_version_from_release(self.resolve(java_path))

    def isJava(self, java_path: str) -> bool:
        """
        检测输入路径的 java.exe 是否为有效 Java（不执行 java.exe）。
        判断标准：
        1. 文件存在且名为 java.exe
        2. 所在目录为 bin
        3. 能通过注册表或 release 文件获取到版本号
        """
        java_path = self.resolve(java_path)
        if not java_path or not os.path.isfile(java_path):
            return False

        # 检查文件名是否为 java.exe (忽略大小写)
        if os.path.basename(java_path).lower() != 'java.exe':
            return False

        # 检查父目录是否为 bin
        parent_dir = os.path.dirname(java_path)
        if os.path.basename(parent_dir).lower() != 'bin':
            return False

        # 尝试获取版本，如果能获取到版本，则认为是有效的 Java 环境
        version = self.getJavaVersion(java_path)
        return version is not None


javaManager = _JavaManager()
