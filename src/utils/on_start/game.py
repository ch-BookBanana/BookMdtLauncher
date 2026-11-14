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
"""启动时未完成的 mdt 游戏下载续传。"""

import hashlib
import json
import os

from ..QDownloader import QDownloader
from ..mdtManager import mdtManager
from ..path_utils import getPath
from ..utils import t


def _dest_dir(path):
    """dest 的父目录（规范化后），用于比较两条记录是不是指着同一个实例。"""
    try:
        return os.path.normcase(os.path.normpath(os.path.dirname(path or "")))
    except Exception:
        return ""


def _rewrite_record(name, info):
    """把修正后的 dest 写回 downloading.json；失败不影响本次续传。"""
    try:
        path = os.path.join(mdtManager.base_dir, name, "downloading.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        pass


def resume_mdt_downloads(root):
    """启动续传所有未完成的 mdt 游戏下载（downloading.json 记录），并同步暂停状态。

    通过 mdtManager.getDownloadingMdts() 获取下载中列表；
    有 .tmp/<task_id>/state.json → continue_task 续传；否则用 downloading.json
    的 url/dest 新建任务；downloading.json 记录 paused=true 时创建后立即暂停。
    """
    # 上次取消时线程还卡在网络请求里，临时目录没能当场删干净（标记文件在）。
    # 那些线程已经随进程消失，这里正好一次清掉，后面就不会再被当成待续传任务。
    try:
        QDownloader.clean_cancelled_tasks()
    except Exception:
        pass
    try:
        downloading = root.mdtManager.getDownloadingMdts() or {}
    except Exception as e:
        root.logger.warning(t(root.langer.get("core.log.warning.dlMdtScanError"), repr(e)))
        return
    if not downloading:
        return
    if not hasattr(root, "_mdt_downloads"):
        root._mdt_downloads = []
    for name, info in downloading.items():
        dest = info.get("dest") or ""
        url = info.get("url") or ""
        if not (dest and url):
            continue
        # 记录可能是启动器整个搬过家之前写的：dest 指着已经不存在的旧目录。
        # 按实例名把目标改回当前位置并写回 —— 不修的话续传会往旧路径写（甚至在
        # 旧位置重新建出目录），取消时按 dest 也找不回这个实例
        # （见 utils.mdt_dir_of_dest），于是「取消完重启又出现」。
        fixed = os.path.join(mdtManager.base_dir, name, "mdt.jar")
        if _dest_dir(dest) != _dest_dir(fixed):
            dest = fixed
            info["dest"] = dest
            _rewrite_record(name, info)
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
            dl.finished.connect(lambda ok, d=dl, n=name: on_mdt_download_finished(root, d, n, ok))
            root._mdt_downloads.append(dl)
            root.logger.info(t(root.langer.get("core.log.info.dlMdtResumeStart"), name, paused))
        except Exception as e:
            root.logger.warning(t(root.langer.get("core.log.warning.dlMdtResumeError"), name, repr(e)))


def on_mdt_download_finished(root, dl, name, ok):
    """启动续传任务收尾：释放 QDownloader；成功后刷新 BML.json 并删除 downloading.json。"""
    try:
        dl.wait_thread(5000)
        dl.deleteLater()
    except Exception:
        pass
    try:
        if dl in root._mdt_downloads:
            root._mdt_downloads.remove(dl)
    except Exception:
        pass
    if not ok:
        root.logger.error(t(root.langer.get("core.log.error.dlMdtFinishedFail"), name))
        return
    try:
        root.mdtManager._retrieve_mdt_data(name)
        dfile = getPath("BML/.Mindustrys/%s/downloading.json" % name)
        if os.path.isfile(dfile):
            os.remove(dfile)
        root.mdtManager.invalidate_cache()
        root.logger.info(t(root.langer.get("core.log.info.dlMdtFinishedOk"), name))
    except Exception as e:
        root.logger.error(t(root.langer.get("core.log.error.dlMdtFinishedCleanErr"), name, repr(e)))
