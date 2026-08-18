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
"""注册应用启动阶段的恢复任务。"""

from PySide6.QtCore import QTimer

from .. import javaDownload
from .game import resume_mdt_downloads
from .java import startup_resume_java


def register(root):
    """注册 Java、游戏和 appdataCopy 的启动恢复流程。"""
    root.java_flow = None
    root._java_flow_cancelled = False

    launcher = root.launcher
    launcher.java_missing.connect(lambda: root._java_show_status("missing"))
    launcher.java_status.connect(root._on_java_status)
    launcher.java_progress.connect(root._on_java_progress)
    launcher.java_extract_progress.connect(root._on_java_extract_progress)
    launcher.java_done.connect(root._on_java_download_done)
    launcher.java_cancelled.connect(root._on_java_cancelled)
    launcher.java_paused.connect(root._on_java_paused_changed)

    if javaDownload.get_status() in ("downloading", "extracting"):
        QTimer.singleShot(300, lambda: startup_resume_java(root))

    QTimer.singleShot(400, lambda: resume_mdt_downloads(root))
    QTimer.singleShot(500, root._resume_appdata_saves)
