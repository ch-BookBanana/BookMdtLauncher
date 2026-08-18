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
"""启动时 Java 未完成下载的接管续传。"""

from PySide6.QtCore import QTimer

from ..javaDownload import JavaDownloadFlow, get_status, load_info
from ..utils import t


def startup_resume_java(root):
    """程序启动时发现未完成的 Java 下载：切页并同步状态，接管续传。

    左 stacked（left.bottom）显示"正在下载未完成的Java..."，
    主区（right.main）同步切到 Launch 页，等待一秒后
    切换"正在下载Java"并拉起 QDownloader 实例，继续流程。
    """
    status = get_status()
    if status not in ("downloading", "extracting"):
        return
    root.logger.info(t(root.langer.get("log.java.resume_takeover"), status), name="Java")
    # 同时切 left.bottom 与 right.main 到 Launch 页（唯一状态 label）
    try:
        bottom = root._java_bottom()
        bottom.setCurrentIndex(3)
        root._java_stack().setCurrentIndex(3)
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
        if root.java_flow is not None:
            return
        try:
            if root.launcher._java_flow is not None:
                return
        except Exception:
            pass
        begin_java_flow(root, resume=True)
    QTimer.singleShot(1000, _resume_once)


def begin_java_flow(root, resume=False):
    """拉起 Java 下载流程（仅启动延续流程使用）。

    resume=True: 从 javaDownload.json 续传（程序启动延续流程）；
    点击开始游戏触发的自动下载由 launcher 内置管理。
    """
    if root.java_flow is not None:
        return
    root.logger.info(t(root.langer.get("log.java.flow_create"), resume), name="Java")
    flow = JavaDownloadFlow(resume=resume)
    root.java_flow = flow
    flow.status_changed.connect(root._on_java_status)
    flow.progress.connect(root._on_java_progress)
    flow.extract_progress.connect(root._on_java_extract_progress)
    flow.finished.connect(root._on_java_finished)
    flow.cancelled.connect(root._on_java_flow_cancelled)
    flow.paused_changed.connect(root._on_java_paused_changed)
    flow.error.connect(lambda msg: root.logger.error(t(root.langer.get("log.java.dl_error_prefix"), str(msg))))
    flow.start()
