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

插件加载器：发现 → 校验 → 隔离加载 → 登记 → （可）卸载。

插件放哪
--------
    BML/plugins/<插件目录>/
    ├── plugin.json     元信息（id / name / version / api / entry）
    ├── main.py         入口，里面得有一个 Plugin 子类
    ├── lang/*.json     可选，自己的语言包
    └── assets/*        可选，自己的图标

必须在 BML/ 下：src/ 是打包进 exe 的只读解压目录（onefile 下每次运行还换位置），
而 BML/ 在 exe 旁边、可写、跟着启动器一起搬走。

两种形态都收：
    BML/plugins/hello/          一个目录
    BML/plugins/hello.zip       一个压缩包（解压到 BML/.tmp/plugins/ 再按目录加载）
zip 是为了分发方便 —— 下载一个文件丢进 plugins/ 就能用。

两条硬规矩
----------
1. **插件只能 import BMLCore**。import src.* 或 main 会被闸门当场拦下 ——
   内部模块不承诺兼容（这个分支里搬过多少东西），而且顺着 main 能摸到宿主对象。
2. **一个插件坏掉不许拖垮别的**。每个插件单独 try，失败只记进它的 error 字段，
   启动流程照走。宿主整个启动过程本来就包在一个大 try 里，那个分支一进去
   就是「启动失败」弹窗 —— 插件不能有这个权力。
"""

import builtins
import importlib.util
import json
import os
import shutil
import sys
import traceback
import zipfile
from dataclasses import dataclass, field

from .path_utils import getPath

__all__ = ["PluginInfo", "PluginLoadError", "discover", "load_all",
           "unload", "loaded", "plugin_langs", "PLUGIN_DIR", "MANIFEST"]

PLUGIN_DIR = "BML/plugins"
PLUGIN_CACHE = "BML/.tmp/plugins"     # zip 插件的解压落点（跟其他临时文件一个待遇）
MANIFEST = "plugin.json"

# 插件不得触达的顶层模块名（BMLCore 是唯一的合法入口）
FORBIDDEN_ROOTS = ("src", "main")


class PluginLoadError(Exception):
    """清单不合法 / 入口缺失 / 版本不匹配 —— 属于「这个插件不该被加载」。"""


# ─────────────────────────────── 清单 ───────────────────────────────

@dataclass
class PluginInfo:
    """一个插件的清单 + 加载结果。"""

    id: str
    path: str                        # 插件目录
    name: str = ""
    version: str = "0.0.0"
    api: str = "1.x"
    entry: str = "main.py"
    author: str = ""
    description: str = ""

    source: str = ""                # 来自目录还是 zip 文件（界面显示/排查用）
    instance: object = None          # 加载成功后的 Plugin 实例
    error: str = ""                  # 非空 = 加载失败（界面据此标红）

    @property
    def ok(self):
        return self.instance is not None and not self.error

    @property
    def dir_name(self):
        return os.path.basename(self.path)


def _safe_extract(zf, dest):
    """解压前先查一遍路径：zip 里的条目不许跑到 dest 外面去（zip slip）。

    别人给的 zip 里写个 ../../.. 是常见套路，先全查完再解，别边解边发现。
    """
    dest_abs = os.path.abspath(dest)
    for name in zf.namelist():
        target = os.path.abspath(os.path.join(dest, name))
        if target != dest_abs and not target.startswith(dest_abs + os.sep):
            raise PluginLoadError(f"zip 里有越界路径，拒绝解压：{name}")
    zf.extractall(dest)


def _prepare_zip(zip_path, cache_root):
    """把 .zip 插件解压到缓存目录，返回解压后的插件根目录。

    每次发现都重解一遍（先删旧的）：插件很小，这样更新 zip 后自动生效，
    省掉一整套缓存失效判断 —— 而缓存失效搞错的代价是「插件改了没反应」，
    那比多解压几百 KB 难查得多。

    解压目录同时是运行期的插件根：${plugin}/… 与 langs/ 都指向它。
    """
    name = os.path.splitext(os.path.basename(zip_path))[0]
    dest = os.path.join(cache_root, name)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            _safe_extract(zf, dest)
    except zipfile.BadZipFile as e:
        raise PluginLoadError(f"不是有效的 zip：{e}") from None

    # 打包时容易把文件夹一起压进去，多套一层就再往里走一层
    if not os.path.isfile(os.path.join(dest, MANIFEST)):
        subs = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
        if len(subs) == 1 and os.path.isfile(os.path.join(dest, subs[0], MANIFEST)):
            return os.path.join(dest, subs[0])
    return dest


def _read_manifest(folder):
    """读 plugin.json 并校验必填项。"""
    path = os.path.join(folder, MANIFEST)
    if not os.path.isfile(path):
        raise PluginLoadError(f"缺少 {MANIFEST}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise PluginLoadError(f"{MANIFEST} 读不了或不是合法 JSON：{e}") from None
    if not isinstance(data, dict):
        raise PluginLoadError(f"{MANIFEST} 顶层必须是一个对象")

    pid = (data.get("id") or "").strip()
    if not pid:
        raise PluginLoadError("plugin.json 缺少 id")
    # id 同时是注册表命名空间与事件名前缀，含点才谈得上前缀扫描
    if "." not in pid or pid.startswith(".") or pid.endswith("."):
        raise PluginLoadError(f"id {pid!r} 应当是反向域名（如 com.example.hello）")
    if pid.split(".")[0] == "core":
        raise PluginLoadError(f"id {pid!r} 用了保留命名空间 core（内置都在 core.* 下）")

    entry = (data.get("entry") or "main.py").strip()
    return PluginInfo(
        id=pid, path=folder, entry=entry,
        name=(data.get("name") or pid).strip(),
        version=str(data.get("version") or "0.0.0"),
        api=str(data.get("api") or "1.x"),
        author=(data.get("author") or "").strip(),
        description=(data.get("description") or "").strip(),
    )


def _api_ok(want, have):
    """插件声明的 api 范围能不能被当前宿主满足。

    支持三种写法：'1.x'（同主版本即可）、'1.0'（精确）、'>=1.0,<2.0'。
    刻意写得简单 —— 版本约束一旦复杂起来，出错的会是加载器而不是插件。
    """
    want = (want or "").strip()
    have_parts = [int(p) for p in (have.split(".") + ["0", "0"])[:2]]
    if want.endswith(".x"):
        try:
            return int(want[:-2]) == have_parts[0]
        except ValueError:
            return False
    if "," in want or want.startswith((">", "<", "=")):
        for clause in want.split(","):
            clause = clause.strip().lstrip("=")
            op = ""
            for ch in (">=", "<=", ">", "<", "=="):
                if clause.startswith(ch):
                    op, clause = ch, clause[len(ch):].strip()
                    break
            try:
                parts = [int(p) for p in (clause.split(".") + ["0", "0"])[:2]]
            except ValueError:
                return False
            c = (have_parts > parts) - (have_parts < parts)
            if op == ">=" and c < 0: return False
            if op == "<=" and c > 0: return False
            if op == ">" and c <= 0: return False
            if op == "<" and c >= 0: return False
            if op in ("", "==") and c != 0: return False
        return True
    try:
        parts = [int(p) for p in (want.split(".") + ["0", "0"])[:2]]
    except ValueError:
        return False
    return parts == have_parts


# ─────────────────────────── import 闸门 ───────────────────────────

class _SrcImportGuard:
    """加载插件期间禁止 import src.* / main。

    为什么用替换 __import__ 而不是 sys.meta_path：宿主启动时已经把 src.* 装进
    sys.modules 了，meta_path 上的 finder 根本轮不到（import 先查缓存），
    拦不住 `import src.utils.events`。替换 __import__ 是唯一全覆盖的位置。

    只拦绝对 import：插件自己包内的相对 import（level > 0）是它自己的事。
    第三方库（requests 之类）不受影响。
    """

    def __init__(self):
        self._real = None

    def __enter__(self):
        # 启动期单线程，不需要锁；真要多线程加载插件时这里得补一把
        self._real = builtins.__import__
        guard = self

        def _guarded(name, globals=None, locals=None, fromlist=(), level=0):
            if level == 0 and name.split(".")[0] in FORBIDDEN_ROOTS:
                raise ImportError(
                    f"插件不得 import {name!r}：内部模块不承诺兼容，"
                    f"而且顺着 main 能摸到宿主对象。"
                    f"插件请只用 `from BMLCore import Plugin, events, registry`。"
                )
            return guard._real(name, globals, locals, fromlist, level)

        builtins.__import__ = _guarded
        return self

    def __exit__(self, *exc):
        if self._real is not None:
            builtins.__import__ = self._real
            self._real = None
        return False


class _PluginDir:
    """把「当前插件目录」告诉 path_utils，让 ${plugin}/… 能解析。

    只在 exec_module + setup 期间生效：插件要在 setup 里把资源路径取好
    （取到的是绝对路径），运行期再调 getPath 就没有上下文了。
    """

    def __init__(self, path):
        self._path = path

    def __enter__(self):
        from .path_utils import set_plugin_dir
        set_plugin_dir(self._path)
        return self

    def __exit__(self, *exc):
        from .path_utils import set_plugin_dir
        set_plugin_dir(None)
        return False


def plugin_langs(lang):
    """收集已加载插件的语言包：<插件>/langs/<lang>.json。

    按加载顺序合并，**后加载的覆盖先前的** —— 插件因此可以盖掉内置的键
    （想改一句文案，直接在自己的 langs/zh-CN.json 里写那个键就行）。
    坏文件只记日志，不影响其他插件与内置语言。
    """
    out = {}
    for info in _STATE["loaded"]:
        path = os.path.join(info.path, "langs", f"{lang}.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                out.update(data)
            else:
                raise ValueError("顶层必须是对象")
        except Exception as e:
            try:
                from .events import events
                events.logger.error(f"插件语言包读不了：{info.id}/{lang}.json —— {e}",
                                    name="Plugin")
            except Exception:
                pass
    return out


# ─────────────────────────── 发现 / 加载 ───────────────────────────

_STATE = {"loaded": []}


def discover(base=None, cache=None):
    """扫描插件目录，返回清单列表。坏清单也会作为一条（error 非空）返回，
    这样插件管理界面能把它显示出来，而不是「凭空少了一个插件」。

    base / cache 留了参数：测试用临时目录，不必碰真实的 BML/。
    目录与 .zip 两种形态都收。
    """
    base = base or getPath(PLUGIN_DIR)
    cache = cache or getPath(PLUGIN_CACHE)
    found = []
    if not os.path.isdir(base):
        return found
    for name in sorted(os.listdir(base)):
        if name.startswith((".", "_")):
            continue
        full = os.path.join(base, name)
        if os.path.isdir(full):
            try:
                info = _read_manifest(full)
                info.source = full
                found.append(info)
            except PluginLoadError as e:
                found.append(PluginInfo(id=f"<{name}>", path=full, error=str(e)))
        elif name.lower().endswith(".zip") and os.path.isfile(full):
            try:
                root = _prepare_zip(full, cache)
                info = _read_manifest(root)
                info.source = full
                found.append(info)
            except PluginLoadError as e:
                found.append(PluginInfo(id=f"<{name}>", path=full, source=full, error=str(e)))
            except Exception as e:
                found.append(PluginInfo(id=f"<{name}>", path=full, source=full,
                                        error=f"解压失败：{e}"))
    return found


def _find_plugin_class(mod, entry_name):
    """在入口模块里找 Plugin 子类。"""
    from ..BMLCore import Plugin
    for attr, obj in vars(mod).items():
        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
            return obj
    raise PluginLoadError(f"{entry_name} 里找不到 Plugin 子类")


def load_one(info):
    """加载单个插件。任何异常都被吞进 info.error，不往外抛。"""
    from ..BMLCore import API_VERSION

    if info.error:
        return info

    if not _api_ok(info.api, API_VERSION):
        info.error = (f"要求 API {info.api}，当前宿主是 {API_VERSION}；"
                      f"请更新插件或改用兼容的 api 声明")
        return info

    entry_path = os.path.join(info.path, info.entry)
    if not os.path.isfile(entry_path):
        info.error = f"入口文件不存在：{info.entry}"
        return info

    mod_name = "bml_plugin_" + info.id.replace(".", "_")
    try:
        with _SrcImportGuard(), _PluginDir(info.path):
            spec = importlib.util.spec_from_file_location(mod_name, entry_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"无法为 {info.entry} 建立模块规格")
            mod = importlib.util.module_from_spec(spec)
            # 先登记进 sys.modules：插件自己的模块级代码里若互相 import 才找得到
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            cls = _find_plugin_class(mod, info.entry)
            inst = cls()
            # 清单与类上都有 id 时以清单为准（清单才是加载器认的那个）
            inst.id = info.id
            inst.setup()
    except Exception:
        info.error = traceback.format_exc(limit=6)
        sys.modules.pop(mod_name, None)
        return info

    info.instance = inst
    return info


def _expose_api():
    """把 BMLCore 挂成顶层模块名，插件才 import 得到它。

    BMLCore 本体住在 src/BMLCore/ 下（会随 exe 一起编译），而插件是 exe 外
    的独立 .py —— 它的 sys.path 里没有 src/，`from BMLCore import ...` 会直接
    找不到。这里显式暴露一个顶层名字：插件只认这一个入口，正是我们想要的。

    （它不在闸门的禁止名单里 —— 闸门只拦 src.* 和 main。）
    """
    if "BMLCore" in sys.modules:
        return sys.modules["BMLCore"]
    from .. import BMLCore
    sys.modules["BMLCore"] = BMLCore
    return BMLCore


def load_all(base=None):
    """发现并加载全部插件，返回清单列表（含失败项）。

    必须是「逐个隔离」：一个插件坏掉只写进它自己的 error，
    绝不向外抛 —— 宿主启动流程整个包在一个大 try 里，抛出去就是启动失败弹窗。
    """
    from .registry import registry
    from .events import events

    _expose_api()
    infos = discover(base)
    for info in infos:
        load_one(info)
        if info.ok:
            events.logger.info(f"插件已加载：{info.id} v{info.version}", name="Plugin")
        else:
            # 只记第一行，完整 traceback 留在 info.error 里给插件管理界面看
            head = (info.error or "").strip().splitlines()[-1:]
            events.logger.error(
                f"插件加载失败：{info.id} —— {head[0] if head else info.error}",
                name="Plugin")
    _STATE["loaded"] = [i for i in infos if i.ok]
    return infos


def loaded():
    """当前加载成功的插件。"""
    return list(_STATE["loaded"])


def unload(info):
    """卸载一个插件：摘注册项 → 摘事件 → teardown。

    顺序有讲究：先摘登记（界面可能还在，条目先消失总比指向已销毁的对象好），
    再摘事件，最后才让插件做自己的清理。
    """
    from .registry import registry
    from .events import events

    if not info.ok:
        return False
    try:
        registry.remove_namespace(info.id)
        events.drop_namespace(info.id)
    except Exception:
        events.logger.error(f"插件卸载时摘登记失败：{info.id}\n{traceback.format_exc(limit=4)}",
                            name="Plugin")
    try:
        info.instance.teardown()
    except Exception:
        events.logger.error(f"插件 teardown 抛异常：{info.id}\n{traceback.format_exc(limit=4)}",
                            name="Plugin")
    info.instance = None
    _STATE["loaded"] = [i for i in _STATE["loaded"] if i.id != info.id]
    return True
