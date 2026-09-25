"""游戏实例锁：启动游戏期间禁止改名/删除实例与本体。

由「句柄 + 共享模式」实现，通过不带 FILE_SHARE_DELETE 把改名/删除挡在系统层：
  - 目录：共享模式 READ|WRITE → 目录自身改不动名/删不掉，里面仍可新建与写入文件；
  - 文件：共享模式 READ        → 本体文件既不能改也不能改名/删除；
  - 被 exclude 的子树（数据目录）完全不持句柄，游戏与用户都能自由读写改；
  - 句柄随进程退出自动释放，即使崩溃也不会遗留锁（区别于 ACL 方案）。

注意：Windows 专属实现（CreateFileW/CloseHandle）。
"""

import ctypes
import logging
import os

from ctypes import wintypes

_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000   # 打开目录必需的标志，对文件无副作用
_INVALID_HANDLE = ctypes.c_void_p(-1).value

# 共享模式就是锁的语义（Win32 的改名/删除都要 DELETE 访问权，缺 FILE_SHARE_DELETE 即被拒）：
# 目录带 WRITE 是为了目录里还能建文件——实例目录里常要放下载中的临时文件
_DIR_SHARE = _FILE_SHARE_READ | _FILE_SHARE_WRITE

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateFileW = _kernel32.CreateFileW
_CreateFileW.restype = wintypes.HANDLE
_CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.restype = wintypes.BOOL
_CloseHandle.argtypes = (wintypes.HANDLE,)

_log = logging.getLogger("Main.MdtLocker")


class mdtLocker:
    """持有文件/目录句柄：锁住期间它们改不了名也删不掉，本体文件还不可被写。"""

    def __init__(self):
        self.path = None
        self.handles = []

    def lock(self, root, exclude=()):
        """锁定 root 自身与其下全部内容，exclude 的整棵子树跳过。

        根目录排在最前，所以实例目录本身一定拿到句柄：谁想改名/删除实例都会被拒。
        返回 (已锁定数量, 打开失败数量)；重复调用会先释放上一次的锁。
        """
        self.unlock()
        if not os.path.isdir(root):
            return 0, 0
        self.path = os.path.abspath(root)
        skips = [os.path.normcase(os.path.abspath(p)) for p in exclude]
        locked = failed = 0
        for target in self._targets(self.path, skips):
            share = _DIR_SHARE if os.path.isdir(target) else _FILE_SHARE_READ
            handle = _CreateFileW(target, _GENERIC_READ, share, None,
                                  _OPEN_EXISTING, _FILE_FLAG_BACKUP_SEMANTICS, None)
            if handle and handle != _INVALID_HANDLE:
                self.handles.append(handle)
                locked += 1
                _log.debug("locked: " + target)
            else:
                failed += 1
                _log.debug("lock failed: " + target)
        return locked, failed

    def unlock(self):
        """释放全部句柄；未持锁时无副作用。"""
        for handle in self.handles:
            _CloseHandle(handle)
        self.handles = []
        self.path = None

    @staticmethod
    def _in_skips(path, skips):
        """path 是否落在任一被排除的子树内（含子树自身）。"""
        norm = os.path.normcase(path)
        return any(norm == skip or norm.startswith(skip + os.sep) for skip in skips)

    @classmethod
    def _targets(cls, root, skips):
        """先给 root 自身，再给其中所有子目录/文件；被排除的子树不下钻。"""
        yield root
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames
                           if not cls._in_skips(os.path.join(dirpath, name), skips)]
            for name in dirnames:
                yield os.path.join(dirpath, name)
            for name in filenames:
                yield os.path.join(dirpath, name)
