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

下载列表浮层：正在下载/暂停/等待的任务，每条可续传、暂停、取消、删除。

原先长在 main.py 里（Window.Main.Top.DlList.DlListPage，四层嵌套），
由标题栏那个 DlList 按钮直接 new 出来。现在按浮层扩展点登记
（core.overlays），按钮只发一个 stackRequested 请求。

按钮（DlList）留在 main.py：它是窗口自己的零件，不是页面。它把 parent
交给本页，本页靠 parent.shown / update_shown 反过来告诉它「列表开着，
图标先别藏」—— 这一对是两者之间仅有的约定。
"""

import json
import os
import shutil
import time

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from ... import javaDownload
from ...bus import bus
from ...events import events
from ...options.scrolls import Scroll
from ...QDownloader import QDownloader
from ...QThTimer import QThTimer
from ...registry import Box, registry
from ...utils import _is_mdt_download, t


class DlListPage(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.parent.shown = False
        self.parent.update_shown()
        self.item_map = {}          # task_id -> Item
        self._closed = False
        self._timer = None
        self._last_java_paused = None   # 检测循环上次看到的 Java 暂停状态（变化时记日志）
        self.init_ui()
        self.langing()
        bus.bind(self)
        # 初始化时立即扫描一次，随后周期刷新
        self._timer = QThTimer.taskP(1000, self._snapshot_tasks, result_callback=self._render_items)
        QThTimer.task(0, self._snapshot_tasks, result_callback=self._render_items)

    def on_close(self):
        self._closed = True
        self.parent.shown = True
        self.parent.update_shown()
        try:
            if self._timer is not None:
                self._timer.destroy()
                self._timer = None
        except Exception:
            pass

    def init_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid", "color2")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 标题栏：标题 + 返回
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(44)
        self.layout.addWidget(self.top_bar, 0)
        self.top_layout = QHBoxLayout(self.top_bar)
        self.top_layout.setContentsMargins(15, 0, 10, 0)
        self.top_layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setProperty("wid", "text")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.top_layout.addWidget(self.title_label, 1)

        self.divider = QWidget()
        self.divider.setProperty("wid", "line")
        self.divider.setFixedHeight(1)
        self.layout.addWidget(self.divider, 0)

        # 任务列表滚动区
        self.list_container = QWidget()
        self.list_container.setAttribute(Qt.WA_StyledBackground, True)
        self.list_container.setStyleSheet("background: transparent")
        self.scroll = Scroll(self, content=self.list_container,
                             margins=(12, 12, 12, 12), spacing=8)
        self.list_layout = self.scroll.scroll_layout
        self.layout.addWidget(self.scroll, 1)

        # 空状态提示（始终位于列表末尾，任务卡片插入其前）
        self.empty_label = QLabel()
        self.empty_label.setProperty("wid", "title")
        self.empty_label.setStyleSheet("font-size: 14px;")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setFixedHeight(120)
        self.list_layout.addWidget(self.empty_label)

    def langing(self):
        self.title_label.setText(events.lang.get("core.wid.pages.downloadList.title"))
        self.empty_label.setText(events.lang.get("core.wid.pages.downloadList.empty"))

    def _snapshot_tasks(self, event):
        """子线程：收集运行中/暂停中与可续传任务的快照（不触碰 UI）。"""
        try:
            actives = {}
            for task_id, task in QDownloader.get_active_tasks().items():
                done, total = 0, 0
                try:
                    done, total = task.get_progress()
                except Exception:
                    pass
                actives[task_id] = {
                    "id": task_id,
                    "kind": "active",
                    "dest": task.dest_path or "",
                    "title": getattr(task, "title", "") or "",
                    "done": done,
                    "total": total,
                    "paused": bool(getattr(task, "_is_paused", False)),
                    "cancel_allowed": bool(getattr(task, "cancel_allowed", True)),
                    "pause_allowed": bool(getattr(task, "pause_allowed", True)),
                    "task": task,
                }
            pendings = {}
            for task_id, info in QDownloader.get_pending_tasks().items():
                pendings[task_id] = {
                    "id": task_id,
                    "kind": "pending",
                    "dest": info.get("dest_path") or "",
                    "title": info.get("title") or "",
                    "done": info.get("done_bytes") or 0,
                    "total": info.get("total_size") or 0,
                    "paused": False,
                    "task": None,
                    "state_file": info.get("state_file") or "",
                }
            return actives, pendings
        except Exception as e:
            return e

    def _render_items(self, result):
        if self._closed or isinstance(result, Exception):
            return
        actives, pendings = result
        # Java 下载状态同步：检测循环轮询读取任务实时状态，驱动 Launch 页 label。
        # 与 paused_changed 信号互补——信号丢失/时序错乱时，1 秒内轮询自动纠正，
        # 避免暂停瞬间被 progress 覆盖成"正在下载"后卡住。
        # 只更新 label 文本不切页，避免打断用户当前页面。
        try:
            for _t in actives.values():
                _dest = _t.get("dest") or ""
                if _dest.startswith(javaDownload.JAVA_TMP_DIR):
                    _total = _t.get("total") or 0
                    _done = _t.get("done") or 0
                    _pct = min(100, int(_done * 100.0 / _total)) if _total > 0 else 0
                    _paused = bool(_t.get("paused"))
                    events.emit("java_status", "paused" if _paused else "downloading", _pct)
                    # 检测循环日志：记录读取到的 Java 任务状态（含暂停/恢复切换），
                    # 用于排查信号竞争导致的"暂停后被覆盖成正在下载"
                    if _paused != self._last_java_paused:
                        events.logger.info(t(events.lang.get("core.log.info.dlJavaState"),
                                                "paused" if _paused else "downloading",
                                                _pct,
                                                os.path.basename(_dest) or _dest))
                        self._last_java_paused = _paused
                    break
        except Exception as e:
            events.logger.warning(t(events.lang.get("core.log.warning.dlJavaSyncError"), repr(e)))
        all_tasks = dict(actives)
        all_tasks.update(pendings)
        # 移除已消失的任务卡片
        for task_id in list(self.item_map.keys()):
            if task_id not in all_tasks:
                item = self.item_map.pop(task_id)
                self.list_layout.removeWidget(item)
                item.deleteLater()
        # 新增或刷新卡片
        for task_id, task_info in all_tasks.items():
            if task_id not in self.item_map:
                item = self.Item(self)
                item.continue_requested.connect(self._continue_task)
                item.delete_requested.connect(self._delete_task)
                self.item_map[task_id] = item
                self.list_layout.insertWidget(self.list_layout.count() - 1, item)
            else:
                item = self.item_map[task_id]
            item.set_data(task_info)
        self.empty_label.setVisible(not bool(all_tasks))

    def _continue_task(self, task_id):
        try:
            dl = QDownloader.continue_task(task_id)
            # 用户主动续传：清除 downloading.json 中的暂停状态（恢复下载）
            try:
                dest = getattr(dl, "dest_path", "") or ""
                if dest and _is_mdt_download(dest):
                    dfile = os.path.join(os.path.dirname(dest), "downloading.json")
                    if os.path.isfile(dfile):
                        with open(dfile, "r", encoding="utf-8") as f:
                            info = json.load(f)
                        if info.get("paused"):
                            info["paused"] = False
                            info["updated_at"] = int(time.time())
                            with open(dfile, "w", encoding="utf-8") as f:
                                json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                pass
        except Exception as e:
            events.logger.error(t(events.lang.get("core.log.error.dlResumeFailed"), task_id, e))

    def _delete_task(self, state_file):
        task_dir = os.path.dirname(state_file) if state_file else None
        if task_dir and os.path.isdir(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)
        # 若是 mdt 游戏下载：同时删除目标文件夹（含 downloading.json），
        # 避免残留记录导致下次启动又被续传
        try:
            dest = ""
            if state_file and os.path.isfile(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    dest = (json.load(f) or {}).get("dest_path", "") or ""
            if dest and _is_mdt_download(dest):
                mdir = os.path.dirname(dest)
                if os.path.isdir(mdir):
                    shutil.rmtree(mdir, ignore_errors=True)
                events.logger.info(t(events.lang.get("core.log.info.dlMdtDeleteCleaned"),
                                        os.path.basename(mdir) or mdir))
        except Exception:
            pass
        # 立即刷新一轮，不必等下一个周期
        QThTimer.task(0, lambda e: self._snapshot_tasks(e), result_callback=self._render_items)

    class Item(QWidget):
        continue_requested = Signal(str)
        delete_requested = Signal(str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent
            self.task_id = ""
            self.task = None      # 运行中任务的 QDownloader 实例（pending 为 None）
            self.state_file = ""
            self.task_info = {}
            self.init_ui()

        def init_ui(self):
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("wid", "color2")
            self.setStyleSheet("border-radius: 8px;")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 8, 12, 8)
            layout.setSpacing(6)

            # 第一行：文件名 + 状态
            row1 = QHBoxLayout()
            row1.setSpacing(8)
            self.title_label = QLabel()
            self.title_label.setProperty("wid", "text")
            self.title_label.setStyleSheet("font-size: 13px;")
            row1.addWidget(self.title_label, 1)
            self.status_label = QLabel()
            self.status_label.setProperty("wid", "title")
            self.status_label.setStyleSheet("font-size: 11px;")
            row1.addWidget(self.status_label, 0)
            layout.addLayout(row1)

            # 第二行：进度条 + 已下载/总大小
            row2 = QHBoxLayout()
            row2.setSpacing(8)
            self.progress_bar = QProgressBar()
            self.progress_bar.setProperty("wid", "progress")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setFixedHeight(14)
            row2.addWidget(self.progress_bar, 1)
            self.size_label = QLabel()
            self.size_label.setProperty("wid", "title")
            self.size_label.setStyleSheet("font-size: 11px;")
            self.size_label.setFixedWidth(120)
            row2.addWidget(self.size_label, 0)
            layout.addLayout(row2)

            # 第三行：主操作（暂停/继续/续传）+ 次操作（取消/删除）
            row3 = QHBoxLayout()
            row3.setSpacing(6)
            row3.addStretch(1)
            self.btn_primary = QPushButton()
            self.btn_primary.setProperty("wid", "btn")
            self.btn_primary.setFixedSize(64, 24)
            row3.addWidget(self.btn_primary, 0)
            self.btn_secondary = QPushButton()
            self.btn_secondary.setProperty("wid", "btn")
            self.btn_secondary.setFixedSize(64, 24)
            row3.addWidget(self.btn_secondary, 0)
            layout.addLayout(row3)

            self.btn_primary.clicked.connect(self._on_primary_clicked)
            self.btn_secondary.clicked.connect(self._on_secondary_clicked)

        @staticmethod
        def _fmt_size(size):
            size = max(0, int(size or 0))
            if size >= 1024 * 1024 * 1024:
                return "%.2f GB" % (size / (1024.0 ** 3))
            if size >= 1024 * 1024:
                return "%.2f MB" % (size / (1024.0 ** 2))
            if size >= 1024:
                return "%.1f KB" % (size / 1024.0)
            return "%d B" % size

        def set_data(self, task_info):
            self.task_info = task_info
            self.task_id = task_info.get("id") or ""
            task = task_info.get("task")
            if task is not self.task:
                self._disconnect_task_signals()
                self.task = task
                self._connect_task_signals()
            self.state_file = task_info.get("state_file") or ""

            # 名称（超长省略）：优先显示 title，回退文件名
            name = task_info.get("title") or os.path.basename(task_info.get("dest") or "") or self.task_id
            self.title_label.setText(QFontMetrics(self.title_label.font()).elidedText(name, Qt.ElideRight, 460))

            # 进度条与大小文本
            done = task_info.get("done") or 0
            total = task_info.get("total") or 0
            if total > 0:
                percent = min(100, int(done * 100.0 / total))
                self.progress_bar.setValue(percent)
                self.size_label.setText("%s / %s" % (self._fmt_size(done), self._fmt_size(total)))
            else:
                self.progress_bar.setValue(0)
                self.size_label.setText(self._fmt_size(done))

            # 状态文本与按钮语义
            if task_info.get("kind") == "active":
                if task_info.get("paused"):
                    self.status_label.setText(events.lang.get("core.wid.pages.downloadList.paused"))
                    self.btn_primary.setText(events.lang.get("core.wid.pages.downloadList.resume"))
                else:
                    self.status_label.setText(events.lang.get("core.wid.pages.downloadList.active"))
                    self.btn_primary.setText(events.lang.get("core.wid.pages.downloadList.pause"))
                self.btn_secondary.setText(events.lang.get("core.wid.pages.downloadList.cancel"))
            else:
                self.status_label.setText(events.lang.get("core.wid.pages.downloadList.pending"))
                self.btn_primary.setText(events.lang.get("core.wid.pages.downloadList.continue"))
                self.btn_secondary.setText(events.lang.get("core.wid.pages.downloadList.delete"))
            self._update_buttons()

        def _connect_task_signals(self):
            """监听任务允许状态变化，即时刷新按钮。"""
            if self.task is not None:
                try:
                    self.task.cancel_allowed_changed.connect(self._on_cancel_allowed_changed)
                except Exception:
                    pass
                try:
                    self.task.pause_allowed_changed.connect(self._on_pause_allowed_changed)
                except Exception:
                    pass

        def _disconnect_task_signals(self):
            if self.task is not None:
                try:
                    self.task.cancel_allowed_changed.disconnect(self._on_cancel_allowed_changed)
                except Exception:
                    pass
                try:
                    self.task.pause_allowed_changed.disconnect(self._on_pause_allowed_changed)
                except Exception:
                    pass

        def _on_cancel_allowed_changed(self, allowed):
            self.task_info["cancel_allowed"] = bool(allowed)
            self._update_buttons()

        def _on_pause_allowed_changed(self, allowed):
            self.task_info["pause_allowed"] = bool(allowed)
            self._update_buttons()

        def _update_buttons(self):
            """根据任务允许状态显示/隐藏操作按钮。"""
            if self.task_info.get("kind") == "active":
                self.btn_primary.setVisible(bool(self.task_info.get("pause_allowed", True)))
                self.btn_secondary.setVisible(bool(self.task_info.get("cancel_allowed", True)))
            else:
                self.btn_primary.setVisible(True)
                self.btn_secondary.setVisible(True)

        def _on_primary_clicked(self):
            # 运行中：暂停/继续；待续传：请求页面续传
            if self.task_info.get("kind") == "active":
                if self.task is not None and self.task_info.get("pause_allowed", True):
                    if self.task_info.get("paused"):
                        self.task.resume()
                        self._sync_mdt_paused(False)
                    else:
                        self.task.pause()
                        self._sync_mdt_paused(True)
            else:
                self.continue_requested.emit(self.task_id)

        def _sync_mdt_paused(self, paused):
            """暂停/恢复时把状态写入 .Mindustrys/<name>/downloading.json（仅 mdt 游戏下载）。

            启动时通过 getDownloadingMdts 读取该状态同步暂停。
            """
            dest = getattr(self.task, "dest_path", "") or ""
            if not _is_mdt_download(dest):
                return
            dfile = os.path.join(os.path.dirname(dest), "downloading.json")
            try:
                info = {}
                if os.path.isfile(dfile):
                    with open(dfile, "r", encoding="utf-8") as f:
                        info = json.load(f)
                info["paused"] = bool(paused)
                info["updated_at"] = int(time.time())
                os.makedirs(os.path.dirname(dfile), exist_ok=True)
                with open(dfile, "w", encoding="utf-8") as f:
                    json.dump(info, f, ensure_ascii=False, separators=(",", ":"))
                _state = events.lang.get("core.log.info.javaPausedState" if paused else "core.log.info.javaResumedState")
                events.logger.info(t(events.lang.get("core.log.info.dlMdtPausedState"),
                                        _state,
                                        os.path.basename(os.path.dirname(dest)) or ""))
            except Exception as e:
                events.logger.warning(t(events.lang.get("core.log.warning.dlMdtPausedError"), repr(e)))

        def _on_secondary_clicked(self):
            # 运行中：取消（子线程执行阻塞式取消，取消后删除 mdt 目标文件夹）；
            # 待续传：请求页面删除
            if self.task_info.get("kind") == "active":
                if self.task is not None and self.task_info.get("cancel_allowed", True):
                    def _do_cancel(e, t=self.task, dest=self.task_info.get("dest") or ""):
                        try:
                            t.cancel(timeout=8)
                        finally:
                            # mdt 游戏下载：取消后删除目标文件夹（含 downloading.json）
                            if dest and _is_mdt_download(dest):
                                mdir = os.path.dirname(dest)
                                try:
                                    if os.path.isdir(mdir):
                                        shutil.rmtree(mdir, ignore_errors=True)
                                    events.logger.info(t(events.lang.get("core.log.info.dlMdtCancelCleaned"),
                                                            os.path.basename(mdir) or mdir))
                                except Exception:
                                    pass
                    QThTimer.task(0, _do_cancel, dedicated=True)
            else:
                self.delete_requested.emit(self.state_file)


def register():
    """把下载列表交给 core.overlays。由 pages/builtin.py 调用一次。"""
    registry.add("core.stacks", "core.dlList",
                 init=lambda b: DlListPage(b.parent),
                 order=30, title="core.wid.pages.downloadList.title")
