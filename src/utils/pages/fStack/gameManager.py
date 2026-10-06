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

游戏管理浮层：容器 GameManager + 它的功能页（当前只有「设置」这一页）。

GameManager 是纯容器：左栏功能菜单从 core.gameManager.pages 读，右栏装页面，
它不认识任何一个具体页。形态和设置页一样（左栏选、右栏看），区别只在于
它活在浮层里、对象是某一个游戏实例。

    左栏（core.gameManager.pages）        右栏
    ├── 设置  → GameSettings（文件夹 / Java / 改名 / 删除…）
    └── …     将来加 Mods、存档之类

加一页 = 写一个模块 + 在自己的 register() 里加一条 registry.add，本文件一行
都不用动。容器入口也由本文件的 register() 交给 core.overlays。
"""

import os

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from ...bus import bus
from ...events import events
from ...javaManager import javaManager
from ...mdtManager import mdtManager
from ...options.items import Bool, Combo
from ...options.navBtn import NavBtn
from ...options.scrolls import Scroll
from ...path_utils import getPath
from ...registry import Box, registry
from ...resources import FILE_FOLDER, TBT_CLOSE
from ...utils import change_color, openFolder, t


class GameManager(QWidget):
    """**指定实例**的游戏管理浮层。

    管哪个实例由打开的人给（见 register 里的 b.game），这里不摸全局默认值：
    摸全局的话这个浮层就只能管默认那一个，想给别的实例开管理没处表达，
    而且「为什么管的是它」会藏进构造函数里 —— 出事时只看得到一个 None。
    """

    def __init__(self, game, parent=None):
        super().__init__()
        self.parent = parent
        self.game = game
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.init_wid()

    def init_wid(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 左栏：功能菜单。外观与设置页左栏是同一套 —— 同一个 NavBtn、同一个
        # Scroll、同样用 QButtonGroup 管互斥，所以两边看起来就是一套东西。
        self.left = QWidget()
        self.left.setFixedWidth(NavBtn.WIDTH)
        self.left.setAttribute(Qt.WA_StyledBackground, True)
        self.left_layout = QVBoxLayout(self.left)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)

        self.scroll = Scroll(self.left)
        self.left_layout.addWidget(self.scroll)
        self.group = QButtonGroup(self)

        self.line = QWidget()
        self.line.setProperty("wid", "line")
        self.line.setFixedWidth(1)
        self.line.setAttribute(Qt.WA_StyledBackground, True)

        # 右栏：各功能页
        self.pages = QStackedWidget()

        self.layout.addWidget(self.left, 0)
        self.layout.addWidget(self.line, 0)
        self.layout.addWidget(self.pages, 1)

        self._build_pages()

    def _build_pages(self):
        """按 core.gameManager.pages 构建左栏与右栏。

        子页的 init 由各自提供（注册方知道怎么造），这里只备一个 parent
        （就是本浮层，子页要用 self.game 时从 b.parent.game 现取）。
        """
        self.btns = []
        for e in registry.entries("core.gameManager.pages"):
            wid = e.init(Box(parent=self, entry=e))
            self.pages.addWidget(wid)

            # text 传语言键：NavBtn 的 langing 在语言切换时自己重取
            btn = NavBtn(e.title, e.get("icon"), self.left)
            self.scroll.add(btn)
            self.group.addButton(btn)
            btn.clicked.connect(lambda _checked=False, w=wid: self.pages.setCurrentWidget(w))
            self.btns.append(btn)

        if self.btns:
            self.btns[0].click()


def group_of(settings, game):
    """game 登记在 settings["gameList"] 的哪个分组下；没登记（含 game 为空）返回 ""。

    分组只在 settings 里记着（键 = 分组名，值 = 该组的实例名），实例自己的
    BML.json 与 mdt.jar 里都没有归属信息，所以要显示归属只能反查这张表。
    """
    if not game:
        return ""
    for name, games in settings["gameList"].items():
        if game in games:
            return name
    return ""


class _ElideLabel(QLabel):
    """定宽省略标签：正文按控件当前宽度右侧省略，宽度/字体变化时重算。

    QLabel 自己不会省略——要么把字硬切掉半截，要么反过来把整行布局撑宽。
    实例名上限 32 字，22px 字号下足够顶穿顶部这一行，所以在这里收口。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        # 水平方向忽略自身 sizeHint：否则长文本会先把布局撑出去，省略就无从谈起
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        self._text = str(text)
        self._apply()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def changeEvent(self, event):
        # 字体变化（宽高比/字体由 qss 定，样式生效晚于首次 setText）后要重算一次
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._apply()

    def _apply(self):
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._text, Qt.ElideRight, self.width()))


class GameSettings(Scroll):
    """游戏管理页：整页就是那层滚动区（顶部信息在内），管理项直接挂在 self.scroll_layout 上。

    页面本身铺满，内容列收在 MAX_WIDTH 里居中，跟设置页那条 600px 的正文列对齐。
    """

    MAX_WIDTH = 600     # 内容列最大宽度，与设置页 Page 的 max-width 一致

    def __init__(self, game, parent=None):
        # 上下留 10：和设置页正文那条一致（那边是外层 layout 给的 0,10,0,10；
        # 这一页整页就是滚动区，所以 10 落在 Scroll 自己的边距上）
        super().__init__(parent, margins=(30, 10, 30, 10), spacing=0,
                         content_align=Qt.AlignHCenter)
        self.main.setMaximumWidth(self.MAX_WIDTH)
        self.parent = parent
        self.game = game
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.init_wid()

    def init_wid(self):
        self.top = self.Top(self)
        self.scroll_layout.addWidget(self.top, 0)

        self.line = QWidget()
        self.line.setFixedHeight(1)
        self.line.setProperty("wid", "line")
        self.scroll_layout.addWidget(self.line, 0)

        # 区块从注册表取：加一个区块 = 写一个 QWidget 子类 + 在本文件 register()
        # 里加一条。登记写在这里的话，init_wid 每构建一次就跑一次，
        # 第二次构建会直接撞「已存在条目」。
        for e in registry.entries("core.gameSettings.sections"):
            wid = e.init(Box(parent=self, entry=e))
            setattr(self, e.attr, self.add(wid, e.get("spacing", 0)))

        # 顶部信息填真实数据（图标/名称/分组/版本），并订阅实例事件：
        # 本页后续的管理项都以 self.game 为操作对象，改名时必须跟着换。
        # 启动器状态同理：本页实例一跑起来，顶部那排按钮就得禁掉。
        self.refresh()
        events.mdtManager.on_game_changed.connect(self._on_game_changed)
        events.launcher.game_started.connect(self._sync_running)
        events.launcher.lifecycle_finished.connect(self._sync_running)
        # Java 候选表归 javaManager 扫（子线程 + TTL 缓存）：本页开着时跟着看，
        # 出栈就 unwatch（见 on_close），不常驻扫盘
        javaManager.watch()
        javaManager.changed.connect(self._on_java_changed)

    def _on_java_changed(self, javas):
        """全局 Java 候选表变了（含首次扫完）：重填本页那行选择。"""
        self.java.fill(javas)

    def refresh(self):
        """按当前实例刷新顶部；没指定实例或实例已失效（msg 为 None）时顶部留空。"""
        msg = events.mdtManager.getMdtMsg(self.game) if self.game else None
        self.top.sets(self.game, msg)
        self.folders.set_enabled(bool(msg))     # 实例都没了，也就没目录可开
        self._sync_running()

    def _sync_running(self, *_):
        """实例运行状态同步到按钮：跑的正是本页这个实例才禁用。"""
        self.top.set_running(self.running())

    def running(self):
        """本页实例是否在跑。启动准备（going=1）也算：那时实例锁已经落下。"""
        launcher = events.launcher
        return bool(launcher.going) and launcher.data.get("mdtName") == self.game

    def _on_game_changed(self, data):
        """实例事件：改名时把 self.game 一起换掉（否则后续操作会拿着旧目录名报 notFound）。

        改名归 nameChanged（比对 old_name）、图标/版本归 iconChanged（比对 game）、
        归属归 groupChanged（比对 game），其余事件（新增、删除）与本页无关。
        """
        etype = data["type"]
        if etype == "nameChanged":
            if data["old_name"] != self.game:
                return
            self.game = data["game"]
        elif etype in ("iconChanged", "groupChanged"):
            if data["game"] != self.game:
                return
        elif etype == "deleteGame":
            # 实例被删（本页删的，或目录在外面没了）：本页已无操作对象，直接出栈。
            # 叠在上面的浮层不属于本页（Qt 上没有父子关系），由删除流程自己出叠。
            if data["game"] == self.game:
                events.emit("stackClosed", self, True)
            return
        else:
            return
        self.refresh()

    def on_close(self):
        """出栈（或被清空）时断开订阅：页面随即被销毁，事件不能再打回来。"""
        mdt_signal = events.mdtManager.on_game_changed
        launcher = events.launcher
        for signal, slot in ((mdt_signal, self._on_game_changed),
                             (javaManager.changed, self._on_java_changed),
                             (launcher.game_started, self._sync_running),
                             (launcher.lifecycle_finished, self._sync_running)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        javaManager.unwatch()

    class Folders(QWidget):
        """数据 / 蓝图 / 模组三个文件夹入口：点一下就在文件管理器里打开对应目录。

        路径一律找 mdtManager 要（<实例目录>/data/Mindustry 及其 schematics、mods），
        页面只管显示与转发；实例名在点击时才向页面现取，所以改名后照样指向新目录。
        实例运行期间不禁用：进程只用不锁这几个目录，开着看数据是正常操作。
        """

        # 按钮：i18n 词条 + mdtManager.DATA_FOLDERS 里的类别名
        KINDS = (("core.wid.pages.gameManage.folder.data", "data"),
                 ("core.wid.pages.gameManage.folder.blueprint", "blueprint"),
                 ("core.wid.pages.gameManage.folder.mod", "mod"))

        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent    # 所属页面：实例名从 parent.game 现取
            self.light = None
            self.icon = QIcon()
            self.buttons = []
            self.init_wid()
            self.langing()      # 总线只在切换时广播，首次文案得自己填
            self.lighting(bool(events.settings["theme"]))
            bus.bind(self)

        def init_wid(self):
            self.row = QHBoxLayout(self)
            self.row.setContentsMargins(0, 0, 0, 0)
            self.row.setSpacing(8)
            self.row.setAlignment(Qt.AlignLeft)
            self.row.addSpacing(10)
            for key, kind in self.KINDS:
                button = QPushButton()
                button.setProperty("wid", "btn")
                button.setProperty("lang", key)
                button.setFixedSize(122, 40)
                button.setIconSize(QSize(16, 16))
                button.clicked.connect(lambda _=False, kind=kind: self.open(kind))
                self.row.addWidget(button, 0)
                self.buttons.append(button)

        def open(self, kind):
            """打开本实例的某个数据文件夹；目录不在就建好再打开。"""
            openFolder(mdtManager.getDataFolder(self.parent.game, kind))

        def set_enabled(self, enabled):
            for button in self.buttons:
                button.setEnabled(enabled)

        def langing(self):
            for button in self.buttons:
                button.setText(events.lang.get(button.property("lang")))

        def lighting(self, light):
            """folder.png 是白图，得按主题改色，取色跟着按钮文字走。"""
            if self.light == light:
                return
            self.light = light
            self.icon = change_color(getPath(FILE_FOLDER),
                                     QColor(22, 22, 22) if light else QColor(255, 255, 255))
            for button in self.buttons:
                button.setIcon(self.icon)

    class Top(QWidget):
        """顶部信息区：l1 是图标与实例信息，l2 是操作按钮行。

        按钮只负责摆位置与显示文案，点击行为待定；实例运行期间整行禁用。
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.parent = parent
            self._name = ""     # 当前实例名，语言切换时靠它重查分组
            self.buttons = []
            self.init_ui()
            self.init_wid()
            self.langing()      # 初次文案：总线只在切语言时回调，不会补这一次
            bus.bind(self)

        @property
        def game(self):
            """本页管理的实例名（从 GameSettings 现取，改名后自动跟着换）。"""
            return self.parent.game

        def init_ui(self):
            self.setAttribute(Qt.WA_StyledBackground, True)

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 10)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

            # l1：图标 + 实例信息（名称 / 分组 ･ 版本）
            self.l1 = QHBoxLayout()
            self.l1.setContentsMargins(0, 0, 0, 0)
            self.l1.setSpacing(0)
            self.l1.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.layout.addLayout(self.l1)

            self.icon = QLabel()
            self.icon.setProperty("wid", "png")
            self.icon.setFixedSize(80, 80)
            self.icon.setScaledContents(True)
            self.l1.addWidget(self.icon, 0)

            self.l1.addSpacing(10)

            self.infow = QWidget()
            self.info = QVBoxLayout(self.infow)
            self.info.setContentsMargins(0, 0, 0, 0)
            self.info.setSpacing(0)
            self.l1.addWidget(self.infow, 1)

            self.name = _ElideLabel()
            self.name.setProperty("wid", "text")
            self.name.setFixedHeight(40)
            self.name.setStyleSheet("font-size: 22px;")
            self.info.addWidget(self.name, 0)

            # 版本行：分组 ･ 版本号。分组是这个实例的归属信息，摆在版本号前面；
            # 中间那个点只是分隔符，压成灰色，不跟两边的字抢眼。
            self.versw = QWidget()
            self.versw.setFixedHeight(30)
            self.vers_l = QHBoxLayout(self.versw)
            self.vers_l.setContentsMargins(0, 0, 0, 0)
            self.vers_l.setSpacing(6)
            self.info.addWidget(self.versw, 0)

            self.group = QLabel()
            self.group.setProperty("wid", "text")
            self.group.setStyleSheet("font-size: 16px;")
            self.vers_l.addWidget(self.group, 0)

            self.dot = QLabel("･")
            self.dot.setProperty("wid", "text")
            self.dot.setStyleSheet("font-size: 16px; color: gray;")
            self.vers_l.addWidget(self.dot, 0)

            self.vers = QLabel()
            self.vers.setProperty("wid", "text")
            self.vers.setStyleSheet("font-size: 16px;")
            self.vers_l.addWidget(self.vers, 0)

            self.vers_l.addStretch(1)

            self.layout.addSpacing(10)

            # l2：操作按钮行（并排）。样式沿用左侧栏那套 wid="btn"，
            # 只有删除是危险操作，单独压成红色。文案挂 property，切语言时统一刷。
            self.l2 = QHBoxLayout()
            self.l2.setContentsMargins(0, 8, 0, 0)
            self.l2.setSpacing(8)
            self.l2.setAlignment(Qt.AlignLeft)
            self.layout.addLayout(self.l2)

            self.buttons = [
                self._button("core.wid.pages.gameManage.rename", self.Rename),
                self._button("core.wid.pages.gameManage.group", self.Group),
                self._button("core.wid.pages.gameManage.delete", self.Delete, danger=True),
            ]

        def _button(self, key, page, danger=False):
            """按钮行里的一颗按钮：点击弹出对应的叠加浮层；删除是危险操作，单独压红。

            内容区（表单、确认文字）待定，页面里暂时只有标题栏。
            """
            btn = QPushButton()
            btn.setProperty("wid", "btn")
            btn.setProperty("lang", key)
            btn.setFixedSize(122, 40)
            if danger:
                btn.setStyleSheet("color: rgb(214, 62, 62); border: 1px solid rgb(214, 62, 62);")
            btn.clicked.connect(lambda: self.open_page(page))
            self.l2.addWidget(btn, 0)
            return btn

        def open_page(self, page):
            """把页面实例化后交给叠加浮层：遮罩、居中、叠层都由浮层统一管。"""
            events.emit("overlayRequested", page(self))

        def set_running(self, running):
            """实例运行期间三个按钮全禁：目录被锁，改名/删除必定失败。"""
            for btn in self.buttons:
                btn.setEnabled(not running)

        def sets(self, name, msg):
            """填入实例信息（mdtManager.getMdtMsg 的返回值）；msg 为 None 则全部留空。

            msg 里 icon 是图标文件路径，number/build/modifier 拼出版本号。
            """
            pm = QPixmap(msg["icon"]) if msg else QPixmap()
            if not pm.isNull():
                pm = pm.scaled(self.icon.width(), self.icon.height(),
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            vers = "v%s.%s%s" % (msg["number"], msg["build"], msg["modifier"]) if msg else ""
            self.icon.setPixmap(pm)
            self.name.setText(name or "")
            self.vers.setText(vers)
            self._name = name or ""
            self._sync_group()
            self.icon.setToolTip("\n".join(x for x in (name, vers) if x))

        def _sync_group(self):
            """把分组名落到版本号前面；没有归属（实例无效/没登记）连分隔点一起藏掉。

            默认分组在表里是个符号键，显示前过一遍 i18n，所以语言切换也要重刷这里。
            """
            group = group_of(events.settings, self._name)
            if group == mdtManager.DEFAULT_GROUP:
                group = events.lang.get("core.text.default")
            self.group.setText(group)
            self.group.setVisible(bool(group))
            self.dot.setVisible(bool(group))

        def langing(self):
            self._sync_group()
            for btn in self.buttons:
                btn.setText(events.lang.get(btn.property("lang")))

        class Page(QWidget):
            """按钮弹层的公共底板：标题栏（标题 + ×）+ 分割线 + 内容区。

            遮罩与居中由叠加浮层（FloatingOverlay）提供，这里只画面板。
            内容区交给 init_body()，子类现在只定自己的标题与尺寸。
            """

            WIDTH = 320
            HEIGHT = 190
            TITLE_KEY = ""
            # 确定按钮的两套配色：可用=实心黄，禁用=半透明黄（与下载页确定按钮同源）
            BTN_ON = "background-color: #f0b731; border: none;"
            BTN_OFF = "background-color: rgba(240, 183, 49, 100); border: none;"

            def __init__(self, parent=None):
                super().__init__()
                self.parent = parent
                self.setAttribute(Qt.WA_StyledBackground, True)
                self.init_wid()
                self.langing()
                self.lighting(bool(events.settings.get("theme")))
                # 接总线必须在控件建好之后：bus.bind 会立刻补一次 lighting，
                # 那时 btn_close 还不存在，直接炸 AttributeError。
                bus.bind(self)

            def init_wid(self):
                self.setFixedSize(self.WIDTH, self.HEIGHT)
                self.layout = QVBoxLayout(self)
                self.layout.setSpacing(0)
                self.layout.setContentsMargins(0, 0, 0, 0)
                self.layout.setAlignment(Qt.AlignTop)

                self.top = QWidget()
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
                # 这里不能写 setStyleSheet("background: transparent")：
                # 控件级样式表是「整棵子树」的规则，优先级还高于全局 qss，
                # 会把弹层里所有子控件的底色一起压成透明（分组页的 color2 就是这么丢的）。
                # body 与面板同源同色（都吃全局 QWidget 那条），不写也看不出接缝。
                self.layout.addWidget(self.body, 1)
                self.body_l = QVBoxLayout(self.body)
                self.body_l.setContentsMargins(15, 0, 15, 15)
                self.body_l.setSpacing(0)
                self.body_l.setAlignment(Qt.AlignTop)
                self.init_body(self.body_l)

            def init_body(self, layout):
                """内容区：子类往这个布局里塞控件（当前留空）。"""
                pass

            @property
            def game(self):
                """目标实例名：从 Top 现取，改名后自动跟着换，浮层不用自己同步。

                原先写的是 self.parent.parent.game —— 一次跨两层，靠「Top 的 parent
                恰好是 GameSettings」这条隐含前提撑着。现在每层只依赖自己的直接 parent。
                """
                return self.parent.game

            def _set_ok_enabled(self, enabled):
                """确定按钮的可用态与配色一起切（禁用时压成半透明）。"""
                self.btn_ok.setEnabled(enabled)
                self.btn_ok.setStyleSheet(self.BTN_ON if enabled else self.BTN_OFF)

            def langing(self):
                self.title.setText(events.lang.get(self.TITLE_KEY))
                self.btn_close.setToolTip(events.lang.get("core.wid.top.close"))

            def lighting(self, light):
                # 关闭按钮图标随主题取色（面板其余部分交给全局 qss）
                color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
                icon = change_color(TBT_CLOSE, color)
                self.btn_close.setIcon(QIcon(icon.pixmap(24, 24)))

            def _close(self):
                """出叠并销毁（on_close 由浮层在出叠时统一调）。"""
                events.emit("overlayClosed", self, True)

        class Rename(Page):
            """更改名称弹层：输入框 + 校验提示 + 确定。

            规则与下载页命名弹窗同一套：mdtManager.check_name 判字形、
            name_conflict 判占用、unique_name 自动加后缀，连提示词条都复用那几条。
            唯一的差别是重名判定要略过实例自身——改名成自己不算撞名。
            """

            TITLE_KEY = "core.wid.pages.gameManage.rename"

            def init_body(self, layout):
                self._final_name = None

                layout.addStretch(1)

                self.input = QLineEdit()
                self.input.setProperty("wid", "input")
                self.input.setFixedHeight(32)
                self.input.setClearButtonEnabled(True)
                # 名字即目录名，上限与 check_name 同源，超长直接打不进去
                self.input.setMaxLength(mdtManager.MAX_NAME_LEN)
                self.input.setText(self.game)
                self.input.selectAll()      # 打开就是要改名，直接覆盖原名
                layout.addWidget(self.input, 0)

                layout.addStretch(1)

                self.bottom = QWidget()
                self.bottom.setStyleSheet("background: transparent;")
                layout.addWidget(self.bottom, 0)
                self.bottom_l = QHBoxLayout(self.bottom)
                self.bottom_l.setContentsMargins(0, 0, 0, 0)
                self.bottom_l.setSpacing(8)
                self.bottom_l.setAlignment(Qt.AlignVCenter)

                self.tip = QLabel()
                self.tip.setProperty("wid", "text")
                self.tip.setStyleSheet("font-size: 13px;")
                self.tip.setWordWrap(True)
                self.bottom_l.addWidget(self.tip, 1)

                self.btn_ok = QPushButton()
                self.btn_ok.setProperty("wid", "btn")
                self.btn_ok.setFixedSize(80, 30)
                self.btn_ok.clicked.connect(self._on_ok)
                self.bottom_l.addWidget(self.btn_ok, 0)

                # setText 已在前面做过，这里再接变化信号，免得刚建好就白跑一轮
                self.input.textChanged.connect(self._validate)
                self._validate()

            def langing(self):
                super().langing()
                self.btn_ok.setText(events.lang.get("core.text.yes"))
                self._validate()    # 提示与「将改名为」都是译文，得按新语言重算

            def _validate(self, *_):
                """按当前输入重算状态：错误红框 / 重名黄框 + 提示 + 确定可用性。

                最终名落在 self._final_name，None 表示这次输入不可提交。
                重名不直接拒绝：自动加 (1)(2) 后缀后照样能提交，跟下载页一致。
                """
                text = self.input.text().strip()
                langer = events.lang
                final = None
                if not text:
                    state, msg = "empty", ""
                else:
                    error = mdtManager.check_name(text)
                    if error == "dot":
                        state, msg = "dot", langer.get("core.wid.pages.download.item.name.dot")
                    elif error:
                        state, msg = "illegal", langer.get("core.wid.pages.download.item.name.illegal")
                    elif events.mdtManager.name_conflict(text, except_name=self.game):
                        final = events.mdtManager.unique_name(text)
                        state = "dup"
                        msg = t(langer.get("core.wid.pages.download.item.name.willBe"), final)
                    else:
                        state, msg = "ok", ""
                        final = text
                self._final_name = final
                if state in ("illegal", "dot"):
                    self.input.setStyleSheet("border: 1px solid red;")
                    self.tip.setStyleSheet("font-size: 13px; color: red;")
                    self._set_ok_enabled(False)
                elif state == "dup":
                    self.input.setStyleSheet("border: 1px solid yellow;")
                    self.tip.setStyleSheet("font-size: 13px; color: yellow;")
                    self._set_ok_enabled(True)
                else:
                    self.input.setStyleSheet("")
                    self.tip.setStyleSheet("font-size: 13px;")
                    self._set_ok_enabled(state == "ok")
                self.tip.setText(msg)

            def _on_ok(self):
                """提交改名：字形/占用/锁全在 mdtManager.Editor.rename 里判。

                成功后本页出叠；GameSettings 收到 nameChanged 会把实例名连同顶部
                信息一起换掉，浮层这边无需再同步。
                """
                if not self._final_name:
                    return
                editor = events.mdtManager.edit(self.game)
                editor.rename(self._final_name)
                if not editor.ok:
                    # notFound / locked / ioError：实例没了或正被系统锁着，
                    # 退回校验态已无意义，直接把失败摆在下边
                    self._final_name = None
                    self.input.setStyleSheet("border: 1px solid red;")
                    self.tip.setStyleSheet("font-size: 13px; color: red;")
                    self.tip.setText(events.lang.get("core.wid.pages.gameManage.failed"))
                    self._set_ok_enabled(False)
                    return
                self._close()

        class Group(Page):
            """更改分组弹层：分组列表（互斥单选）+ 确定。

            选项直接取 settings["gameList"] 的键——分组只活在那张表里，
            没有别的地方记着一共有哪些组。条目用设置页那套 Bool（勾选图标 +
            文本），塞进同一个 QButtonGroup 就成了互斥单选。
            比其它弹层高 60%（190 → 304），多出来的高度全给列表滚动用。
            """

            TITLE_KEY = "core.wid.pages.gameManage.group"
            TIP_KEY = "core.wid.pages.gameManage.group.tip"
            HEIGHT = 304            # 其余弹层是 190，这里是它的 1.6 倍

            def init_body(self, layout):
                self._choice = self._current_group()
                self._items = []

                layout.addSpacing(10)

                self.tip = QLabel()
                self.tip.setProperty("wid", "text")
                self.tip.setStyleSheet("font-size: 14px;")
                layout.addWidget(self.tip, 0)

                layout.addSpacing(10)

                # 列表底：滚动区自己只画 viewport，颜色得由装在它里面的容器给，
                # 这样滚动时才是一整块 color2，而不是底色与内容两层脱开
                self.box = QWidget()
                self.box.setProperty("wid", "color2")
                self.box.setAttribute(Qt.WA_StyledBackground, True)
                self.scroll = Scroll(self, content=self.box,
                                     margins=(10, 5, 10, 5))
                layout.addWidget(self.scroll, 1)

                layout.addSpacing(10)

                self.bottom = QWidget()
                self.bottom.setStyleSheet("background: transparent;")
                layout.addWidget(self.bottom, 0)
                self.bottom_l = QHBoxLayout(self.bottom)
                self.bottom_l.setContentsMargins(0, 0, 0, 0)
                self.bottom_l.setSpacing(8)
                self.bottom_l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

                self.btn_ok = QPushButton()
                self.btn_ok.setProperty("wid", "btn")
                self.btn_ok.setFixedSize(80, 30)
                self.btn_ok.clicked.connect(self._on_ok)
                self.bottom_l.addWidget(self.btn_ok, 0)

                # 互斥靠这一个组：条目只管往里加按钮，选中态由 Qt 自己管
                self.choices = QButtonGroup(self)
                self.choices.setExclusive(True)
                self._build()

            # ---------- 组装 ----------
            def _current_group(self):
                """当前分组；settings 里没登记（含 game 为空）按默认分组算。"""
                return group_of(events.settings, self.game) or mdtManager.DEFAULT_GROUP

            def _label(self, name):
                """条目要显示的文本：默认分组是个符号键，得翻成「默认」。

                别的分组名不是词条，langer.get() 查不到会原样返回，
                所以自定义组名照样显示自己，只有默认组那条会被翻译——
                顺带让它在切语言时自动跟着变。
                """
                if name == mdtManager.DEFAULT_GROUP:
                    return "core.text.default"
                return name

            def _build(self):
                """按 gameList 的键铺一组互斥项，勾上当前分组。"""
                for name in events.settings["gameList"]:
                    item = Bool(self.scroll, self._label(name))
                    item.setStyleSheet("background: transparent;")
                    self.choices.addButton(item.btn)
                    # 只认被勾上的那个；老项被组里自动取消时也会回调，忽略掉
                    item.btn.toggled.connect(
                        lambda checked, name=name: self._pick(name) if checked else None)
                    self.scroll.add(item)
                    self._items.append(item)
                    if name == self._choice:
                        item.btn.setChecked(True)

            def _pick(self, name):
                self._choice = name

            def langing(self):
                super().langing()
                self.tip.setText(events.lang.get(self.TIP_KEY))
                self.btn_ok.setText(events.lang.get("core.text.yes"))

            def _on_ok(self):
                """提交：分组只写在 settings 里，搬表的活交给 Editor.group。

                失败（实例没了 / 磁盘错）就不关窗，把失败摆在提示行上，
                免得用户以为换成功了、退出来发现还在原组。
                """
                editor = events.mdtManager.edit(self.game)
                editor.group(self._choice)
                if not editor.ok:
                    self.tip.setStyleSheet("font-size: 14px; color: red;")
                    self.tip.setText(events.lang.get("core.wid.pages.gameManage.failed"))
                    self._set_ok_enabled(False)
                    return
                self._close()

        class Delete(Page):
            """删除游戏弹层：警示文案 + 红底白字确认按钮。"""

            TITLE_KEY = "core.wid.pages.gameManage.delete"
            TIP_KEY = "core.wid.pages.gameManage.delete.tip"
            CONFIRM_KEY = "core.wid.pages.gameManage.delete.confirm"

            def init_body(self, layout):
                layout.addStretch(1)

                self.warn = QLabel()
                self.warn.setProperty("wid", "text")
                self.warn.setStyleSheet("font-size: 14px;")
                self.warn.setWordWrap(True)
                layout.addWidget(self.warn, 0)

                layout.addStretch(1)

                self.bottom = QWidget()
                self.bottom.setStyleSheet("background: transparent;")
                layout.addWidget(self.bottom, 0)
                self.bottom_l = QHBoxLayout(self.bottom)
                self.bottom_l.setContentsMargins(0, 0, 0, 0)
                self.bottom_l.setSpacing(8)
                self.bottom_l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

                self.btn_ok = QPushButton()
                self.btn_ok.setProperty("wid", "btn")
                self.btn_ok.setFixedSize(80, 30)
                # 红底白字：危险操作不吃确定按钮那套黄
                self.btn_ok.setStyleSheet(
                    "background-color: rgb(214, 62, 62); color: white; border: none;")
                self.btn_ok.clicked.connect(self._on_ok)
                self.bottom_l.addWidget(self.btn_ok, 0)

            def langing(self):
                super().langing()
                self.warn.setText(events.lang.get(self.TIP_KEY))
                self.btn_ok.setText(events.lang.get(self.CONFIRM_KEY))

            def _on_ok(self):
                """确认删除：连目录一起删，登记与 defaultGame 由 mdtManager 收拾。

                成功后本页出叠；GameSettings 收到 deleteGame 会自己出栈——
                实例都没了，那一页已经没有可管理的对象。
                """
                editor = events.mdtManager.edit(self.game)
                editor.delete()
                if not editor.ok:
                    # notFound / locked / ioError：把警示换成失败，按钮随即禁掉
                    self.warn.setStyleSheet("font-size: 14px; color: red;")
                    self.warn.setText(events.lang.get("core.wid.pages.gameManage.failed"))
                    self.btn_ok.setEnabled(False)
                    return
                self._close()

    class Java(Combo):
        """实例的 Java 选择行。

        词条复用设置页那套（wid.pages.setting.launcher.java.select*），只有「跟随全局」
        是本页独有的——设置页本身就是全局，没有这一项。
        对应 BML.json 里 javaPath 的三态（与 mdtManager.getMdtData 的解析一致）：
            mdtManager.FOLLOW - 跟随全局设置
            None              - 自动匹配（字段写 null，启动时挑 Java 17 或最高版本）
            具体路径          - 已选定的 Java
        头两项是固定项（文案随语言刷），其余按全局候选表显示版本号、路径挂 tooltip。
        校验与失败码全交给 mdtManager.edit()，这里只负责把当前值画出来。
        候选表交给 javaManager（有缓存，子线程扫）：changed 一到就重填，本页不自己扫盘。
        """

        AUTO = "auto"   # 「自动匹配」在 combo 里的占位值（写回 BML.json 时落成 null）

        def __init__(self, parent=None):
            self.page = parent       # 所属的 GameSettings 页，实例名现取（改名后自动是新名）
            self._none = False       # 一个 Java 也没嗅到：第 0 项文案改挂「无可用 Java」
            # 左侧标题走 Combo 那套 i18n，bus 的绑定也在 Combo.__init__ 里做完了；
            # 那条链上 MRO 先命中这里的 langing，所以覆写时必须 super() 上去
            super().__init__(parent, "core.wid.pages.setting.launcher.java.select")
            self.combo.popupAboutToShow.connect(self.fill)
            self.combo.activated.connect(self._apply)
            QTimer.singleShot(0, self.fill)

        @property
        def game(self):
            """实例名从页面现取：改名时页面自己换过了，这里不用跟着同步。"""
            return self.page.game

        def _current(self):
            """实例 BML.json 里记录的 javaPath 原值（FOLLOW / None / 具体路径）。

            读原值而不经 getMdtData：那里会把 FOLLOW 与 None 都解析成具体路径，
            界面就分不出用户当初选的是「跟随全局」还是「自动匹配」了。
            """
            if not self.game:
                return None
            return events.mdtManager.getMdtRaw(self.game).get("javaPath")

        def fill(self, javas=None):
            """按全局 Java 候选重填一遍，并把实例当前的选择对上去。

            javas 是 javaManager.changed 送来的候选表；不长传就用 settings 里那一份，
            自己削一遍失效项（展开下拉框时走这条）。
            """
            combo = self.combo
            combo.blockSignals(True)
            combo.clear()
            self._none = False
            if not self.game:
                # 实例无效（没指定或已失效）：顶部本来就是空的，这行也不该可点
                combo.setEnabled(False)
            else:
                if javas is None:
                    javas = events.settings["javaPaths"]
                    # 遍历副本：边遍历边 remove 会漏掉紧挨着的元素
                    javas = [java for java in list(javas) if javaManager.isJava(java[0])]
                else:
                    javas = list(javas)
                events.settings["javaPaths"] = javas
                current = self._current()
                self._none = not javas
                combo.setEnabled(True)
                # 头两项固定：跟随全局、自动匹配
                combo.addItem("", events.mdtManager.FOLLOW)
                combo.addItem("", self.AUTO)
                for java in javas:
                    combo.addItem("v%s" % java[1], java[0])
                    combo.setItemData(combo.count() - 1, java[0], Qt.ToolTipRole)
                if current is None:
                    index = combo.findData(self.AUTO)
                elif current == events.mdtManager.FOLLOW:
                    index = combo.findData(events.mdtManager.FOLLOW)
                else:
                    index = combo.findData(current)
                    if index < 0:
                        # 记法变过（绝对 ↔ 相对），候选表里那条就是它：按真身对回来，
                        # 免得同一个 Java 在列表里出现两次
                        for i in range(combo.count()):
                            if javaManager.sameJava(combo.itemData(i), current):
                                index = i
                                break
                    if index < 0:
                        # 记录里的 Java 已不在候选里（卸载/换盘）：照样列出来，
                        # 否则界面显示的选项跟 BML.json 里的实际值对不上
                        combo.addItem("v%s" % (javaManager.getJavaVersion(current) or "?"), current)
                        combo.setItemData(combo.count() - 1, current, Qt.ToolTipRole)
                        index = combo.count() - 1
                combo.setCurrentIndex(index)
            combo.blockSignals(False)
            self._texts()

        def _texts(self):
            """刷那两条固定项的文案：版本号与路径不用翻译，固定项得跟着语言走。"""
            combo = self.combo
            index = combo.findData(events.mdtManager.FOLLOW)
            if index >= 0:
                # 没装 Java 时这条改挂「无可用 Java」，两种情况都复用设置页的词条；
                # 「跟随全局」是本页独有的，设置页没有对应文案
                key = ("core.wid.pages.setting.launcher.java.select.none" if self._none
                       else "core.wid.pages.gameManage.java.follow")
                combo.setItemText(index, events.lang.get(key))
            index = combo.findData(self.AUTO)
            if index >= 0:
                combo.setItemText(index, events.lang.get("core.wid.pages.setting.launcher.java.select.auto"))

        def _apply(self, index):
            """把选中的 Java 写进实例：校验与失败码全在 mdtManager.edit() 里。"""
            data = self.combo.currentData()
            current = self._current()
            if data is None or data == (self.AUTO if current is None else current):
                return
            editor = events.mdtManager.edit(self.game)
            if data == self.AUTO:
                # 自动匹配：字段写 null，getMdtData 认这个值自行挑版本，不跟全局设置
                editor.set("javaPath", None)
            elif data == events.mdtManager.FOLLOW:
                editor.java(None)
            else:
                editor.java(data)
            if not editor.ok:
                # notFound / invalidJava：实例没了或选中的 Java 已失效，
                # 重填一遍把界面退回真实值，不留在假的选项上
                self.fill()

        def langing(self):
            super().langing()   # 左侧标题
            self._texts()

def register():
    """本文件定义的东西，在这里一次性交出去。由 pages/builtin.py 调用一次。

    GameManager 是**容器的入口** —— 谁要打开游戏管理，从注册表按 key 取，
    不必 import 这个类（start.py 就是这么用的）。
    """
    # 管哪个实例走 Box 上下文：开浮层的人才知道（start.py 传当前显示那个）
    registry.add("core.overlays", "core.gameManager",
                 init=lambda b: GameManager(b.game, b.parent),
                 order=10, title="core.wid.pages.gameManager", layer="stack")

    # 左栏那个「设置」功能页。它管的是**某个实例**，实例名从 GameManager
    # 现取（b.parent.game）—— 容器里改了名，这里跟着换，不用自己同步。
    registry.add("core.gameManager.pages", "core.gameManager.settings",
                 init=lambda b: GameSettings(b.parent.game, b.parent),
                 order=10, title="core.wid.pages.gameManager.settings")

    # 设置页里的两个区块。本文件定义了它们，所以本文件交出去。
    registry.add("core.gameSettings.sections", "core.gameSettings.folders",
                 init=lambda b: GameSettings.Folders(b.parent),
                 attr="folders", order=10, spacing=10)
    registry.add("core.gameSettings.sections", "core.gameSettings.java",
                 init=lambda b: GameSettings.Java(b.parent),
                 attr="java", order=20, spacing=20)
