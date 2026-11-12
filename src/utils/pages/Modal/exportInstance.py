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

导出实例浮层。

为什么要有这条路
----------------
在它之前，用户想把一个实例带走，唯一办法是点「打开数据文件夹」然后自己去
``.Mindustrys`` 里翻 —— 而那个按钮打开的是 ``<实例>/data/Mindustry``，
``mdt.jar`` 还要往上两层，界面上没有任何地方告诉过他路径。等于「能拿到」
只对开发者成立。

这里做的事就是替他把「找目录 → 挑文件 → 压包」三步合成一次点击，并且写一个
``bml-export.json`` 让导回去时不用猜这是什么。

交互取舍
--------
打开即给好一个默认路径（桌面/实例名.zip），点确定就开始导 —— 不为「先选保存
位置」多拦一道。想换位置随时点浏览。

导出成功后不自动关窗：用户需要看见「存到哪了、几个文件、多大」。关掉之后这些
信息没有任何地方可以回看（没有 toast，日志也不给普通用户看）。

脱敏默认打开
------------
包里最危险的不是客户端，是 ``data/Mindustry/settings.bin`` 里的 ``usid-*`` ——
服务器身份，拿到即可冒充。所以这里默认抹掉，宁可让换机自用的人多点一下取消
勾选，也不让「顺手发给别人看看」变成把身份一起送出去。规则见 instanceSanitize。
"""

import os
import threading

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from shiboken6 import isValid

from ...bus import bus
from ...events import events
from ...instanceExport import export_instance
from ...mdtManager import mdtManager
from ...qthtimer import QThTimer
from ...registry import registry
from ...resources import TBT_CLOSE
from ...utils import change_color, primary_btn_style, t


class ExportInstance(QWidget):
    """把一个实例打包成 zip。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        # 实例名在打开时取一次：浮层存续期间它不会变（改名要开另一个浮层），
        # 而 parent.game 会在切实例时变，中途跟着变会把包写到别人身上
        self.game = str(getattr(parent, "game", "") or "")
        self._busy = False
        self._done = False
        self._closed = False
        # 浅色/深色：确定按钮的禁用灰度按主题取（lighting() 会随后校准）
        self._light = bool(events.settings.get("theme"))
        # 取消标志用 Event：子线程里读，界面线程里 set，不依赖 Qt 的线程亲和性
        self._cancel = threading.Event()

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid", "color2")
        self.init_wid()
        self.path.setText(self._default_dest())
        self.path.setToolTip(self.path.text())
        self.langing()
        self.lighting(bool(events.settings.get("theme")))
        self._refresh()
        bus.bind(self)

    # ---------- 界面 ----------

    def init_wid(self):
        # 420x344：比导入高，因为多了「包含存档」「抹去个人信息」两个选项与说明
        self.setFixedSize(420, 344)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignTop)

        self.top = QWidget()
        self.top.setProperty("wid", "plain")    # 裸 QWidget 会被全局规则刷成底色
        self.top.setFixedHeight(30)
        self.layout.addWidget(self.top, 0)
        self.top_l = QHBoxLayout(self.top)
        self.top_l.setContentsMargins(15, 0, 3, 0)
        self.top_l.setSpacing(0)

        self.title = QLabel()
        self.title.setProperty("wid", "title")
        self.title.setStyleSheet("font-size: 16px;")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.top_l.addWidget(self.title, 1)

        self.btn_close = QPushButton()
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setProperty("wid", "tbtn")
        self.btn_close.clicked.connect(self._close)
        self.top_l.addWidget(self.btn_close, 0)

        self.line = QWidget()
        self.line.setFixedHeight(1)
        self.line.setProperty("wid", "line")
        self.layout.addWidget(self.line, 0)

        self.body = QWidget()
        self.body.setProperty("wid", "color2")
        self.layout.addWidget(self.body, 1)
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(15, 12, 15, 15)
        self.body_l.setSpacing(8)
        self.body_l.setAlignment(Qt.AlignTop)

        # 说明：写明包里有什么，用户点确定前就知道自己在导出什么
        self.desc = QLabel()
        self.desc.setProperty("wid", "text")
        self.desc.setStyleSheet("font-size: 13px;")
        self.desc.setWordWrap(True)
        self.body_l.addWidget(self.desc, 0)

        # 是否连存档一起导：默认勾上。只导客户端本体的场景（「我就要这个 jar」）
        # 用不上 zip，直接拷 mdt.jar 更省事，所以这里不把它做成默认。
        self.opt = QCheckBox()
        self.opt.setChecked(True)
        # 复选框自带底板会被全局 QWidget 规则刷成一整条深色横带（同容器问题）
        self.opt.setStyleSheet("font-size: 13px; background: transparent;")
        self.opt.toggled.connect(lambda _: self._refresh())
        self.body_l.addWidget(self.opt, 0)

        # 抹去个人信息：默认勾上。这个默认值是有意识的取舍 —— 忘掉勾它的代价是
        # 把 usid 连同服务器身份一起发出去（不可逆、不可撤回），而误勾的代价只是
        # 接收端要重新登录、丢掉在服务器上的管理员身份（可以再要回来）。
        # 换机自用的人看得到这行字，取消勾选即可。
        self.priv = QCheckBox()
        self.priv.setChecked(True)
        self.priv.setStyleSheet("font-size: 13px; background: transparent;")
        self.priv.toggled.connect(lambda _: self._refresh())
        self.body_l.addWidget(self.priv, 0)

        # 保存位置行：输入框可编辑（用户能自己粘路径），浏览按钮给不会拼路径的人
        self.path_row = QWidget()
        # 同导入浮层：容器不画底，否则「浏览」按钮的透明背景会透出深一档的色
        self.path_row.setProperty("wid", "plain")
        self.body_l.addWidget(self.path_row, 0)
        self.path_l = QHBoxLayout(self.path_row)
        self.path_l.setContentsMargins(0, 0, 0, 0)
        self.path_l.setSpacing(8)

        self.path = QLineEdit()
        self.path.setProperty("wid", "input")
        self.path.setFixedHeight(32)
        self.path.textChanged.connect(lambda _: self._refresh())
        self.path_l.addWidget(self.path, 1)

        self.btn_pick = QPushButton()
        self.btn_pick.setProperty("wid", "btn")
        self.btn_pick.setFixedSize(80, 32)
        self.btn_pick.clicked.connect(self._pick)
        self.path_l.addWidget(self.btn_pick, 0)

        self.tip = QLabel()
        self.tip.setProperty("wid", "text")
        self.tip.setStyleSheet("font-size: 13px;")
        self.tip.setWordWrap(True)
        self.body_l.addWidget(self.tip, 1)

        self.bottom = QWidget()
        self.bottom.setProperty("wid", "plain")
        self.body_l.addWidget(self.bottom, 0)
        self.bottom_l = QHBoxLayout(self.bottom)
        self.bottom_l.setContentsMargins(0, 0, 0, 0)
        self.bottom_l.setSpacing(8)
        self.bottom_l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_ok = QPushButton()
        self.btn_ok.setProperty("wid", "btn")
        self.btn_ok.setFixedSize(80, 30)
        self.btn_ok.setStyleSheet(primary_btn_style(self._light, False))
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._on_ok)
        self.bottom_l.addWidget(self.btn_ok, 0)

    def langing(self):
        lang = events.lang
        self.title.setText(lang.get("core.wid.pages.exportInstance.title"))
        self.btn_close.setToolTip(lang.get("core.wid.top.close"))
        self.desc.setText(t(lang.get("core.wid.pages.exportInstance.desc"), self.game))
        self.opt.setText(lang.get("core.wid.pages.exportInstance.opt"))
        self.priv.setText(lang.get("core.wid.pages.exportInstance.priv"))
        self.priv.setToolTip(lang.get("core.wid.pages.exportInstance.priv.tip"))
        self.btn_pick.setText(lang.get("core.wid.pages.importJar.pick"))
        self.btn_ok.setText(lang.get("core.text.yes"))
        self._refresh()

    def lighting(self, light):
        color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
        icon = change_color(TBT_CLOSE, color)
        self.btn_close.setIcon(QIcon(icon.pixmap(24, 24)))
        # 禁用灰按主题取值，切主题后要重算；_refresh 在导出中/已完成时会自己早退
        self._light = bool(light)
        self._refresh()

    def _default_dest(self):
        """桌面/实例名.zip。桌面取不到（无此目录的精简系统）就退回用户目录。"""
        base = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
        if not base or not os.path.isdir(base):
            base = os.path.expanduser("~")
        return os.path.join(base, (self.game or "Mindustry") + ".zip")

    # ---------- 选保存位置 ----------

    def _pick(self):
        if self._busy:
            return
        lang = events.lang
        current = self.path.text().strip() or self._default_dest()
        path, _ = QFileDialog.getSaveFileName(
            self, lang.get("core.wid.pages.exportInstance.saveTitle"),
            current, lang.get("core.wid.pages.exportInstance.filter"))
        if not path:
            return
        if not path.lower().endswith(".zip"):
            # 用户在对话框里把扩展名删了：补回来。不补的话导出的文件双击
            # 打不开，而它明明是能用的 zip
            path += ".zip"
        self.path.setText(path)
        self.path.setToolTip(path)
        self._refresh()

    # ---------- 状态 ----------

    def _refresh(self):
        if self._busy or self._done:
            return
        lang = events.lang
        ok = bool(self.path.text().strip())
        self.btn_ok.setEnabled(ok)
        self.btn_ok.setStyleSheet(primary_btn_style(self._light, ok))
        self.tip.setStyleSheet("font-size: 13px;")
        if not ok:
            self.tip.setText(lang.get("core.wid.pages.exportInstance.path.none"))
        elif not self.opt.isChecked():
            self.tip.setText(lang.get("core.wid.pages.exportInstance.clientOnly"))
        else:
            self.tip.setText("")

    # ---------- 导出 ----------

    def _on_ok(self):
        if self._done:
            self._close()
            return
        if self._busy:
            return
        dest = self.path.text().strip()
        if not dest:
            self._pick()
            dest = self.path.text().strip()
            if not dest:
                return

        self._busy = True
        self._cancel.clear()
        self.btn_pick.setEnabled(False)
        self.path.setEnabled(False)
        self.opt.setEnabled(False)
        self.priv.setEnabled(False)
        self.btn_ok.setEnabled(False)
        self.btn_ok.setStyleSheet(primary_btn_style(self._light, False))
        self.tip.setStyleSheet("font-size: 13px;")
        self.tip.setText(t(events.lang.get("core.wid.pages.exportInstance.exporting"), 0))

        meta = {"name": self.game}
        try:
            version = mdtManager.getMdtMsg(self.game) or {}
            # mod / modVersion / baseVersion 是 fork 的自报家门（MindustryX 等）：
            # 只记 build 的话，接收方看到的又是一个「MDT 版本」而不是这一版改端
            for key in ("build", "modifier", "number", "type",
                        "mod", "modVersion", "baseVersion"):
                meta[key] = str(version.get(key) or "")
        except Exception:
            # 读不到版本就不是致命问题：包照样能导，只是标记文件里少几个字段
            pass

        root = os.path.join(mdtManager.base_dir, self.game)
        include_data = self.opt.isChecked()
        sanitize = self.priv.isChecked()

        # 打包 100 MB 在机械盘上要十几秒，必须在子线程；dedicated=True 是因为
        # 它比共享队列里那些「查一下」的任务长得多，混在一起会把它们堵住
        QThTimer.task(
            0,
            lambda e: export_instance(
                root, dest, meta=meta,
                progress=lambda f: e.lambdas[0].emit(f),
                cancel=self._cancel.is_set,
                include_data=include_data,
                sanitize=sanitize),
            events=[self._on_progress],
            result_callback=self._on_done,
            dedicated=True,
        )

    def _on_progress(self, frac):
        if self._closed or not isValid(self) or not self._busy:
            return
        self.tip.setText(t(events.lang.get("core.wid.pages.exportInstance.exporting"),
                           int(max(0.0, min(1.0, float(frac))) * 100)))

    def _on_done(self, result):
        if self._closed or not isValid(self):
            return
        self._busy = False
        self.btn_pick.setEnabled(True)
        self.path.setEnabled(True)
        self.opt.setEnabled(True)
        self.priv.setEnabled(True)

        if isinstance(result, Exception) or not result or not result[0]:
            code = "ioError" if isinstance(result, Exception) else (
                result[1] if result else "ioError")
            self.tip.setStyleSheet("font-size: 13px; color: red;")
            self.tip.setText(events.lang.get("core.wid.pages.exportInstance.failed") + "  "
                             + events.lang.get("core.wid.pages.exportInstance.err." + str(code)))
            # 路径还在：用户换块盘/腾出空间后可以直接重试
            self.btn_ok.setEnabled(True)
            self.btn_ok.setStyleSheet(primary_btn_style(self._light, True))
            detail = ""
            if not isinstance(result, Exception) and isinstance(result[2], dict):
                detail = str(result[2].get("detail") or "")
            events.logger.error("[export] 导出 %s 失败: %s %s" % (self.game, code, detail))
            return

        stats = result[2] or {}
        self._done = True
        self.btn_ok.setText(events.lang.get("core.text.done"))
        self.btn_ok.setEnabled(True)
        self.btn_ok.setStyleSheet(primary_btn_style(self._light, True))
        self.tip.setStyleSheet("font-size: 13px; color: #4a9a4a;")
        msg = t(events.lang.get("core.wid.pages.exportInstance.done"),
                str(stats.get("files", 0)),
                "%.1f" % (float(stats.get("zip_bytes", 0)) / 1048576.0))
        # 抹掉了多少要当面说清楚：用户勾了那个框，就得知道它到底做了什么，
        # 而不是只能相信「已脱敏」这四个字
        if stats.get("sanitized"):
            removed = int(stats.get("removed") or 0)
            if removed:
                msg += "  " + t(events.lang.get("core.wid.pages.exportInstance.stripped"),
                                str(removed), str(stats.get("serverIds") or 0))
            else:
                msg += "  " + events.lang.get("core.wid.pages.exportInstance.stripped.none")
        # 跳过数是游戏正开着时才会出现的：日志/存档被占用，那些文件没进包。
        # 不说明的话用户会以为导出是完整的。
        if stats.get("skipped"):
            msg += "  " + t(events.lang.get("core.wid.pages.exportInstance.skipped"),
                            str(stats["skipped"]))
        self.tip.setText(msg)
        events.logger.info("[export] 已导出 %s -> %s (%s 个文件)" %
                           (self.game, self.path.text(), stats.get("files")))

    # ---------- 出叠 ----------

    def _close(self):
        events.emit("overlayClosed", self, True)

    def on_close(self):
        self._closed = True
        # 正在打包时关窗：让子线程在下一个块边界停下并删掉半成品。不这么做的话
        # 用户关了窗、文件还在后台慢慢长，最后留下一个看似完成的 zip。
        self._cancel.set()


def register():
    """把导出浮层交给 core.overlays。由 pages/builtin.py 调用一次。"""
    registry.add("core.overlays", "core.exportInstance",
                 init=lambda b: ExportInstance(b.parent),
                 title="core.wid.pages.exportInstance.title")
