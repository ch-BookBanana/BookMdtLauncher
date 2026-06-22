# -*- coding: utf-8 -*-
"""
Copyright (C) 2026 BookBanana
轻量级 Windows Java 嗅探器（无缓存，不扫用户目录）
- 不执行 java.exe
- 不扫全盘
- 版本来源：注册表 > release 文件（若两者都无，则忽略该 JDK）
- 每次调用实时扫描，无缓存
"""

import os
import asyncio
import time
import winreg
from typing import List, Optional, Set, Dict
from .path_utils import getPath

class javaScanner:
    """轻量级 Windows Java 嗅探器（无缓存，不扫用户目录）"""

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

    # ---------- 版本获取：从 release 文件 ----------
    @classmethod
    def _get_version_from_release(cls, java_path: str) -> Optional[str]:
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
    @classmethod
    async def _scan_env_async(cls) -> Set[str]:
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
    @classmethod
    async def _scan_registry_async(cls) -> Dict[str, str]:
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
                        if depth > 3:
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
        all_paths = set()
        for r in results:
            if isinstance(r, set):
                all_paths.update(r)
        return all_paths

    # ---------- 主异步流程 ----------
    @classmethod
    async def _async_get_javas(cls) -> List[List[str]]:
        # 并行执行各扫描源（不再扫描用户目录）
        env_paths = await cls._scan_env_async()
        reg_map = await cls._scan_registry_async()
        common_paths = await cls._scan_common_dirs_async()

        # 合并所有路径
        all_paths = env_paths | common_paths

        final = []
        for p in all_paths:
            # 优先使用注册表版本
            ver = reg_map.get(p)
            if ver is None:
                # 注册表没有，尝试读取 release 文件
                ver = cls._get_version_from_release(p)
            # 如果两者都未提供版本，则忽略该路径
            if ver:
                final.append([p, ver])

        final.sort(key=lambda x: x[0].lower())
        return final

    # ---------- 公共接口（无缓存） ----------
    @classmethod
    def getJavas(cls) -> List[List[str]]:
        """
        同步获取系统中所有可确定版本的 Java 路径（实时扫描，无缓存）。
        :return: 列表，形如 [["C:\\...\\java.exe", "17.0.2"], ...]
                 只包含能通过注册表或 release 文件获取版本的 JDK。
        """
        return asyncio.run(cls._async_get_javas())

    @classmethod
    def getJavaVersion(cls, java_path: str) -> Optional[str]:
        """
        同步获取单个 Java 可执行文件的版本号（仅尝试读取 release 文件）。
        若失败则返回 None。
        """
        return cls._get_version_from_release(java_path)

    @classmethod
    def isJava(cls, java_path: str) -> bool:
        """
        检测输入路径的 java.exe 是否为有效 Java（不执行 java.exe）。
        判断标准：
        1. 文件存在且名为 java.exe
        2. 所在目录为 bin
        3. 能通过注册表或 release 文件获取到版本号
        """
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
        version = cls.getJavaVersion(java_path)
        return version is not None

    