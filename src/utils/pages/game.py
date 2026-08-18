

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout

from ..path_utils import getPath


from ._init import *


#TODO: 游戏管理界面
class Game(Page):
    def __init__(self, parent=None, root=None, text=None, logo=None):
        super().__init__(parent, root, text, logo)

    class Main(Mainw):
        def __init__(self, parent=None, root=None):
            super().__init__(parent, root)
            self.init_wid()

        def init_wid(self):
            self.layout = QVBoxLayout(self)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.layout.setSpacing(0)

            self.todoText = QLabel("UNFINISHED")
            self.todoText.setProperty("wid", "text")
            self.todoText.setAlignment(Qt.AlignCenter)
            self.todoText.setStyleSheet("font-size: 20px;")
            self.layout.addWidget(self.todoText,1)
