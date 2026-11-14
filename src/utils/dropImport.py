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
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
"""拖放导入：把 jar / zip 拖到窗口上，开导入浮层并填好路径。

为什么单独一层
--------------
Qt 的拖放事件必须由「接受方」重写，而「拖进来的是什么、能不能导、导完
怎么落地」跟窗口无关。本模块只做两件事：从 MIME 数据里挑出可导入的文件、
画一层「松开以导入」的提示。窗口负责把事件转过来，导入本身仍走
pages/Modal/importJar 那条已经验过的链路 —— 拖放只是换了个选文件的方式，
不是第二条导入路径。

只筛后缀，不在这里验包
----------------------
拖动经过窗口时只为回答「要不要亮起提示」，此刻去读 zip 中央目录会让拖动
一顿一顿的（网络盘上尤其明显）。真正的校验留给 inspect_package，它是毫秒级
且只跑一次。
"""

import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QLineEdit, QPlainTextEdit,
                               QTextEdit, QWidget)
from shiboken6 import isValid

# 能导入的后缀。拖进来一个 .txt 时不该亮「松开以导入」，所以先按后缀筛一道；
# 后缀对但内容不对的（改名的压缩包、半截文件）由验包那一关拒收。
DROP_SUFFIXES = (".jar", ".zip")

# 本次拖动里被 disable_child_drops 关掉拖放的控件；拖动结束由
# restore_child_drops 还原（否则一次拖 jar 会把输入框的拖文本能力永久关掉）。
_DROPS_OFF = []

# 提示卡片尺寸：一行标题 + 一行说明，两行都居中
CARD_W = 300
CARD_H = 118


def drop_candidates(mime):
    """列出拖放数据里所有可导入的本地文件路径（保持拖动时的顺序）。

    只认本地文件：从浏览器拖来的图片/链接是 hasUrls 但没有本地路径，或者
    指向一个 http 地址，都不该被当成能导入的包。
    """
    if mime is None or not mime.hasUrls():
        return []
    found = []
    for url in mime.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if not path or not path.lower().endswith(DROP_SUFFIXES):
            continue
        # QUrl 给出的本地路径在 Windows 上是正斜杠，而浏览入口给的是反斜杠。
        # 统一成后者：同一个文件从两个入口进来，界面上显示的路径不该长得不一样。
        found.append(os.path.normpath(path))
    return found


def first_candidate(mime):
    """第一个可导入的文件；没有就返回空串。"""
    found = drop_candidates(mime)
    return found[0] if found else ""


def disable_child_drops(root):
    """关掉子控件自带的文件拖放，让事件统一冒泡到窗口。

    QLineEdit / QTextEdit 默认 acceptDrops=True，意思是「允许把拖进来的文字
    插进去」。控制台铺满右栏，文件落上去就被它当成待插入的文本吃掉，窗口
    永远收不到 drop —— 表现是「拖到右边没反应，拖到左边才行」。
    这些都是输入控件，拖一个 jar 进去没有任何合理语义。

    关掉的控件记在 _DROPS_OFF 里，拖动一结束就由 restore_child_drops 还原：
    拖文本进输入框是这些控件本来就该有的能力，不能因为用户拖过一次 jar 就
    永久失效。
    """
    for cls in (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox):
        for wid in root.findChildren(cls):
            if wid.acceptDrops():
                wid.setAcceptDrops(False)
                _DROPS_OFF.append(wid)


def restore_child_drops():
    """把 disable_child_drops 关掉的子控件还原（拖动结束/取消时调）。"""
    while _DROPS_OFF:
        wid = _DROPS_OFF.pop()
        try:
            if isValid(wid):        # 拖动期间页面可能已被销毁
                wid.setAcceptDrops(True)
        except Exception:
            pass


def open_import(parent, path):
    """开导入浮层并把文件填进去，返回浮层实例。"""
    # 延迟导入：本模块由 main.py 在启动早期引入，而 pages._init 要等注册表
    # 声明完才能用。放在函数里，导入顺序就不必再迁就谁先谁后。
    from .pages._init import open_overlay

    wid = open_overlay("core.importJar", parent)
    wid.set_path(path)
    return wid


class DropHint(QWidget):
    """铺满窗口的拖放提示：半透明遮罩 + 居中一张虚线卡片。

    全部自绘，不用子控件也不用样式表 —— 全局 `QWidget` 规则会把任何裸容器
    刷成面板底色（导入浮层为这个加过 wid="plain"），自绘不受它影响。
    鼠标穿透属性保证它不参与事件分发；即便拖动位置落在它上面，因为它不接受
    drops，Qt 也会向上找到窗口作为落点。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._light = False
        self._title = ""
        self._desc = ""
        self.hide()

    def show_hint(self, light, title, desc):
        """亮起提示。主题在每次拖动进入时现读，切过主题也不会留旧色。"""
        self._light = bool(light)
        self._title = title or ""
        self._desc = desc or ""
        self.update()
        self.show()
        self.raise_()

    def hide_hint(self):
        # 用 isHidden 而不是 isVisible 做守卫：父窗口尚未显示时子控件的
        # isVisible() 恒为 False，拿它判断会让 hide 永远不执行，提示层
        # 就留在「已 show 但没 hide」的状态里。
        if not self.isHidden():
            self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))

        card = QRectF((self.width() - CARD_W) / 2.0,
                      (self.height() - CARD_H) / 2.0, CARD_W, CARD_H)
        # 虚线边框用品牌黄：和「确定」按钮同一个色，读起来就是「这里可以放」
        p.setPen(QPen(QColor("#f0b731"), 1.5, Qt.DashLine))
        p.setBrush(QColor("#373737" if not self._light else "#e5e4e4"))
        p.drawRoundedRect(card, 12, 12)

        title_font = QFont(self.font())
        title_font.setPixelSize(16)
        title_font.setWeight(QFont.Weight.Medium)
        p.setFont(title_font)
        p.setPen(QColor("#e8e8e8" if not self._light else "#2c2c2a"))
        p.drawText(card.adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                   self._title)

        desc_font = QFont(self.font())
        desc_font.setPixelSize(12)
        desc_font.setWeight(QFont.Weight.Normal)
        p.setFont(desc_font)
        p.setPen(QColor("#9a9a9a" if not self._light else "#5f5e5a"))
        p.drawText(card.adjusted(0, 62, 0, 0), Qt.AlignHCenter | Qt.AlignTop,
                   self._desc)
