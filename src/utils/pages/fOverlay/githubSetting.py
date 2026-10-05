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

GitHub 设置浮层：token 的增删改测、账号信息、rate 余量。

原先长在 main.py 里（Window.GithubSetting，约 690 行），由 Window 在启动时
**建好并一直攥着**，打开它的按钮直接点 Window 的方法 —— 窗口因此认识这个类，
面板也永远只有那一个实例（改完配置关掉再开，看到的还是旧状态）。
现在按浮层扩展点登记（core.overlays），谁要打开就从注册表取条目现建。

面板尺寸 520x365：它是浮在窗口上的小卡片，跟设置页那条 600px 正文列不是一个口径。
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from ...api import githubAPI
from ...bus import bus
from ...events import events
from ...options.scrolls import Scroll
from ...path_utils import getPath
from ...QThTimer import QThTimer
from ...registry import Box, registry
from ...resources import ACT_TIPS, TBT_CLOSE
from ...utils import change_color


def sync_rate_from_api():
    """把 GithubAPI 的实时 rate 同步到 settings 内存（不写盘）。

    只是把一份内存数据挪个地方：不碰控件，所以不必挂在页面上 ——
    面板刷新与「token 校验后重取」两处都要，写成模块函数谁都能调。
    """
    rate = events.githubAPI.rate
    s = events.settings["github"]
    s["rate"]["core"] = {
        "remaining": rate["core"]["remaining"],
        "reset": rate["core"]["reset"]
    }
    s["rate"]["search"] = {
        "remaining": rate["search"]["remaining"],
        "reset": rate["search"]["reset"]
    }


def clear_token_data():
    """清除 settings 里所有 token 相关数据（仅在 token 确认无效时调用）。"""
    events.githubAPI.setToken(None)
    s = events.settings["github"]
    s["token_enc"] = None
    s["token_key"] = None
    s["useful"] = None
    s["user"] = {"name": None, "headurl": None}


class GithubSetting(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()
        self.init_wid()
        self.hide()

    def init_ui(self):
        # 遮罩与居中由所属叠加浮层（FloatingOverlay）统一提供，本页仅承载 Panel
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid_", "_window.github")

    def init_wid(self):
        self.l = QHBoxLayout(self)
        self.l.setContentsMargins(0, 0, 0, 0)
        self.l.setSpacing(0)
        self.l.setAlignment(Qt.AlignCenter)

        self.panel = self.Panel(self)
        self.l.addWidget(self.panel,0)

    def showEvent(self, event):
        # 显示时提层，盖过 floatingStack 等覆盖控件
        super().showEvent(event)
        self.raise_()

    def close_(self):
        """关闭自身：从叠加浮层出叠。

        不再留着实例复用（原先传 deletable=False）—— 现在每次打开都是现建的，
        留个旧实例在叠外只会让面板停在过期数据上。
        """
        events.emit("overlayClosed", self, True)

    class Panel(QWidget):
        def __init__(self, parent=None):
            super().__init__()
            self.parent = parent
            self.githubAPI = events.githubAPI
            self.init_ui()
            self.init_wid()
            self.githubAPI.refreshed.connect(self._on_rate_refreshed)


        def init_ui(self):
            self.setFixedSize(520,365)
            self.setAttribute(Qt.WA_StyledBackground, True)

        def _on_rate_refreshed(self):
            sync_rate_from_api()
            if self.isVisible():
                self.body.content._update_rate_section()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignTop)

            self.top = self.Top(self)
            self.layout.addWidget(self.top,0)

            self.line = QWidget(self)
            self.line.setFixedHeight(1)
            self.line.setProperty("wid","line")
            self.layout.addWidget(self.line,0)

            self.body = self.Body(self)
            self.layout.addWidget(self.body,1)


        class Top(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.parent = parent
                self.init_ui()
                self.init_wid()

            def init_ui(self):
                self.setFixedHeight(30)
                self.setAttribute(Qt.WA_StyledBackground, True)

            def init_wid(self):
                self.layout = QHBoxLayout(self)
                self.layout.setContentsMargins(30, 0, 0, 0)
                self.layout.setSpacing(0)
                self.layout.setAlignment(Qt.AlignLeft)

                self.title = QLabel("GitHub")
                self.title.setProperty("wid", "title")
                self.title.setStyleSheet("font-size: 16px;")
                self.layout.addWidget(self.title,0)

                self.layout.addStretch(1)

                self.close = self.Close(self)
                self.layout.addWidget(self.close,0)

                self.close.clicked.connect(self.parent.parent.close_)

            class Close(QPushButton):
                def __init__(self, parent=None):
                    super().__init__()
                    self.parent = parent
                    self.init_ui()
                    bus.bind(self)

                def init_ui(self):
                    self.setFixedSize(30, 30)
                    self.setProperty("wid", "tbtn")

                def lighting(self, light: bool):
                    color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                    logo = change_color(getPath(TBT_CLOSE),color)
                    icon = QIcon(logo.pixmap(30,30))

                    self.setIcon(icon)

        class Body(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.parent = parent
                self.init_wid()

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setSpacing(0)

                self.content = self.Content(self)
                self.layout.addWidget(self.content)

            class Content(Scroll):
                def __init__(self, parent=None):
                    # 原先这里是 super().__init__(parent, root, …) —— 而 Scroll 的第二个
                    # 位置参数是 horizontal，传进去的宿主对象一直被当成 True，内容区
                    # 这些年其实是按**横向**排的。现在按本意竖排。
                    super().__init__(parent, margins=(20, 20, 20, 20), spacing=10)
                    self.parent = parent
                    self._editing = False
                    self.init_wid()
                    self.langing()
                    bus.bind(self)

                def init_wid(self):
                    self.layout = self.scroll_layout

                    self.l1w = QWidget()
                    self.l1w.setFixedHeight(84)
                    self.layout.addWidget(self.l1w,0)

                    self.l1 =QHBoxLayout(self.l1w)
                    self.l1.setContentsMargins(0, 0, 0, 0)
                    self.l1.setSpacing(0)

                    self.headIcon = QLabel()
                    self.headIcon.setProperty("wid","png")
                    self.headIcon.setFixedSize(84,84)
                    self.headIcon.setStyleSheet("border-radius:42px;")
                    self.l1.addWidget(self.headIcon,0)

                    self.l1_l1w = QWidget()
                    self.l1.addWidget(self.l1_l1w,1)

                    self.l1_l1 = QVBoxLayout(self.l1_l1w)
                    self.l1_l1.setContentsMargins(10, 0, 0, 0)
                    self.l1_l1.setSpacing(5)
                    self.l1_l1.setAlignment(Qt.AlignTop)

                    self.userName = QLabel("User-Name")
                    self.userName.setProperty("wid","text")
                    self.userName.setStyleSheet("font-size: 22px;")
                    self.userName.setAlignment(Qt.AlignLeft)
                    self.userName.setFixedHeight(24)
                    self.l1_l1.addWidget(self.userName,0)

                    self.tokenStatus = QLabel("")
                    self.tokenStatus.setProperty("wid","title")
                    self.tokenStatus.setStyleSheet("font-size: 11px;")
                    self.tokenStatus.setAlignment(Qt.AlignLeft)
                    self.tokenStatus.setFixedHeight(14)
                    self.l1_l1.addWidget(self.tokenStatus,0)

                    self.l1_l1_l1w = QWidget()
                    self.l1_l1.addWidget(self.l1_l1_l1w,1)

                    self.l1_l1_l1 = QHBoxLayout(self.l1_l1_l1w)
                    self.l1_l1_l1.setContentsMargins(0, 0, 0, 0)
                    self.l1_l1_l1.setSpacing(5)

                    self.coreBadge = QLabel()
                    self.coreBadge.setProperty("wid","badge")
                    self.coreBadge.setFixedHeight(20)
                    self.l1_l1_l1.addWidget(self.coreBadge,0)

                    self.searchBadge = QLabel()
                    self.searchBadge.setProperty("wid","badge")
                    self.searchBadge.setFixedHeight(20)
                    self.l1_l1_l1.addWidget(self.searchBadge,0)

                    self.l1_l1_l1.addStretch(1)

                    self.layout.addSpacing(14)

                    self.tokenTips = QWidget()
                    self.tokenTips.setStyleSheet(
                        "QWidget#tokenTips{"
                        "background-color: rgba(255, 255, 0, 50);"
                        "border: 1px solid orange;"
                        "border-radius: 4px;"
                        "}"
                    )
                    self.tokenTips.setObjectName("tokenTips")
                    tips_l = QHBoxLayout(self.tokenTips)
                    tips_l.setContentsMargins(6, 5, 6, 5)
                    tips_l.setSpacing(6)

                    self.tokenTipsIcon = QLabel()
                    self.tokenTipsIcon.setFixedSize(18, 18)
                    self.tokenTipsIcon.setScaledContents(True)
                    tips_l.addWidget(self.tokenTipsIcon, 0, Qt.AlignTop)

                    self.tokenTipsText = QLabel()
                    self.tokenTipsText.setProperty("wid", "text")
                    self.tokenTipsText.setStyleSheet("font-size: 10px;")
                    self.tokenTipsText.setWordWrap(True)
                    tips_l.addWidget(self.tokenTipsText, 1)

                    self.layout.addWidget(self.tokenTips, 0)

                    self.layout.addSpacing(8)

                    self.tokenTitle = QLabel()
                    self.tokenTitle.setProperty("wid","text")
                    self.tokenTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                    self.tokenTitle.setFixedHeight(18)
                    self.layout.addWidget(self.tokenTitle,0)

                    self.tokenStack = QStackedWidget()
                    self.tokenStack.setFixedHeight(32)
                    self.layout.addWidget(self.tokenStack,0)

                    self.tokenInputW = QWidget()
                    self.tokenInputL = QHBoxLayout(self.tokenInputW)
                    self.tokenInputL.setContentsMargins(0, 0, 0, 0)
                    self.tokenInputL.setSpacing(5)

                    self.tokenInput = QLineEdit()
                    self.tokenInput.setProperty("wid","input")
                    self.tokenInput.setFixedHeight(28)
                    self.tokenInputL.addWidget(self.tokenInput,1)

                    self.tokenSaveBtn = QPushButton()
                    self.tokenSaveBtn.setProperty("wid","btn")
                    self.tokenSaveBtn.setFixedSize(44,28)
                    self.tokenSaveBtn.clicked.connect(self._save_token)
                    self.tokenInputL.addWidget(self.tokenSaveBtn,0)

                    self.tokenCancelBtn = QPushButton()
                    self.tokenCancelBtn.setProperty("wid","btn")
                    self.tokenCancelBtn.setFixedSize(54,28)
                    self.tokenCancelBtn.clicked.connect(self._cancel_edit)
                    self.tokenCancelBtn.setVisible(False)
                    self.tokenInputL.addWidget(self.tokenCancelBtn,0)

                    self.tokenStack.addWidget(self.tokenInputW)

                    self.tokenDisplayW = QWidget()
                    self.tokenDisplayL = QHBoxLayout(self.tokenDisplayW)
                    self.tokenDisplayL.setContentsMargins(0, 0, 0, 0)
                    self.tokenDisplayL.setSpacing(5)

                    self.tokenMaskedLabel = QLabel()
                    self.tokenMaskedLabel.setProperty("wid","title")
                    self.tokenMaskedLabel.setStyleSheet("font-size: 12px;")
                    self.tokenMaskedLabel.setFixedHeight(28)
                    self.tokenDisplayL.addWidget(self.tokenMaskedLabel,1)

                    self.tokenEditBtn = QPushButton()
                    self.tokenEditBtn.setProperty("wid","btn")
                    self.tokenEditBtn.setFixedSize(60,28)
                    self.tokenEditBtn.clicked.connect(self._start_edit)
                    self.tokenDisplayL.addWidget(self.tokenEditBtn,0)

                    self.tokenClearBtn = QPushButton()
                    self.tokenClearBtn.setProperty("wid","btn")
                    self.tokenClearBtn.setFixedSize(60,28)
                    self.tokenClearBtn.clicked.connect(self._clear_token)
                    self.tokenDisplayL.addWidget(self.tokenClearBtn,0)

                    self.tokenStack.addWidget(self.tokenDisplayW)

                    self.tokenMsg = QLabel()
                    self.tokenMsg.setProperty("wid","title")
                    self.tokenMsg.setStyleSheet("font-size: 10px;")
                    self.tokenMsg.setFixedHeight(14)
                    self.layout.addWidget(self.tokenMsg,0)

                    self.tokenTestBtnW = QWidget()
                    self.tokenTestBtnL = QHBoxLayout(self.tokenTestBtnW)
                    self.tokenTestBtnL.setContentsMargins(0, 0, 0, 0)
                    self.tokenTestBtnL.setSpacing(5)

                    self.tokenTestBtn = QPushButton()
                    self.tokenTestBtn.setProperty("wid","btn")
                    self.tokenTestBtn.setFixedSize(90,26)
                    self.tokenTestBtn.clicked.connect(self._test_token)
                    self.tokenTestBtnL.addWidget(self.tokenTestBtn,0)

                    self.tokenLatencyBtn = QPushButton()
                    self.tokenLatencyBtn.setProperty("wid","btn")
                    self.tokenLatencyBtn.setFixedSize(90,26)
                    self.tokenLatencyBtn.clicked.connect(self._test_latency)
                    self.tokenTestBtnL.addWidget(self.tokenLatencyBtn,0)

                    self.tokenTestBtnL.addStretch(1)
                    self.layout.addWidget(self.tokenTestBtnW,0)

                    self.layout.addSpacing(8)

                    self.rateTitle = QLabel()
                    self.rateTitle.setProperty("wid","text")
                    self.rateTitle.setStyleSheet("font-size: 13px;font-weight:bold;")
                    self.rateTitle.setFixedHeight(18)
                    self.layout.addWidget(self.rateTitle,0)

                    self.rateCoreW = QWidget()
                    self.rateCoreL = QHBoxLayout(self.rateCoreW)
                    self.rateCoreL.setContentsMargins(0, 0, 0, 0)
                    self.rateCoreL.setSpacing(10)

                    self.rateCoreLabel = QLabel()
                    self.rateCoreLabel.setProperty("wid","text")
                    self.rateCoreLabel.setStyleSheet("font-size: 11px;")
                    self.rateCoreLabel.setFixedHeight(16)
                    self.rateCoreL.addWidget(self.rateCoreLabel,0)

                    self.rateCoreValue = QLabel()
                    self.rateCoreValue.setProperty("wid","title")
                    self.rateCoreValue.setStyleSheet("font-size: 11px;")
                    self.rateCoreValue.setFixedHeight(16)
                    self.rateCoreL.addWidget(self.rateCoreValue,1)

                    self.layout.addWidget(self.rateCoreW,0)

                    self.rateSearchW = QWidget()
                    self.rateSearchL = QHBoxLayout(self.rateSearchW)
                    self.rateSearchL.setContentsMargins(0, 0, 0, 0)
                    self.rateSearchL.setSpacing(10)

                    self.rateSearchLabel = QLabel()
                    self.rateSearchLabel.setProperty("wid","text")
                    self.rateSearchLabel.setStyleSheet("font-size: 11px;")
                    self.rateSearchLabel.setFixedHeight(16)
                    self.rateSearchL.addWidget(self.rateSearchLabel,0)

                    self.rateSearchValue = QLabel()
                    self.rateSearchValue.setProperty("wid","title")
                    self.rateSearchValue.setStyleSheet("font-size: 11px;")
                    self.rateSearchValue.setFixedHeight(16)
                    self.rateSearchL.addWidget(self.rateSearchValue,1)

                    self.layout.addWidget(self.rateSearchW,0)

                    self.layout.addStretch(1)

                def langing(self):
                    self.tokenTipsIcon.setPixmap(change_color(getPath(ACT_TIPS), QColor(255, 165, 0)).pixmap(QSize(18, 18)))
                    self.tokenTipsText.setText(events.lang.get("core.github.settings.tokenTips"))
                    self.tokenTitle.setText(events.lang.get("core.github.settings.tokenTitle"))
                    self.tokenSaveBtn.setText(events.lang.get("core.text.save"))
                    self.tokenCancelBtn.setText(events.lang.get("core.text.cancel"))
                    self.tokenEditBtn.setText(events.lang.get("core.text.edit"))
                    self.tokenClearBtn.setText(events.lang.get("core.text.clear"))
                    self.tokenTestBtn.setText(events.lang.get("core.github.settings.testToken"))
                    self.tokenLatencyBtn.setText(events.lang.get("core.github.settings.testLatency"))
                    self.rateTitle.setText(events.lang.get("core.github.settings.rateTitle"))
                    self.rateCoreLabel.setText(events.lang.get("core.github.settings.rateCore"))
                    self.rateSearchLabel.setText(events.lang.get("core.github.settings.rateSearch"))
                    self._refresh_ui()

                def showEvent(self, event):
                    super().showEvent(event)
                    self._refresh_ui()

                def _refresh_ui(self):
                    token = events.settings["github"]["token_enc"]
                    self._update_user_section()
                    self._update_token_section(token)
                    self._update_rate_section()

                def _update_user_section(self):
                    user = events.settings["github"]["user"]
                    name = user.get("name") if user else None
                    headurl = user.get("headurl") if user else None

                    if name:
                        self.userName.setText(name)
                        self.tokenStatus.setText(events.lang.get("core.github.settings.tokenStatus.valid"))
                        if headurl:
                            self._load_avatar(headurl)
                        else:
                            self.headIcon.clear()
                    elif events.settings["github"]["token_enc"] and events.settings["github"]["useful"] is False:
                        self.userName.setText(events.lang.get("core.github.settings.notLoggedIn"))
                        self.tokenStatus.setText(events.lang.get("core.github.settings.tokenStatus.invalid"))
                        self.headIcon.clear()
                    elif events.settings["github"]["token_enc"]:
                        self.userName.setText(events.lang.get("core.text.loading"))
                        self.tokenStatus.setText("")
                        self.headIcon.clear()
                    else:
                        self.userName.setText(events.lang.get("core.github.settings.notLoggedIn"))
                        self.tokenStatus.setText(events.lang.get("core.github.settings.tokenStatus.none"))
                        self.headIcon.clear()

                def _load_avatar(self, url):
                    def _fetch():
                        # 复用 githubAPI 的 session：走系统代理 + 合并 CA bundle
                        # （裸 requests.get 无法访问 avatars.githubusercontent.com）
                        try:
                            session = events.githubAPI
                            sess = getattr(session, "_session", None)
                            if sess is not None:
                                resp = sess.get(url, timeout=10)
                            else:
                                import requests as _req
                                resp = _req.get(url, timeout=10)
                            if resp.status_code == 200:
                                return resp.content
                        except Exception:
                            pass
                        return None
                    def _set_round(data):
                        # 主线程创建 QPixmap（QPixmap 是 GUI 类，禁止在子线程创建）
                        if not data:
                            return
                        pix = QPixmap()
                        if not pix.loadFromData(data):
                            return
                        scaled = pix.scaled(78, 78, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        round_pix = QPixmap(78, 78)
                        round_pix.fill(Qt.transparent)
                        painter = QPainter(round_pix)
                        painter.setRenderHint(QPainter.Antialiasing)
                        path = QPainterPath()
                        path.addEllipse(0, 0, 78, 78)
                        painter.setClipPath(path)
                        offset_x = (78 - scaled.width()) // 2
                        offset_y = (78 - scaled.height()) // 2
                        painter.drawPixmap(offset_x, offset_y, scaled)
                        painter.end()
                        self.headIcon.setPixmap(round_pix)
                    QThTimer.task(0, lambda e,_url=url: _fetch(), result_callback=_set_round, dedicated=True)

                def _update_token_section(self, token):
                    if self._editing:
                        return
                    if token:
                        self.tokenStack.setCurrentIndex(1)
                        masked = events.githubAPI.getMaskedToken()
                        self.tokenMaskedLabel.setText(masked if masked else "****")
                        self.tokenMsg.setText("")
                    else:
                        self.tokenStack.setCurrentIndex(0)
                        self.tokenInput.clear()
                        self.tokenMsg.setText("")

                def _update_rate_section(self):
                    rate = events.githubAPI.rate
                    core = rate.get("core", {})
                    search = rate.get("search", {})

                    core_rem = core.get("remaining")
                    search_rem = search.get("remaining")
                    core_reset = core.get("reset", [])
                    search_reset = search.get("reset", [])

                    if core_rem is not None:
                        self.coreBadge.setText(f"Core: {core_rem}")
                        self.coreBadge.setVisible(True)
                        reset_str = ""
                        if len(core_reset) == 6:
                            reset_str = f"{core_reset[0]}-{core_reset[1]:02d}-{core_reset[2]:02d} {core_reset[3]:02d}:{core_reset[4]:02d}:{core_reset[5]:02d}"
                        self.rateCoreValue.setText(
                            f"{events.lang.get('core.github.settings.rateRemaining')}: {core_rem}   "
                            f"{events.lang.get('core.github.settings.rateReset')}: {reset_str}"
                        )
                    else:
                        self.coreBadge.setVisible(False)
                        self.rateCoreValue.setText("")

                    if search_rem is not None:
                        self.searchBadge.setText(f"Search: {search_rem}")
                        self.searchBadge.setVisible(True)
                        reset_str = ""
                        if len(search_reset) == 6:
                            reset_str = f"{search_reset[0]}-{search_reset[1]:02d}-{search_reset[2]:02d} {search_reset[3]:02d}:{search_reset[4]:02d}:{search_reset[5]:02d}"
                        self.rateSearchValue.setText(
                            f"{events.lang.get('core.github.settings.rateRemaining')}: {search_rem}   "
                            f"{events.lang.get('core.github.settings.rateReset')}: {reset_str}"
                        )
                    else:
                        self.searchBadge.setVisible(False)
                        self.rateSearchValue.setText("")

                def _start_edit(self):
                    self._editing = True
                    self.tokenStack.setCurrentIndex(0)
                    self.tokenCancelBtn.setVisible(True)
                    self.tokenInput.clear()

                def _cancel_edit(self):
                    self._editing = False
                    token = events.settings["github"]["token_enc"]
                    if token:
                        self.tokenStack.setCurrentIndex(1)
                    self.tokenInput.clear()

                def _save_token(self):
                    new_token = self.tokenInput.text().strip()
                    if not new_token:
                        self.tokenMsg.setText(events.lang.get("core.github.settings.tokenEmpty"))
                        return

                    events.githubAPI.setToken(new_token)
                    githubAPI.store_token(events.settings, new_token)
                    new_token = None

                    self.tokenSaveBtn.setEnabled(False)
                    self.tokenMsg.setText(events.lang.get("core.github.settings.tokenChecking"))

                    def _on_checked(result):
                        ok, error_type, data = result
                        self.tokenSaveBtn.setEnabled(True)
                        if ok:
                            sync_rate_from_api()
                            events.settings["github"]["useful"] = True
                            events.saveSettings()
                            self._editing = False
                            self._refresh_ui()
                            self._fetch_user()
                            # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                            self.tokenMsg.setText(events.lang.get("core.github.settings.tokenStatus.valid"))
                        elif error_type == "auth":
                            events.settings["github"]["useful"] = False
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.tokenStatus.invalid')}: {data}"
                            )
                        elif error_type == "network":
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.latencyConnError')}: {data}"
                            )
                        else:
                            self.tokenMsg.setText(f"{events.lang.get('core.github.settings.tokenStatus.invalid')}: {data}")

                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.checkToken(),
                        result_callback=_on_checked,
                        dedicated=True
                    )

                def _clear_token(self):
                    clear_token_data()
                    events.saveSettings()
                    self._editing = False
                    self._refresh_ui()

                def _test_token(self):
                    if not events.settings["github"]["token_enc"]:
                        self.tokenMsg.setText(events.lang.get("core.github.settings.tokenEmpty"))
                        return
                    self.tokenTestBtn.setEnabled(False)
                    self.tokenMsg.setText(events.lang.get("core.github.settings.tokenChecking"))
                    def _done(result):
                        self.tokenTestBtn.setEnabled(True)
                        ok, error_type, data = result
                        if ok:
                            sync_rate_from_api()
                            events.settings["github"]["useful"] = True
                            self._refresh_ui()
                            # 最后设置，避免被 _refresh_ui 清空（tokenMsg 会随验证结果显性显示）
                            self.tokenMsg.setText(events.lang.get("core.github.settings.tokenStatus.valid"))
                        elif error_type == "auth":
                            # 仅明确的认证失败才清除 token
                            clear_token_data()
                            events.saveSettings()
                            self._refresh_ui()
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.tokenStatus.invalid')}: {data}"
                            )
                        elif error_type == "network":
                            # 网络不通，保留 token
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.latencyConnError')}: {data}"
                            )
                        else:
                            self.tokenMsg.setText(f"{events.lang.get('core.github.settings.tokenStatus.invalid')}: {data}")
                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.checkToken(),
                        result_callback=_done,
                        dedicated=True
                    )

                def _test_latency(self):
                    if not events.settings["github"]["token_enc"]:
                        self.tokenMsg.setText(events.lang.get("core.github.settings.tokenEmpty"))
                        return
                    self.tokenLatencyBtn.setEnabled(False)
                    self.tokenMsg.setText(events.lang.get("core.github.settings.latencyChecking"))
                    def _done(latency):
                        self.tokenLatencyBtn.setEnabled(True)
                        if latency > 0:
                            self.tokenMsg.setText(
                                events.lang.get("core.github.settings.latencyResult").replace("$1", str(latency))
                            )
                        elif latency == -2:
                            self.tokenMsg.setText(events.lang.get("core.github.settings.latencyTimeout"))
                        elif latency == -3:
                            self.tokenMsg.setText(events.lang.get("core.github.settings.latencyConnError"))
                        elif latency == -4:
                            self.tokenMsg.setText("SSL 连接错误")
                        else:
                            self.tokenMsg.setText(
                                events.lang.get("core.github.settings.latencyError").replace("$1", str(latency))
                            )
                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.checkConnection(),
                        result_callback=_done,
                        dedicated=True
                    )

                def _fetch_user(self):
                    def _on_user(result):
                        ok, data = result
                        if ok:
                            body = data.get("body", {})
                            events.settings["github"]["user"] = {
                                "name": body.get("login"),
                                "headurl": body.get("avatar_url")
                            }
                            events.saveSettings()
                            self._refresh_ui()
                        else:
                            # 获取用户信息失败，但不影响 token 有效性
                            events.settings["github"]["user"] = {"name": None, "headurl": None}
                            self._refresh_ui()
                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.getUser(),
                        result_callback=_on_user,
                        dedicated=True
                    )


def register():
    """把 GitHub 设置页交给 core.overlays。由 pages/builtin.py 调用一次。

    标题是品牌名（各语言都不译），所以直接写字面量 —— 跟面板自己那个
    QLabel("GitHub") 一个口径。
    """
    registry.add("core.overlays", "core.githubSetting",
                 init=lambda b: GithubSetting(b.parent),
                 order=20, title="GitHub", layer="overlay")
