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

导入本地 JAR 浮层。

为什么要有这条路
----------------
BML 原先只有「从 GitHub Releases 下载」一个入口：离线环境、别人给的 jar、自己
编译的 bleeding-edge 构建，全都没地方放。下载那条链路上每个环节都绑着下载器
（downloading.json、QDownloader、断点续传），本地文件用不上，所以单开一条：
选文件 → 验包 → 定名 → 落盘。

界面形状照抄下载页那个命名弹窗（同样「一两个输入 + 提示 + 确定」），多出来的
一行是文件选择 —— 「选的是哪个包」必须一直看得见，否则改完名字就分不清自己在
导哪一个了。

职责边界：校验口径全在 jarImport 与 mdtManager.importJar 里（都不碰界面），
本文件只负责把结果画出来，以及把「验包 / 拷贝」这两件会卡住界面的事丢到子线程。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from shiboken6 import isValid

from ...bus import bus
from ...events import events
from ...jarImport import blank_info, inspect_package, suggest_name, version_text
from ...mdtManager import mdtManager
from ...qthtimer import QThTimer
from ...registry import registry
from ...resources import TBT_CLOSE
from ...utils import change_color, primary_btn_style, t


class ImportJar(QWidget):
    """选一个本地 jar，收成实例。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self._jar = ""          # 选中的 jar 路径
        self._info = None       # inspect_jar 的结果；None 表示还在验
        self._final_name = None # 这次提交实际会用的名字（撞名时是加过后缀的）
        self._user_named = False
        self._busy = False
        self._closed = False
        # 浅色/深色：确定按钮的禁用灰度按主题取，先按当前设置落一个初值，
        # 随后 lighting() 会把它校准（bus.bind 补主题时会立刻回调一次）
        self._light = bool(events.settings.get("theme"))
        # 遮罩与居中由叠加浮层统一提供，本页自身即弹窗面板
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid", "color2")
        self.init_wid()
        self.langing()
        self.lighting(bool(events.settings.get("theme")))
        self._refresh()
        # 总线补主题会立刻回调一次 lighting，所以必须放在控件建好之后
        bus.bind(self)

    # ---------- 界面 ----------

    def init_wid(self):
        # 420x260：比命名弹窗宽一倍 —— 中间要摆得下 jar 的绝对路径；
        # 高度多出来的部分全给提示行（版本信息、拒收原因、导入进度共用那一行）
        self.setFixedSize(420, 260)

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

        # 文件行：只读输入框（路径多半比按钮长，能选中复制）+ 浏览
        self.file_row = QWidget()
        # 容器自身不画底：否则「浏览」按钮的透明背景会透出这层被全局 QWidget
        # 规则染深一档的颜色，看上去就像按钮自己变暗了
        self.file_row.setProperty("wid", "plain")
        self.body_l.addWidget(self.file_row, 0)
        self.file_l = QHBoxLayout(self.file_row)
        self.file_l.setContentsMargins(0, 0, 0, 0)
        self.file_l.setSpacing(8)

        self.file = QLineEdit()
        self.file.setProperty("wid", "input")
        self.file.setFixedHeight(32)
        self.file.setReadOnly(True)
        self.file_l.addWidget(self.file, 1)

        self.btn_pick = QPushButton()
        self.btn_pick.setProperty("wid", "btn")
        self.btn_pick.setFixedSize(80, 32)
        self.btn_pick.clicked.connect(self._pick)
        self.file_l.addWidget(self.btn_pick, 0)

        # 名称行：规则与下载页命名弹窗、管理页改名弹层完全同一套
        # （mdtManager.check_name 判字形、name_conflict 判占用、unique_name 加后缀）
        self.input = QLineEdit()
        self.input.setProperty("wid", "input")
        self.input.setFixedHeight(32)
        self.input.setClearButtonEnabled(True)
        # 名字即目录名，上限与 check_name 同源，超长直接打不进去
        self.input.setMaxLength(mdtManager.MAX_NAME_LEN)
        self.input.textChanged.connect(self._refresh)
        self.input.textEdited.connect(self._on_name_edited)
        self.body_l.addWidget(self.input, 0)

        # 状态行：版本/大小、拒收原因、导入进度都写这里。**只有一行**，
        # 优先级写死在 _refresh 里 —— 三个来源各占一个控件就会互相覆盖。
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
        self.title.setText(lang.get("core.wid.pages.importJar.title"))
        self.btn_close.setToolTip(lang.get("core.wid.top.close"))
        self.btn_pick.setText(lang.get("core.wid.pages.importJar.pick"))
        self.file.setPlaceholderText(lang.get("core.wid.pages.importJar.file"))
        self.input.setPlaceholderText(lang.get("core.wid.pages.importJar.name"))
        self.btn_ok.setText(lang.get("core.text.yes"))
        self._refresh()     # 提示是译文，切语言得按新语言重算一遍

    def lighting(self, light):
        # 关闭按钮图标随主题取色（面板其余部分交给全局 qss）
        color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
        icon = change_color(TBT_CLOSE, color)
        self.btn_close.setIcon(QIcon(icon.pixmap(24, 24)))
        # 禁用态的中性灰按主题取不同的值，切主题后必须重算一遍；_refresh 顺带
        # 把「能否点确定」也重新判断一次，两件事都落在同一条路径上。
        # 导入中不刷：_refresh 会重写提示行，把「导入中 45%」冲掉。
        self._light = bool(light)
        if not self._busy:
            self._refresh()

    # ---------- 选文件与验包 ----------

    def _pick(self):
        if self._busy:
            return
        lang = events.lang
        path, _ = QFileDialog.getOpenFileName(
            self,
            lang.get("core.wid.pages.importJar.pickTitle"),
            "",
            lang.get("core.wid.pages.importJar.filter"))
        if not path:
            return
        self.set_path(path)

    def set_path(self, path):
        """选定一个包并开始验包。

        浏览与拖放共用这一条：拖进来的文件不该走另一套「先落盘再说」的逻辑，
        否则同一个包从两个入口进来会有两种校验口径（以及两处要单独修）。
        浮层刚建好、还没显示时也能调 —— 控件在 __init__ 里就全建好了。
        """
        if self._busy or not path:
            return
        self._jar = path
        self._info = None
        self.file.setText(path)
        self.file.setToolTip(path)
        self._refresh()
        # 验包放子线程：只读中央目录，正常是毫秒级，但网络盘/机械盘上的大包
        # 也能到几百毫秒 —— 那点卡顿正好落在「选完文件」这一刻，最像卡死。
        # 路径按值绑定（p=path）而不是让线程去读 self._jar：用户可能连着换两个
        # 文件，读实例字段会让「A 的结果」落到「B 的路径」上。
        #
        # inspect_package 而不是 inspect_jar：同一个入口要同时认客户端 jar 与
        # BML 导出的实例包，按包内标记分流，界面不必让用户先选「我要导哪种」。
        QThTimer.task(0, lambda e, p=path: (p, inspect_package(p)),
                      result_callback=self._on_probe)

    def _on_probe(self, result):
        """验包结果回主线程：好包就把默认名填上，坏包把原因写在提示行。"""
        if self._closed or not isValid(self):
            return
        if isinstance(result, Exception):
            # QThTimer 把 job 里漏出来的异常原样回传（见 task 的 _wrapped_job）
            path, info = self._jar, blank_info()
            info["error"] = "notZip"
        else:
            path, info = result
            if isinstance(info, Exception):
                info = blank_info()
                info["error"] = "notZip"
        if path != self._jar:
            return      # 期间又选了别的文件，这份结果已经过期
        self._info = info
        if info["ok"] and not self._user_named:
            # 用户自己敲过的名字不许被覆盖 —— 默认名只负责「还没输」的情况
            self.input.setText(suggest_name(info, path))
        self._refresh()

    def _on_name_edited(self, _text):
        self._user_named = True

    # ---------- 状态计算 ----------

    def _refresh(self, *_):
        """重算这一屏的两件事：提示行写什么、确定能不能点。

        优先级（写死在一处，见 init_wid 里关于「只有一行提示位」的说明）：
            没选文件 → 验包中 → 包不能收 → 名字不能收 → 版本信息。
        """
        lang = events.lang
        info = self._info
        text = self.input.text().strip()
        self._final_name = None
        msg, style, border = "", "", ""
        enabled = False
        name_bad = False

        if not self._jar:
            msg = lang.get("core.wid.pages.importJar.file.none")
        elif info is None:
            msg = lang.get("core.wid.pages.importJar.reading")
        elif not info["ok"]:
            msg = lang.get("core.wid.pages.importJar.err." + str(info.get("error") or "notZip"))
            style = "color: red;"
        else:
            if info.get("kind") == "instance":
                # 实例包报体积与条目数，不报版本号：用户此刻想知道的是「这个包
                # 里到底有没有东西」，而 83 MB 的空壳和 83 MB 带二十个存档的包
                # 从大小上看不出区别，条目数能。
                msg = t(lang.get("core.wid.pages.importJar.info.instance"),
                        "%.1f" % (info.get("size", 0) / 1048576.0),
                        str(info.get("members", 0)))
            else:
                msg = t(lang.get("core.wid.pages.importJar.info"),
                        version_text(info, prefix="") or "?",
                        "%.1f" % (info.get("size", 0) / 1048576.0))
            if not text:
                msg = msg + "  " + lang.get("core.wid.pages.importJar.name.none")
            else:
                error = mdtManager.check_name(text)
                if error == "dot":
                    msg = lang.get("core.wid.pages.download.item.name.dot")
                    style, border, name_bad = "color: red;", "border: 1px solid red;", True
                elif error:
                    msg = lang.get("core.wid.pages.download.item.name.illegal")
                    style, border, name_bad = "color: red;", "border: 1px solid red;", True
                elif events.mdtManager.name_conflict(text):
                    # 撞名不拦：加后缀照样能导 —— 与下载页、改名页同一处理。
                    # 「将用某个名字」接在包信息后面，而不是整行替换掉：用户
                    # 此刻在看的是「这个包是什么」，名字只是顺带确认一下，
                    # 把它上面那句「实例包 · 83 MB · 含 7 个文件」冲掉不划算。
                    self._final_name = events.mdtManager.unique_name(text)
                    msg = msg + "  " + t(lang.get("core.wid.pages.download.item.name.willBe"),
                                         self._final_name)
                    style = "color: #d8b64a;"
                    enabled = True
                else:
                    self._final_name = text
                    enabled = True

        self.tip.setText(msg)
        self.tip.setStyleSheet("font-size: 13px;" + style)
        # 描边只反映「名字本身不合法」；包有问题时红的是提示行，不是输入框
        self.input.setStyleSheet(border if name_bad else "")
        if not self._busy:
            self._set_ok(enabled)

    def _set_ok(self, enabled):
        """确定按钮的可用态与配色一起切（禁用时是中性灰，不是压暗的黄）。"""
        self.btn_ok.setEnabled(enabled)
        self.btn_ok.setStyleSheet(primary_btn_style(self._light, enabled))

    # ---------- 导入 ----------

    def _on_ok(self):
        if self._busy or not self._final_name:
            return
        jar, name = self._jar, self._final_name
        self._busy = True
        self.btn_pick.setEnabled(False)
        self.input.setEnabled(False)
        self._set_ok(False)
        self.tip.setStyleSheet("font-size: 13px;")
        self.tip.setText(t(events.lang.get("core.wid.pages.importJar.importing"), 0))

        # 拷贝 90 MB 的包在机械盘上要几秒，必须离开主线程；dedicated=True 是因为
        # 它比共享线程里那些「查一下」的任务长得多，占着共享队列会把别的任务堵住。
        QThTimer.task(
            0,
            lambda e: events.mdtManager.importJar(
                jar, name, progress=lambda f: e.lambdas[0].emit(f)),
            events=[self._on_progress],
            result_callback=self._on_done,
            dedicated=True,
        )

    def _on_progress(self, frac):
        if self._closed or not isValid(self) or not self._busy:
            return
        self.tip.setText(t(events.lang.get("core.wid.pages.importJar.importing"),
                           int(max(0.0, min(1.0, float(frac))) * 100)))

    def _on_done(self, result):
        if self._closed or not isValid(self):
            # 用户中途把浮层关了：拷贝本身会走完（它已经在子线程里），实例会在
            # 下一次 3 秒巡检时自己出现在列表里 —— 这里只管别再碰已销毁的控件。
            return
        self._busy = False
        self.btn_pick.setEnabled(True)
        self.input.setEnabled(True)

        if isinstance(result, Exception) or not result or not result[0]:
            code = "ioError" if isinstance(result, Exception) else (
                result[1] if result else "ioError")
            self.tip.setStyleSheet("font-size: 13px; color: red;")
            self.tip.setText(events.lang.get("core.wid.pages.importJar.failed") + "  "
                             + events.lang.get("core.wid.pages.importJar.err." + str(code)))
            # 名字仍然是合法的：留着确定可点，用户换块盘/腾出空间后能直接重试
            self._set_ok(bool(self._final_name))
            events.logger.error("[import] 导入 %s 失败: %s" % (self._jar, code))
            return

        final = result[2]
        events.logger.info("[import] 已导入实例 %s" % final)
        self._close()
        # 落盘之后交给常规巡检：它负责把这个目录登记进 gameList（发 newGame），
        # 列表与左栏都按那个事件增量更新，这里不必自己拼一遍界面。
        events.mdtManager.invalidate_cache()
        events.mdtManager.checkGame()
        # 切到刚导入的这个：用户刚做的动作，界面应该跟着走。取不到页面实例时
        # 就不管了 —— 下一次（3 秒）巡检会把 defaultGame 修到有效值上。
        try:
            from ..start import _page
            _page().changeGame(final)
        except Exception:
            pass

    # ---------- 出叠 ----------

    def _close(self):
        events.emit("overlayClosed", self, True)

    def on_close(self):
        """出叠时置旗：子线程的进度/结果回调据此停手（浮层随后就 deleteLater）。"""
        self._closed = True


def register():
    """把导入浮层交给 core.overlays。由 pages/builtin.py 调用一次。"""
    registry.add("core.overlays", "core.importJar",
                 init=lambda b: ImportJar(b.parent),
                 title="core.wid.pages.importJar.title")
