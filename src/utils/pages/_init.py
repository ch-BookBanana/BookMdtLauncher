from PySide6.QtWidgets import QWidget


class Leftw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__(None)
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.left.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.left.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width

       
class Mainw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.parent.parent.main.addWidget(self)

class Rightw(QWidget):
    def __init__(self, parent=None, root=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.width_ = 0
        self.resize_(0)
        self.parent.parent.right.addWidget(self)

    def resizeEvent(self, event):
        self.parent.parent.right.setFixedWidth(self.width_)
        super().resizeEvent(event)

    def resize_(self,width):
        self.setFixedWidth(width)
        self.width_ = width


class Page():
    def __init__(self, parent=None, root=None, text=None, logo=None):
        super().__init__()
        self.parent = parent
        self.root = root
        self.text = text
        self.logo = logo
        self.init_wid()
        self.id = len(self.parent.pages)
        self.parent.pages.append(self)
        self.btn = self.root.window.left.pagebtns.add_btn(self.text,self.logo)
        self.parent.btns.append(self)
        self.btn.clicked.connect(self.changePage)

    def changePage(self):
        self.parent.left.setCurrentWidget(self.left)
        self.parent.main.setCurrentWidget(self.main)
        self.parent.right.setCurrentWidget(self.right)
        self.parent.left.setFixedWidth(self.left.width_)
        self.parent.right.setFixedWidth(self.right.width_)

    def click(self):
        self.btn.click()

    def init_wid(self):
        cls_left = self.Left if hasattr(self, 'Left') else Leftw
        self.left = cls_left(self, self.root)

        cls_main = self.Main if hasattr(self, 'Main') else Mainw
        self.main = cls_main(self, self.root)

        cls_right = self.Right if hasattr(self, 'Right') else Rightw
        self.right = cls_right(self, self.root)
