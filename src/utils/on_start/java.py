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
"""Java 下载流程：启动时未完成下载的接管续传、延续流程拉起，以及下载 UI 回调/辅助函数。

main.py 的 Main 通过 `attach(root)` 挂载本模块的 UI 回调（root._java_* / root._on_java_*），
保持原 Main 方法调用点不变。
"""

import types

from PySide6.QtCore import QTimer

from ..javaDownload import JavaDownloadFlow, get_status
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


# ==================== Java 下载流程的 UI 回调/辅助函数 ====================
# 原为 main.py Main 类方法，拆分后改为模块级函数（第一个参数 root），
# 通过 attach(root) 绑定为 Main 实例方法，保持 main.py 内 self._java_* 调用点不变。


def _java_bottom(root):
    """Start 页左栏 Bottom（QStackedWidget）：0=Start 1=Mod 2=World 3=Launch 4=Suspend。"""
    return root.window.main.main.start.left.main


def _java_stack(root):
    """Start 页主区 stack（QStackedWidget）：0=Start 1=Mod 2=World 3=Launch 4=Log。"""
    return root.window.main.main.start.main.stack


def _on_java_status(root, status):
    """Java 下载/解压状态变化：left.bottom 与 right.main 都切到 Launch 页并更新 label。"""
    try:
        root.logger.info(t(root.langer.get("log.java.status_change"), status), name="Java")
        bottom = _java_bottom(root)
        bottom.setCurrentIndex(3)
        _java_stack(root).setCurrentIndex(3)
        bottom.launch.setStatus(status)
    except Exception as e:
        print("[java_ui_status]", status, "ERR:", repr(e))


def _on_java_progress(root, done, total):
    """下载字节进度 → label 显示百分比（如 正在下载Java... 45%）。"""
    try:
        pct = int(done * 100 / total) if total else 0
        bottom = _java_bottom(root)
        bottom.setCurrentIndex(3)
        _java_stack(root).setCurrentIndex(3)
        bottom.launch.setStatus("downloading", pct)
    except Exception as e:
        print("[java_ui_progress]", done, total, "ERR:", repr(e))


def _on_java_extract_progress(root, done, total):
    """解压进度 → label 显示百分比（如 正在解压Java... 45%）。"""
    try:
        pct = int(done * 100 / total) if total else 0
        bottom = _java_bottom(root)
        bottom.setCurrentIndex(3)
        _java_stack(root).setCurrentIndex(3)
        bottom.launch.setStatus("extracting", pct)
    except Exception as e:
        print("[java_ui_extract]", done, total, "ERR:", repr(e))


def _on_java_paused_changed(root, paused, pct):
    """Java 下载暂停/恢复 → label 显示"Java暂停下载 n%"或恢复"正在下载Java n%"。"""
    try:
        _state = root.langer.get("log.java.paused_state" if paused else "log.java.resumed_state")
        root.logger.info(t(root.langer.get("log.java.paused_change"), _state, pct), name="Java")
        bottom = _java_bottom(root)
        bottom.setCurrentIndex(3)
        _java_stack(root).setCurrentIndex(3)
        if paused:
            bottom.launch.setStatus("paused", pct)
        else:
            bottom.launch.setStatus("downloading", pct)
    except Exception as e:
        print("[java_ui_paused]", paused, pct, "ERR:", repr(e))


def _on_java_flow_cancelled(root):
    """启动延续流程的下载被用户取消（下载列表页/退出）：记录标记。"""
    root.logger.info(root.langer.get("log.java.flow_cancelled"), name="Java")
    root._java_flow_cancelled = True


def _on_java_cancelled(root):
    """launcher 内置 Java 下载被用户取消：显示"已取消"，一秒后回主界面。"""
    root.logger.info(root.langer.get("log.java.dl_cancelled_show"), name="Java")
    _java_show_status(root, "cancelled")
    QTimer.singleShot(1000, lambda: _java_go_home(root))


def _on_java_finished(root, ok):
    """启动延续流程结束：显示"Java部署完成/失败/已取消"，等待一秒后返回主界面。

    （run 触发的下载由 launcher 内置管理，其 java_done 信号走 _on_java_download_done）
    """
    flow = root.java_flow
    root.java_flow = None   # 释放流程引用（QDownloader 已完成并注销）
    if flow is not None:
        try:
            flow.shutdown()   # 确保下载/解压线程完全退出后再释放
        except Exception:
            pass
    cancelled = root._java_flow_cancelled
    root._java_flow_cancelled = False
    root.logger.info(t(root.langer.get("log.java.flow_finished"), ok, cancelled), name="Java")
    if ok:
        _java_show_status(root, "done")
    elif cancelled:
        _java_show_status(root, "cancelled")   # 用户主动取消，不误报"下载失败"
    else:
        _java_show_status(root, "error")
    QTimer.singleShot(1000, lambda: _java_go_home(root))


def _on_java_download_done(root, ok):
    """launcher 内置 Java 下载流程结束：显示结果，一秒后由 launcher 自动重新 run 或回主界面。

    ok=True：launcher 内部已刷新 Java 设置并重新启动游戏（game_launched 信号会切页）；
    ok=False：显示失败，一秒后回主界面。
    """
    root.logger.info(t(root.langer.get("log.java.dl_finished_show"), ok), name="Java")
    if ok:
        _java_show_status(root, "done")
    else:
        _java_show_status(root, "error")
        QTimer.singleShot(1000, lambda: _java_go_home(root))


def _java_show_status(root, status):
    """left.bottom 与 right.main 都切到 Launch 页并更新唯一状态 label。"""
    try:
        bottom = _java_bottom(root)
        bottom.setCurrentIndex(3)
        _java_stack(root).setCurrentIndex(3)
        bottom.launch.setStatus(status)
    except Exception as e:
        print("[java_ui_show]", status, "ERR:", repr(e))


def _java_go_home(root):
    """返回主界面（左 stacked 与主区均回到 Start 页）。"""
    try:
        _java_bottom(root).setCurrentIndex(0)
        _java_stack(root).setCurrentIndex(0)
    except Exception:
        pass


def _java_cancel_all(root):
    """取消当前 Java 下载流程（用户手动取消/退出时）。

    仅当确实存在流程时才打印日志并执行取消，避免退出时产生误导性日志。
    """
    flow = root.java_flow
    root.java_flow = None
    lf = None
    try:
        lf = root.launcher._java_flow
        root.launcher._java_flow = None
    except Exception:
        pass
    if flow is None and lf is None:
        # 没有任何流程，无需打印"取消全部流程"
        return
    root.logger.info(root.langer.get("log.java.cancel_all"), name="Java")
    if flow is not None:
        try:
            flow.cancel()
        except Exception:
            pass
    if lf is not None:
        try:
            lf.cancel()
        except Exception:
            pass


def _resume_appdata_saves(root):
    """启动时续传未完成的 appdataCopy 保存任务（launcher 内部处理 step=1/step=2）。"""
    try:
        root.launcher.resume_appdata_saves()
    except Exception as e:
        root.logger.warning(t(root.langer.get("log.appdata.resume_scan_error"), repr(e)))


def attach(root):
    """把 Java 下载流程的 UI 回调/辅助函数绑定为 root（Main）实例方法。

    main.py 及 on_start/startup.py 中通过 root._java_* / root._on_java_* 访问，
    此处保持原有调用点不变。
    """
    for fn in (
        _java_bottom, _java_stack,
        _on_java_status, _on_java_progress, _on_java_extract_progress,
        _on_java_paused_changed, _on_java_flow_cancelled, _on_java_cancelled,
        _on_java_finished, _on_java_download_done,
        _java_show_status, _java_go_home, _java_cancel_all,
        _resume_appdata_saves,
    ):
        setattr(root, fn.__name__, types.MethodType(fn, root))
