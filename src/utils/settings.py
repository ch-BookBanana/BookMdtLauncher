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
    "closeByTray": True,
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
    # 插件设置：一格一个插件（com.example.hello: {...}）。
    # 空 dict 是「开放映射」—— 键由插件自己定，宿主没法定 schema，
    # 见 _merge 里对空 dict 默认值的处理。
    "plugins": {},
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
        """只保留最近 keep_backups 份，避免目录堆积（文件名按时间戳排序即时间序）。"""
        try:
            folder = getPath(self.backup_dir)
            names = sorted(n for n in os.listdir(folder)
                           if n.startswith("settings.") and n.endswith(".json"))
            for name in names[:-self.keep_backups]:
                os.remove(os.path.join(folder, name))
        except Exception:
            pass
