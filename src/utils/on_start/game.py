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
import os

from ..QDownloader import QDownloader
from ..mdtScanner import mdtScanner
from ..path_utils import getPath
from ..utils import t


def resume_mdt_downloads(root):
    """启动续传所有未完成的 mdt 游戏下载（downloading.json 记录），并同步暂停状态。

    通过 mdtScanner.getDownloadingMdts() 获取下载中列表；
    有 .tmp/<task_id>/state.json → continue_task 续传；否则用 downloading.json
    的 url/dest 新建任务；downloading.json 记录 paused=true 时创建后立即暂停。
    """
    try:
        downloading = root.mdtScanner.getDownloadingMdts() or {}
    except Exception as e:
        root.logger.warning(t(root.langer.get("log.dl.mdt_scan_error"), repr(e)))
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
            root.logger.info(t(root.langer.get("log.dl.mdt_resume_start"), name, paused))
        except Exception as e:
            root.logger.warning(t(root.langer.get("log.dl.mdt_resume_error"), name, repr(e)))


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
        root.logger.error(t(root.langer.get("log.dl.mdt_finished_fail"), name))
        return
    try:
        root.mdtScanner._retrieve_mdt_data(name)
        dfile = getPath("BML/.Mindustrys/%s/downloading.json" % name)
        if os.path.isfile(dfile):
            os.remove(dfile)
        root.mdtScanner.invalidate_cache()
        root.logger.info(t(root.langer.get("log.dl.mdt_finished_ok"), name))
    except Exception as e:
        root.logger.error(t(root.langer.get("log.dl.mdt_finished_clean_err"), name, repr(e)))
