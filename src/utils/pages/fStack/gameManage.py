from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget


class GameManage(QWidget):
    def __init__(self, game, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.game = game
        self.init_ui()
        self.init_wid()

    def init_ui(self):
        self.setFixedSize(520, 365)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid", "color2")

    def init_wid(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignTop)

        self.top = self.Top(self, self.root)
        self.layout.addWidget(self.top, 0)

        self.line = QWidget(self)
        self.line.setFixedHeight(1)
        self.line.setProperty("wid", "line")
        self.layout.addWidget(self.line, 0)

        self.body = self.Body(self, self.root)
        self.layout.addWidget(self.body, 1)

    class Top(QWidget):
        def __init__(self, parent=None, root=None):
            super().__init__(parent)
            self.parent = parent
            self.root = root
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

            self.title = QLabel("游戏管理")
            self.title.setProperty("wid", "title")
            self.title.setStyleSheet("font-size: 16px;")
            self.layout.addWidget(self.title, 1)

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

        class Content(QWidget):
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

