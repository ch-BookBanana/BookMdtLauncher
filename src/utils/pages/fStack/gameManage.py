from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget


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


class GameManage(QWidget):
    def __init__(self, game, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.game = game
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.init_wid()    

    def init_wid(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.top = self.Top(self, self.root)
        self.layout.addWidget(self.top, 0)

        self.line = QWidget(self)
        self.line.setFixedHeight(1)
        self.line.setProperty("wid", "line")
        self.layout.addWidget(self.line, 0)

        self.body = self.Body(self, self.root)
        self.layout.addWidget(self.body, 1)

        # 顶部信息填真实数据（图标/名称/版本），并订阅实例事件：
        # 本页后续的管理项都以 self.game 为操作对象，改名时必须跟着换
        self.refresh()
        self.root.mdtScanner.on_game_changed.connect(self._on_game_changed)

    def refresh(self):
        """按当前实例刷新顶部；没指定实例或实例已失效（msg 为 None）时顶部留空。"""
        msg = self.root.mdtScanner.getMdtMsg(self.game) if self.game else None
        self.top.sets(self.game, msg)

    def _on_game_changed(self, data):
        """实例事件：改名时把 self.game 一起换掉（否则后续操作会拿着旧目录名报 notFound）。

        改名归 nameChanged（比对 old_name）、图标/版本归 iconChanged（比对 game），
        其余事件（新增、删除）与本页无关。
        """
        etype = data["type"]
        if etype == "nameChanged":
            if data["old_name"] != self.game:
                return
            self.game = data["game"]
        elif etype == "iconChanged":
            if data["game"] != self.game:
                return
        else:
            return
        self.refresh()

    def on_close(self):
        """出栈（或被清空）时断开订阅：页面随即被销毁，事件不能再打回来。"""
        try:
            self.root.mdtScanner.on_game_changed.disconnect(self._on_game_changed)
        except (RuntimeError, TypeError):
            pass

    class Top(QWidget):
        def __init__(self, parent=None, root=None):
            super().__init__(parent)
            self.parent = parent
            self.root = root
            self.init_ui()
            self.init_wid()

        def init_ui(self):
            self.setFixedHeight(100)
            self.setAttribute(Qt.WA_StyledBackground, True)

        def init_wid(self):
            self.layout = QHBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 10)
            self.layout.setSpacing(0)
            self.layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

            self.icon = QLabel()
            self.icon.setProperty("wid", "png")
            self.icon.setFixedSize(80, 80)
            self.icon.setScaledContents(True)
            self.layout.addWidget(self.icon, 0)

            self.layout.addSpacing(10)

            self.l2w = QWidget()
            self.l2 = QVBoxLayout(self.l2w)
            self.l2.setContentsMargins(0, 0, 0, 0)
            self.l2.setSpacing(0)
            self.layout.addWidget(self.l2w, 1)

            self.name = _ElideLabel()
            self.name.setProperty("wid", "text")
            self.name.setFixedHeight(40)
            self.name.setStyleSheet("font-size: 22px;")
            self.l2.addWidget(self.name, 0)

            self.vers = _ElideLabel()
            self.vers.setProperty("wid", "text")
            self.vers.setFixedHeight(30)
            self.vers.setStyleSheet("font-size: 16px;")
            self.l2.addWidget(self.vers, 0)

            self.l2.addStretch(1)

        def sets(self, name, msg):
            """填入实例信息（mdtScanner.getMdtMsg 的返回值）；msg 为 None 则全部留空。

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
            self.icon.setToolTip("\n".join(x for x in (name, vers) if x))

    class Body(QWidget):
        def __init__(self, parent=None, root=None):
            super().__init__(parent)
            self.parent = parent
            self.root = root
            self.init_wid()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.scroll = QScrollArea(self)
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.NoFrame)
            self.layout.addWidget(self.scroll)

            self.content = self.Content(self, self.root)
            self.scroll.setWidget(self.content)

        class Content(QWidget): #TODO: 添加管理项
            """主体内容区：后续在此填充管理项"""

            def __init__(self, parent=None, root=None):
                super().__init__()
                self.parent = parent
                self.root = root
                self.init_wid()

            def init_wid(self):
                self.layout = QVBoxLayout(self)
                self.layout.setContentsMargins(20, 20, 20, 20)
                self.layout.setSpacing(10)
                self.layout.setAlignment(Qt.AlignTop)

                self.todoText = QLabel("UNFINISHED")
                self.todoText.setProperty("wid", "title")
                self.todoText.setAlignment(Qt.AlignCenter)
                self.todoText.setStyleSheet("font-size: 20px;")
                self.layout.addWidget(self.todoText, 1)

