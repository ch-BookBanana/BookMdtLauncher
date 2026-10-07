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

宿主设置（基层）。

为什么从裸 dict 升成一个类
--------------------------
1. **schema 有出处**：键与默认值在这一个文件里看得全（原来是一段藏在
   Main.__init__ 里的字面量），写值能校验，读文件时也能按它淘汰已删的键；
2. **写值会通知**：原先「谁改谁记得调 saveSettings」散在十几处，漏一个就是
   悄悄丢配置；现在改了就通知，存盘由宿主挂一个防抖的订阅者统一做；
3. **它是个对象**：可以从多处持有同一个引用 —— 重载上层（服务/插件/界面）时
   这些引用不会失效。

仍然是 MutableMapping
---------------------
全仓有 138 处 `settings["x"]` / `settings.get(...)`，所以这个类必须**长得像
dict**，那些写法一行都不用改。子对象也一样：`_Section` 继承 dict（别处有
`isinstance(x, dict)` 的判断，换成别的映射类型会把那些地方弄坏），并且
`settings["a"]["b"] = x` 这种嵌套写也会通知 —— 通知的是 `a.b` 这条路径。

它不依赖谁
----------
基层不往上依赖：日志与翻译都是**注入**进来的（logger / tr），拿不到就退化成
标准库打印与原文。所以这个模块可以直接单测，不用起 Qt、不用起宿主。

两级：基础 + 浮层
----------------
文件按两级摆：

    第一级（文件上面那一大段）  L0 基础：schema、读文件、合并、通知、写盘，
                                一行 Qt 都不碰 —— 上面那句「不用起 Qt」说的是它；
    第二级（文件末尾那一段）    要 Qt 的东西：当前只有一个关闭询问浮层
                                （点窗口 × 时问「藏到托盘还是退出」）。

浮层放这儿，是因为它问的恰好是第一级那个字段 closeByTray（一个字段配一层
问法，摆在一起看得清）；它同时**登记进 core.overlays**（见本文件末尾的
register），于是想换问法 / 换样式的人可以拿一条同名条目把它盖掉 —— 控件写
在这儿，口子开在注册表，两件事不冲突。QWidget 是类体上的基类，没法「用到才
拉 Qt」，所以第二级的 Qt import 就摆在第二级开头 —— 界面上仍然是「先基础、
后浮层」。
"""

import copy
import json
import os
import shutil
import time
from collections.abc import MutableMapping
from datetime import datetime

from .path_utils import getPath

SETTINGS_PATH = "BML/settings.json"
BAD_DIR = "BML/badSettings"          # 损坏 settings 的备份目录
BAD_KEEP = 5                         # 损坏备份最多保留份数
_MISSING = object()


# ─────────────────────────── 默认值表（= schema）───────────────────────────

DEFAULT_SCHEMA = {
    "language": None,
    "theme": 0,
    "maxLogNum": 50,
    # 点右上角 × 时怎么办：True = 隐藏到托盘，False = 退出启动器，
    # None（默认）= 每次弹一层问，用户勾「保存到设置」才定下来
    "closeByTray": None,
    "defaultGame": None,
    "javaPath": None,
    "github": {
        "token_enc": None,
        "token_key": None,
        "useful": None,
        "user": {
            "name": None,
            "headurl": None
        },
        "rate": {
            "core":   {"remaining": None, "reset": []},
            "search": {"remaining": None, "reset": []}
        }
    },
    "javaPaths": [],
    "gameList": {"<:|default|:>": []},
    # 插件设置：一格一个插件（example_hello: {...}）。
    # 空 dict 是「开放映射」—— 键由插件自己定，宿主没法定 schema，
    # 见 _merge 里对空 dict 默认值的处理。
    "pluginSettings": {},
    # 上次加载失败、已被标注停用的插件 id（下次启动不再加载它们）
    "disabledPlugins": []
}


# ─────────────────────────── 原子写盘（不依赖 Qt）───────────────────────────

def _replace_with_retry(src, dst, attempts=4):
    """os.replace 在 Windows 上可能被杀毒/索引临时占用，短重试以躲开瞬时锁。"""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05)


def atomic_write_json(path, data):
    """原子写入 JSON：写同目录唯一临时文件并刷盘，再 os.replace 覆盖目标。

    任意时刻磁盘上的目标文件要么是旧内容、要么是新内容；
    临时名带 pid 与纳秒时间戳，多线程同时保存也不会互相踩踏。
    """
    tmp = f"{path}.{os.getpid()}-{time.time_ns()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(',', ':'), ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


# ─────────────────────────── 子对象（会通知的 dict）───────────────────────────

class _Section(dict):
    """设置里的一层子对象。

    继承 dict 是**有意的**：别处有 `isinstance(x, dict)` 的判断（插件设置那格
    就看它），换成 MutableMapping 会把那些地方弄坏。

    构造时就把下层的 dict 递归包成 _Section（**存进去**，不是每次读时包）：
    dict 子类没法做「视图」，若在 __getitem__ 里现包一份拷贝，写进去就丢了。
    这样 `settings["a"]["b"] = x` 走的是同一份存储，并且会通知到 `a.b`。

    代价是「写进去的」与「赋值给变量拿到的」不是同一个对象：写
    `d = settings["a"] = {}` 时，`d` 是那个原 dict，存进去的却是包过的副本，
    之后往 `d` 上写不会生效。给一个不存在的层赋值后要接着用它，就**重新取**：

        settings["a"] = {}
        d = settings["a"]
    """

    def __init__(self, data=None, *, root=None, path=""):
        super().__init__()
        self._root = root
        self._path = path
        for k, v in (data or {}).items():
            dict.__setitem__(self, k, self._wrap(v, k))

    def _child_path(self, key):
        return "%s.%s" % (self._path, key) if self._path else str(key)

    def _wrap(self, value, key):
        if isinstance(value, _Section):
            return value
        if isinstance(value, dict):
            return _Section(value, root=self._root, path=self._child_path(key))
        return value

    def _changed(self, key, old, new):
        if self._root is not None:
            self._root._notify(self._child_path(key), old, new)

    def __setitem__(self, key, value):
        old = dict.get(self, key, _MISSING)
        dict.__setitem__(self, key, self._wrap(value, key))
        self._changed(key, old, value)

    def __delitem__(self, key):
        old = dict.get(self, key, _MISSING)
        dict.__delitem__(self, key)
        self._changed(key, old, _MISSING)

    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self[k] = v

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def pop(self, key, *default):
        if key in self:
            old = dict.__getitem__(self, key)
            del self[key]
            return old
        if default:
            return default[0]
        raise KeyError(key)

    def clear(self):
        for key in list(self):
            del self[key]

    # 深拷贝要给回普通结构，免得拷贝出来的东西还牵着一个 root
    def __deepcopy__(self, memo):
        return copy.deepcopy(dict(self), memo)


# ─────────────────────────── 设置本体 ───────────────────────────

class Settings(MutableMapping):
    """宿主设置：schema 有出处、写值有通知、落盘有事务。

    用法与原 dict 完全一致：

        settings["theme"] = 1          # 会通知
        settings["github"]["user"] = {}  # 嵌套写也会通知（路径 "github.user"）
        settings.get("defaultGame")
    """

    def __init__(self, schema=None, *, path=None, backup_dir=None, keep_backups=BAD_KEEP,
                 logger=None, tr=None):
        self.schema = copy.deepcopy(schema if schema is not None else DEFAULT_SCHEMA)
        self._path_override = path
        self.backup_dir = backup_dir or BAD_DIR
        self.keep_backups = keep_backups
        self._logger = logger
        self._tr = tr
        self._watchers = []
        self.data = self._fresh()

    # ── 注入的两样（基层不往上依赖）──

    def set_logger(self, logger):
        self._logger = logger
        return self

    def set_tr(self, tr):
        self._tr = tr
        return self

    def _log(self, level, msg, **kw):
        log = self._logger
        if log is None:
            return
        try:
            getattr(log, level, log.info)(msg, **kw)
        except Exception:
            pass

    def _t(self, key, fallback):
        """翻译：宿主挂了 Langer 就用它，没有就退回英文原文。"""
        if self._tr is None:
            return fallback
        try:
            got = self._tr(key)
            return got if got and got != key else fallback
        except Exception:
            return fallback

    # ── 路径 ──

    @property
    def path(self):
        return self._path_override or getPath(SETTINGS_PATH)

    # ── MutableMapping ──

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return "<Settings %s keys=%d>" % (self.path, len(self.data))

    # ── 变更通知 ──

    def watch(self, fn):
        """订阅写值：fn(路径, 旧值, 新值)。路径是点分的（"github.user"）。

        宿主拿它挂一个防抖存盘 —— 于是「谁改谁记得存」这件事就不存在了。
        """
        self._watchers.append(fn)
        return fn

    def unwatch(self, fn):
        if fn in self._watchers:
            self._watchers.remove(fn)

    def _notify(self, path, old, new):
        for fn in list(self._watchers):
            try:
                fn(path, None if old is _MISSING else old,
                   None if new is _MISSING else new)
            except Exception as e:
                self._log("error", f"设置变更订阅者抛异常（{path}）：{e}")

    # ── 读盘 / 写盘 ──

    def _fresh(self):
        """按 schema 造一份干净的（子对象也包好）。"""
        return _Section(self.schema, root=self)

    def reset(self):
        """回到默认值（损坏回退 / 测试用）。"""
        self.data = self._fresh()
        return self

    def load(self):
        """从文件读进来，按 schema 合并；读不了或值非法就备份原文件再回默认值。"""
        self._clean_tmp()
        path = self.path
        if not os.path.exists(path):
            self._log("warning", "settings file not found, using default settings")
            return self
        try:
            self._log("info", "loading settings...")
            raw = self._read_file(path)
        except Exception as e:
            self._log("error",
                      "ERR:Fail to load settings, using default setting"
                      "\n--Exception: " + str(e), exc_info=True)
            self.reset()
            self._backup(path, (str(e).splitlines() or ["unreadable"])[0])
            return self

        self.reset()
        issues = self._merge(self.data, raw)
        if issues:
            self._log("warning",
                      "settings has invalid values, fallback to default: " + "; ".join(issues))
            self._backup(path, "invalid values")
        return self

    def save(self):
        """原子写盘。写不进去只记日志 —— 设置存不下去不该把正在做的事一起弄崩。"""
        try:
            atomic_write_json(self.path, self.data)
            self._log("info", self._t("core.log.info.saveSettings", "Settings saved"))
            return True
        except Exception as e:
            self._log("error",
                      self._t("core.log.error.saveSettings", "Failed to save settings")
                      + "\n--Exception: " + str(e), exc_info=True)
            return False

    @staticmethod
    def _read_file(path):
        """读 settings.json 并返回 dict；内容为空或不是对象时抛异常。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("root is not a JSON object")
        return data

    # ── 合并（schema 驱动）──

    @classmethod
    def _merge(cls, default, file_settings, path=""):
        """把文件里的设置合并进默认设置（就地），返回被拒绝的键说明列表。

        只接受默认值里已有的键（多余键丢弃，用于淘汰已删除的设置项）；
        类型不符的键保留默认值并记录；dict 递归合并，其余叶子直接覆盖。
        默认值为 None 的键推不出类型（如 language/defaultGame），一律放行。
        默认值是**空 dict** 的键按开放映射处理：宿主不认识里面的键
        （插件设置就是这样，键由插件自己定），逐项收下、值仍要求是 dict。
        """
        issues = []
        if not default:
            # 开放映射：整片收下，只查值是不是对象
            for key, value in file_settings.items():
                if isinstance(value, dict):
                    default[key] = value
                else:
                    issues.append(f"{path}{key}: object -> {type(value).__name__}")
            return issues
        for key, value in file_settings.items():
            if key not in default:
                continue
            cur = default[key]
            if isinstance(cur, dict):
                if isinstance(value, dict):
                    issues += cls._merge(cur, value, f"{path}{key}.")
                else:
                    issues.append(f"{path}{key}: object -> {type(value).__name__}")
            elif cls._accepts_value(cur, value):
                default[key] = value
            else:
                issues.append(f"{path}{key}: {type(cur).__name__} -> {type(value).__name__}")
        return issues

    @staticmethod
    def _accepts_value(default_value, value):
        """判断文件里的值能否覆盖默认值（None 默认值放行；bool 与 int 严格区分）。"""
        if default_value is None:
            return True
        if isinstance(default_value, bool) or isinstance(value, bool):
            return isinstance(default_value, bool) and isinstance(value, bool)
        if isinstance(default_value, (int, float)):
            return isinstance(value, (int, float))
        return isinstance(value, type(default_value))

    # ── 损坏备份 ──

    def _clean_tmp(self):
        """清理上次写盘中断残留的临时文件（settings.json.<pid>-<ns>.tmp）。"""
        try:
            head = os.path.basename(self.path) + "."
            folder = os.path.dirname(self.path)
            for name in os.listdir(folder):
                if name.startswith(head) and name.endswith(".tmp"):
                    os.remove(os.path.join(folder, name))
        except Exception:
            pass

    def _backup(self, path, reason):
        """把有问题的 settings 备份到 badSettings/settings.<时间戳>.json，返回备份路径。"""
        try:
            if not os.path.isfile(path):
                return None
            folder = getPath(self.backup_dir)
            os.makedirs(folder, exist_ok=True)
            name = "settings.%s.json" % datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = os.path.join(folder, name)
            shutil.copy2(path, dest)
            self._log("warning", "bad settings backed up: %s/%s --%s"
                      % (self.backup_dir, name, reason))
            self._prune_backups()
            return dest
        except Exception as e:
            self._log("error", "Failed to back up settings\n--Exception: " + str(e))
            return None

    def _prune_backups(self):
        """只保留最近 keep_backups 份，避免目录堆积（文件名按时间戳排序即时间序）。

        keep_backups = 0 时全删 —— `names[:-0]` 是空表（不是「一份不留」），
        所以这里显式分开写。
        """
        try:
            folder = getPath(self.backup_dir)
            names = sorted(n for n in os.listdir(folder)
                           if n.startswith("settings.") and n.endswith(".json"))
            keep = max(0, int(self.keep_backups))
            doomed = names if keep == 0 else names[:-keep]
            for name in doomed:
                os.remove(os.path.join(folder, name))
        except Exception:
            pass


# ═══════════════════════ 第二级：浮层（要 Qt）═══════════════════════
#
# 见模块说明「两级：基础 + 浮层」。上面是第一级（一行 Qt 都不碰），
# 从这里往下是第二级。QWidget 是类体上的基类，躲不掉 —— 所以 Qt 的 import
# 就摆在这儿，而不装成「用到才拉」。

from PySide6.QtCore import Qt                                     # noqa: E402
from PySide6.QtGui import QColor, QIcon                            # noqa: E402
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel,   # noqa: E402
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .bus import bus                                               # noqa: E402
from .events import events                                         # noqa: E402
from .options.items import Bool                                    # noqa: E402
from .options.scrolls import Scroll                                # noqa: E402
from .registry import registry                                     # noqa: E402
from .resources import TBT_CLOSE                                   # noqa: E402
from .utils import change_color                                    # noqa: E402

# 关闭询问的两个选项：值 → 文案键。第一个是默认勾上的那个。
# closeByTray 是三态（见 DEFAULT_SCHEMA）：True = 藏到托盘，False = 退出，
# None = 每次问 —— 这一层就是为 None 准备的，谁来弹见 main.py 的 close_()。
CLOSE_CHOICES = (("tray", "core.wid.closeAsk.tray"),
                 ("quit", "core.wid.closeAsk.quit"))


class AskClose(QWidget):
    """关闭询问浮层：点窗口右上角那个 × 时问一句「藏到托盘，还是退出」。

    样式照 gameManager 的「更改分组」弹层：同一套面板底板（标题栏 + 分割线 +
    内容区）、同一个滚动列表（Bool 塞进一个 QButtonGroup 当互斥单选）+ 底部
    确定。滚动区**下面**多一项「保存到设置」：勾上才把这次的选择写回 settings
    （写完立刻落盘），不勾就只做这一次 —— 下次点 × 还会问。

    遮罩与居中由 FloatingOverlay 提供，这里只画面板。答复走事件
    （closeRequested）：藏还是退由窗口自己动手，浮层不该知道窗口能被藏起来。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("wid_", "_window.closeAsk")

        self.l = QHBoxLayout(self)
        self.l.setContentsMargins(0, 0, 0, 0)
        self.l.setSpacing(0)
        self.l.setAlignment(Qt.AlignCenter)

        self.panel = self.Panel(self)
        self.l.addWidget(self.panel, 0)
        self.hide()

    def showEvent(self, event):
        # 显示时提层，盖过 floatingStack 等覆盖控件
        super().showEvent(event)
        self.raise_()

    def close_(self):
        """关闭自身：从叠加浮层出叠（每次打开都是现建的，不留旧实例）。"""
        events.emit("overlayClosed", self, True)

    class Panel(QWidget):
        """面板：标题栏（标题 + ×）+ 分割线 + 内容区。"""

        WIDTH = 320
        # 提示 + 两项互斥选择（各 40 高）+ 保存到设置（40）+ 底部按钮
        HEIGHT = 260
        TITLE_KEY = "core.wid.closeAsk.title"
        TIP_KEY = "core.wid.closeAsk.tip"
        SAVE_KEY = "core.wid.closeAsk.save"

        def __init__(self, parent=None):
            super().__init__()
            self.parent = parent
            self._choice = CLOSE_CHOICES[0][0]      # 默认「隐藏到托盘」
            self._items = {}
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
            # × = 这次什么都不做（既没藏也没退），浮层自己收起来
            self.btn_close.clicked.connect(self.parent.close_)
            self.top_l.addWidget(self.btn_close, 0)

            self.line = QWidget()
            self.line.setFixedHeight(1)
            self.line.setProperty("wid", "line")
            self.layout.addWidget(self.line, 0)

            self.body = QWidget()
            self.layout.addWidget(self.body, 1)
            self.body_l = QVBoxLayout(self.body)
            self.body_l.setContentsMargins(15, 0, 15, 15)
            self.body_l.setSpacing(0)
            self.body_l.setAlignment(Qt.AlignTop)

            self.body_l.addSpacing(10)
            self.tip = QLabel()
            self.tip.setProperty("wid", "text")
            self.tip.setStyleSheet("font-size: 14px;")
            self.tip.setWordWrap(True)
            self.tip.setFixedHeight(34)
            self.body_l.addWidget(self.tip, 0)
            self.body_l.addSpacing(10)

            # 选项底：和分组弹层一样用 color2 —— 滚动区自己只画 viewport，
            # 颜色得由装在它里面的容器给，滚起来才是一整块。
            self.box = QWidget()
            self.box.setProperty("wid", "color2")
            self.box.setAttribute(Qt.WA_StyledBackground, True)
            self.scroll = Scroll(self, content=self.box, margins=(10, 5, 10, 5))
            self.body_l.addWidget(self.scroll, 1)

            # 滚动区**下面**：勾上才把这次的选择写回设置
            self.save = Bool(self, self.SAVE_KEY)
            self.save.setStyleSheet("background: transparent;")
            self.body_l.addWidget(self.save, 0)
            self.body_l.addSpacing(10)

            self.bottom = QWidget()
            self.bottom.setStyleSheet("background: transparent;")
            self.body_l.addWidget(self.bottom, 0)
            self.bottom_l = QHBoxLayout(self.bottom)
            self.bottom_l.setContentsMargins(0, 0, 0, 0)
            self.bottom_l.setSpacing(8)
            self.bottom_l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.btn_ok = QPushButton()
            self.btn_ok.setProperty("wid", "btn")
            self.btn_ok.setFixedSize(80, 30)
            self.btn_ok.clicked.connect(self._on_ok)
            self.bottom_l.addWidget(self.btn_ok, 0)

            # 互斥靠这一个组：两项只管往里加按钮，选中态由 Qt 自己管
            self.choices = QButtonGroup(self)
            self.choices.setExclusive(True)
            self._build()

        def _build(self):
            """两项互斥单选，勾上默认那个（隐藏到托盘）。"""
            for value, key in CLOSE_CHOICES:
                item = Bool(self.scroll, key)
                item.setStyleSheet("background: transparent;")
                self.choices.addButton(item.btn)
                # 只认被勾上的那个；老项被组里自动取消时也会回调，忽略掉
                item.btn.toggled.connect(
                    lambda checked, value=value: self._pick(value) if checked else None)
                self.scroll.add(item)
                self._items[value] = item
            self._items[self._choice].btn.setChecked(True)

        def _pick(self, value):
            self._choice = value

        def langing(self):
            # 两项的文案由 Bool 自己管（它自己的 langing 会在切语言时重设）
            self.title.setText(events.lang.get(self.TITLE_KEY))
            self.tip.setText(events.lang.get(self.TIP_KEY))
            self.btn_ok.setText(events.lang.get("core.text.yes"))
            self.btn_close.setToolTip(events.lang.get("core.wid.top.close"))

        def lighting(self, light):
            # 关闭按钮图标随主题取色（面板其余部分交给全局 qss）
            color = QColor(120, 120, 120) if light else QColor(200, 200, 200)
            icon = change_color(TBT_CLOSE, color)
            self.btn_close.setIcon(QIcon(icon.pixmap(24, 24)))

        def _on_ok(self):
            """照选择动手，顺手把「以后也这么做」写进设置（如果勾了）。

            勾了才写：写的就是本模块那个 closeByTray（True = 藏到托盘，
            False = 退出），写完立刻落盘 —— 这次选择很可能紧跟着就是退出
            启动器，等宿主那套防抖存盘（500ms）是等不到的。
            """
            want_tray = self._choice == "tray"
            if self.save.btn.isChecked():
                events.settings["closeByTray"] = want_tray
                try:
                    events.saveSettings()
                except Exception:
                    # 存不下也不拦着用户关窗：退出前宿主还会整体存一次
                    pass
            events.emit("closeRequested", "tray" if want_tray else "quit")
            self.parent.close_()


def register():
    """把关闭询问浮层登记进 core.overlays（由 pages/builtin.py 调用一次）。

    用 set 不用 add：这个位子是留出来给人顶掉的 —— 谁想换个问法、换套样式，
    按同名条目 set 一下就把宿主这条盖了（打开它的地方只认 key，见 main.py 的
    close_()），不必改这个文件；将来谁把它换成整页（layer='stack'），
    调用处也一行都不用动。
    """
    registry.set("core.overlays", "core.closeAsk",
                 init=lambda b: AskClose(b.parent),
                 order=30, title="core.wid.closeAsk.title")
