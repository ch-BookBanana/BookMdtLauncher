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

GitHub 设置浮层：登录/退出、账号信息、rate 余量、延迟测试。

登录方式换成了 GitHub App 授权（OAuth 授权码 + PKCE + 本地回环，见
api/githubAuth.py）：用户点一下「登录 GitHub」，浏览器里点授权，凭据由回环
端口带回启动器。这里没有、也不该有「粘贴 token」的输入框 —— 手输长期凭据
既有泄漏风险，又会让用户在权限上做没必要的取舍。

需要用户在 GitHub App 后台配的两件事写在面板顶部的提示条里
（Authorization callback URL = http://127.0.0.1，端口任意；client_id 填进
BML/githubApp.json）。

原先长在 main.py 里（Window.GithubSetting，约 690 行），由 Window 在启动时
**建好并一直攥着**，打开它的按钮直接点 Window 的方法 —— 窗口因此认识这个类，
面板也永远只有那一个实例（改完配置关掉再开，看到的还是旧状态）。
现在按浮层扩展点登记（core.overlays），谁要打开就从注册表取条目现建。

面板尺寸 520x365：它是浮在窗口上的小卡片，跟设置页那条 600px 正文列不是一个口径。
"""

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from shiboken6 import isValid

from ...bus import bus
from ...events import events
from ...options.scrolls import Scroll
from ...path_utils import getPath
from ...qthtimer import QThTimer
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


def fmt_expires(expires_at):
    """把 epoch 秒换成本地时间的「YYYY-MM-DD HH:MM」；没有到期时间返回空串。

    access token 只有 8 小时，面板上必须让人一眼看到「到什么时候为止」——
    否则「昨天还能搜，今天要重登」看起来就像凭空掉线。
    只在打开面板与每次请求失败后刷新显示，不做秒级倒计时：那需要一个常驻
    定时器，而这块信息一分钟内也不会变。
    """
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(expires_at)))
    except (TypeError, ValueError, OSError):
        return ""


def clear_token_data():
    """退出登录：授权包（内存 + settings）与上一个账号的 rate/用户信息一起清掉。

    只在两种时候调：用户自己点「退出登录」，或 token 被 GitHub 明确判为
    无效（401/403）。网络不通时要保留 token —— 那不是凭据的问题。
    """
    events.githubAPI.logout(events.settings)
    s = events.settings["github"]
    s["rate"]["core"] = {"remaining": None, "reset": []}
    s["rate"]["search"] = {"remaining": None, "reset": []}


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

        顺手取消还在等浏览器的那次授权：面板都关了，用户不会再看到结果，
        监听端口没有理由继续开着等满三分钟。
        """
        try:
            events.githubAPI.cancel_authorize()
        except Exception:
            pass
        events.emit("overlayClosed", self, True)

    class Panel(QWidget):
        def __init__(self, parent=None):
            super().__init__()
            self.parent = parent
            self.githubAPI = events.githubAPI
            self.init_ui()
            self.init_wid()
            self.githubAPI.refreshed.connect(self._on_rate_refreshed)
            self.githubAPI.authChanged.connect(self.body.content._on_auth_changed)
            self.githubAPI.authExpired.connect(self.body.content._on_auth_expired)


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
                    super().__init__(parent, margins=(20, 20, 20, 20), spacing=10)
                    self.parent = parent
                    self._authing = False
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

                    self.tokenStack = QStackedWidget()
                    self.tokenStack.setFixedHeight(32)
                    self.layout.addWidget(self.tokenStack,0)

                    self.loginW = QWidget()
                    self.loginL = QHBoxLayout(self.loginW)
                    self.loginL.setContentsMargins(0, 0, 0, 0)
                    self.loginL.setSpacing(5)

                    self.loginBtn = QPushButton()
                    self.loginBtn.setProperty("wid","btn")
                    self.loginBtn.setFixedSize(110,28)
                    self.loginBtn.clicked.connect(self._login)
                    self.loginL.addWidget(self.loginBtn,0)

                    self.loginL.addStretch(1)
                    self.tokenStack.addWidget(self.loginW)

                    self.tokenDisplayW = QWidget()
                    self.tokenDisplayL = QHBoxLayout(self.tokenDisplayW)
                    self.tokenDisplayL.setContentsMargins(0, 0, 0, 0)
                    self.tokenDisplayL.setSpacing(5)

                    self.logoutBtn = QPushButton()
                    self.logoutBtn.setProperty("wid","btn")
                    self.logoutBtn.setFixedSize(110,28)
                    self.logoutBtn.clicked.connect(self._logout)
                    self.tokenDisplayL.addWidget(self.logoutBtn,0)
                    self.tokenDisplayL.addStretch(1)

                    self.tokenStack.addWidget(self.tokenDisplayW)

                    self.expiresLabel = QLabel()
                    self.expiresLabel.setProperty("wid","title")
                    self.expiresLabel.setStyleSheet("font-size: 11px;")
                    self.expiresLabel.setFixedHeight(18)
                    self.layout.addWidget(self.expiresLabel,0)

                    self.tokenMsg = QLabel()
                    self.tokenMsg.setProperty("wid","title")
                    self.tokenMsg.setStyleSheet("font-size: 10px;")
                    self.tokenMsg.setFixedHeight(30)
                    self.tokenMsg.setWordWrap(True)
                    self.layout.addWidget(self.tokenMsg,0)

                    self.tokenTestBtnW = QWidget()
                    self.tokenTestBtnL = QHBoxLayout(self.tokenTestBtnW)
                    self.tokenTestBtnL.setContentsMargins(0, 0, 0, 0)
                    self.tokenTestBtnL.setSpacing(5)

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
                    self.loginBtn.setText(events.lang.get("core.github.settings.login"))
                    self.logoutBtn.setText(events.lang.get("core.github.settings.logout"))
                    self.tokenLatencyBtn.setText(events.lang.get("core.github.settings.testLatency"))
                    self.rateTitle.setText(events.lang.get("core.github.settings.rateTitle"))
                    self.rateCoreLabel.setText(events.lang.get("core.github.settings.rateCore"))
                    self.rateSearchLabel.setText(events.lang.get("core.github.settings.rateSearch"))
                    self._refresh_ui()

                def showEvent(self, event):
                    super().showEvent(event)
                    self._refresh_ui()

                def _refresh_ui(self):
                    self._update_user_section()
                    self._update_token_section()
                    self._update_rate_section()

                def _update_user_section(self):
                    user = events.settings["github"]["user"]
                    name = user.get("name") if user else None
                    headurl = user.get("headurl") if user else None

                    if name:
                        self.userName.setText(name)
                        self.tokenStatus.setText(
                            events.lang.get("core.github.settings.loggedInAs").replace("$1", name))
                        if headurl:
                            self._load_avatar(headurl)
                        else:
                            self.headIcon.clear()
                    elif events.githubAPI.hasToken() and events.settings["github"]["useful"] is False:
                        self.userName.setText(events.lang.get("core.github.settings.notLoggedIn"))
                        self.tokenStatus.setText(events.lang.get("core.github.settings.tokenStatus.invalid"))
                        self.headIcon.clear()
                    elif events.githubAPI.hasToken():
                        self.userName.setText(events.lang.get("core.text.loading"))
                        self.tokenStatus.setText("")
                        self.headIcon.clear()
                    else:
                        self.userName.setText(events.lang.get("core.github.settings.notLoggedIn"))
                        self.tokenStatus.setText(events.lang.get("core.github.settings.tokenStatus.none"))
                        self.headIcon.clear()

                def _load_avatar(self, url):
                    def _fetch():
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
                        if not isValid(self.headIcon):
                            return
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

                def _update_token_section(self):
                    if events.githubAPI.hasToken():
                        self.tokenStack.setCurrentIndex(1)
                        self.tokenMsg.setText("")
                        when = fmt_expires(events.githubAPI.authExpiresAt())
                        self.expiresLabel.setText(
                            events.lang.get("core.github.settings.tokenExpires").replace("$1", when)
                            if when else "")
                    else:
                        self.tokenStack.setCurrentIndex(0)
                        self.tokenMsg.setText("")
                        self.expiresLabel.setText("")

                def _on_auth_changed(self):
                    """授权包变了（续期成功 / 被清空）：只重画，不写提示行。

                    续期发生在后台（可能是用户根本没打开面板的时候），这里
                    不用弹任何东西 —— 但到期时间必须跟着变，否则面板还挂着
                    上一块 access 的时间。
                    """
                    if not isValid(self.tokenMsg):
                        return
                    self._refresh_ui()

                def _on_auth_expired(self):
                    """凭据被判死：切回未登录页 + 提示重新登录，按钮恢复可点。

                    authExpired 会在任意一次请求里触发（不一定是面板里的操作），
                    所以这里要把「正在等待授权」也一起复位 —— 否则按钮会一直
                    停在禁用态，用户连重登都点不了。
                    """
                    if not isValid(self.tokenMsg):
                        return
                    self._authing = False
                    self.loginBtn.setEnabled(True)
                    self._refresh_ui()
                    # 放在 _refresh_ui 之后：那一步会把提示行清空
                    self.tokenMsg.setText(
                        events.lang.get("core.github.settings.authExpired"))

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

                def _login(self):
                    """点「登录 GitHub」：开浏览器授权，回来刷新面板。

                    authorize() 要一直阻塞到用户在浏览器里点完（最多三分钟），
                    所以整段丢给后台线程；主线程只负责把「正在等待」画出来。
                    """
                    if self._authing:
                        return
                    self._authing = True
                    self.loginBtn.setEnabled(False)
                    self.tokenMsg.setText(events.lang.get("core.github.settings.authWaiting"))

                    def _done(result):
                        # 面板可能在等待期间被关掉（控件已 deleteLater）：先确认它还活着
                        if not isValid(self.loginBtn):
                            return
                        self._authing = False
                        self.loginBtn.setEnabled(True)
                        ok, message, _blob = (result if isinstance(result, tuple)
                                              and len(result) == 3
                                              else (False, "授权流程返回了意外的结果", None))
                        if not ok:
                            self.tokenMsg.setText(
                                events.lang.get("core.github.settings.authFailed")
                                .replace("$1", str(message)))
                            return
                        self._check_after_login()

                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.authorize(events.settings),
                        result_callback=_done,
                        dedicated=True
                    )

                def _check_after_login(self):
                    """登录后补一次 checkToken（拿余量）再取用户信息（头像/用户名）。"""
                    def _on_checked(result):
                        ok, error_type, data = result
                        if ok:
                            sync_rate_from_api()
                            events.settings["github"]["useful"] = True
                            events.saveSettings()
                        elif error_type == "auth":
                            clear_token_data()
                            events.saveSettings()

                        if not isValid(self.tokenMsg):
                            return
                        self._refresh_ui()
                        if ok:
                            self._fetch_user()
                            # 放在 _refresh_ui 之后：那一步会把提示行清空
                            self.tokenMsg.setText(events.lang.get("core.github.settings.authSuccess"))
                        elif error_type == "network":
                            # 网络不通不代表凭据有问题 —— 保留登录状态
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.latencyConnError')}: {data}")
                        elif error_type == "auth":
                            self.tokenMsg.setText(
                                events.lang.get("core.github.settings.authExpired"))
                        else:
                            self.tokenMsg.setText(
                                f"{events.lang.get('core.github.settings.tokenStatus.invalid')}: {data}")

                    QThTimer.task(
                        0,
                        lambda e: events.githubAPI.checkToken(),
                        result_callback=_on_checked,
                        dedicated=True
                    )

                def _logout(self):
                    """退出登录：清 token（含 settings 落盘），面板回到未登录态。"""
                    clear_token_data()
                    events.saveSettings()
                    self._authing = False
                    self._refresh_ui()

                def _test_latency(self):
                    # 延迟测试跟登录无关：没登录也能测到 GitHub 的网络延迟
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
                        else:
                            # 获取用户信息失败，但不影响 token 有效性
                            events.settings["github"]["user"] = {"name": None, "headurl": None}
                        if not isValid(self.tokenMsg):
                            return
                        self._refresh_ui()
                        if ok:
                            self.tokenMsg.setText(events.lang.get("core.github.settings.authSuccess"))
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
                 init=lambda b: GithubSetting(b.parent), title="GitHub")
