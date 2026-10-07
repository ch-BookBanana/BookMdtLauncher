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
    ├── manifest.toml   元信息（id / name / version / api / entry / dependencies）
    │                   （旧格式 plugin.json 也认）
    ├── main.py         入口，里面得有一个 Plugin 子类
    ├── *.py            可选，自己的模块：用相对导入拿（from . import widgets）
    ├── libs/           可选，自带的第三方依赖（纯 Python 的放这儿就能 import）
    ├── langs/*.json    可选，自己的语言包（文件名就是语言码）
    └── assets/*        可选，自己的图标

插件目录本身是一个**真包**：加载后就是 `bmlplugin.<id>`，目录里的 .py 是它的子模块
（`bmlplugin.<id>.widgets`）。所以：

  * 插件内部用相对导入（`from . import widgets`），不必把目录塞进 sys.path ——
    那条路径是全局的，两个插件都带 utils.py 时会互相撞，且一声不吭；
  * 别的插件要拿它的代码就是 `from bmlplugin.<id> import Widgets`（清单里先声明
    dependencies），拿到的是**实名**的那一份，不是「碰巧先加载的那个」。

必须在 BML/ 下：src/ 是打包进 exe 的只读解压目录（onefile 下每次运行还换位置），
而 BML/ 在 exe 旁边、可写、跟着启动器一起搬走。

两种形态都收：
    BML/plugins/hello/          一个目录
    BML/plugins/hello.zip       一个压缩包（解压到 BML/.tmp/plugins/ 再按目录加载）
zip 是为了分发方便 —— 下载一个文件丢进 plugins/ 就能用。

依赖与加载日志
--------------
清单里的 dependencies 写「依赖哪些插件 id」（数组；只有一个时写字符串也认）。
加载一个插件前先把它的依赖拉起来 —— 依赖也在 BML/plugins 里，找不到就算这个
插件加载失败，不静默跳过（少一个依赖却照常跑起来，坏的是几层之外的表现）。

日志按「谁在等谁」打，依赖先起来：

    [example_a]开始加载
    [example_b]开始加载      ← 依赖走同一套，递归进来说
    [example_b]加载完成
    [example_a]加载完成

已经起来的、以及正在这条链上的（成环），都不会再打一遍「开始加载」。
失败打 [id]加载失败:\n<traceback>；缺依赖、依赖成环、清单不合法这类没有
traceback，就写原因 —— 格式一样，排查时不必分两种读法。

插件失败之后
--------------
**登记的是全有或全无**：插件写注册表走一次加载会话（见 registry.begin/commit/abort），
构造跑到一半抛异常就整块丢掉 —— 不会在正表里留下半截条目（那会让界面冒出点不动
的项，重试还撞「已存在条目」），连它自己 declare 出来的扩展点也一起消失。

会话管不到的另外两样由加载器自己收：
  * 事件订阅 —— 不在注册表里，按命名空间摘一遍；
  * on_close —— 构造可能只做了一半，尽力试一次，抛什么都吞掉。

**插件盖过的东西，卸载/失败后对账回来**：语言包、样式片段（core.qss）、托盘菜单项、
页面（左栏按钮与三栏控件）、设置页里由插件条目建出来的那一组。做法是加载器发一条
plugins_changed，宿主收到后重载语言、重收样式、重建托盘、按 core.pages 与
core.setting.sections 对账 —— 这些都不在注册表里，光摘条目它们不会自己回去。

**滚不回来的两处**（已知限制，不是忘了做）：
  * 卸载时**正开着**的插件浮层：它由宿主挂在叠层上，条目没了也没人把它关掉；
  * 插件运行期自己往宿主页面里塞的控件：它没经扩展点登记，也就没人认领。

两条硬规矩
----------
1. **插件只该 import BMLCore**。import src.* 或 main 会被闸门当场拦下 ——
   内部模块不承诺兼容（这个分支里搬过多少东西），而且顺着 main 能摸到宿主对象。
   闸门挡的是**加载期**走 `import` 语句的那些：`importlib.import_module("src.…")`
   与推迟到运行期的导入它拦不住（`sys.modules` 更是直接就能取）。它是一道
   「别这么写」的提示，不是沙箱 —— 插件代码是用户自己装进来的，本来就信任它。
2. **一个插件坏掉不许拖垮别的**。每个插件单独 try，失败只记进它的 error 字段，
   启动流程照走。宿主整个启动过程本来就包在一个大 try 里，那个分支一进去
   就是「启动失败」弹窗 —— 插件不能有这个权力。
"""

import builtins
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sys
import traceback
import types
import zipfile
from dataclasses import dataclass, field

from .path_utils import getPath

__all__ = ["PluginInfo", "PluginLoadError", "discover", "load_all", "load_one",
           "unload", "loaded", "state", "enable", "disable", "disabled_ids",
           "langs_revision", "ensure_dirs", "plugin_langs", "PLUGIN_DIR",
           "PLUGIN_CACHE", "MANIFEST", "MANIFEST_JSON"]

PLUGIN_DIR = "BML/plugins"
PLUGIN_CACHE = "BML/.tmp/plugins"
PLUGIN_DATA = "BML/pluginData"
# 加载期给插件加进 sys.path 的目录：{插件 id: [那几条路径]}（卸载时按 id 摘掉）
_PLUGIN_PATHS = {}
# 上次加载失败、已标注停用的插件 id 列表（存在设置里，要活过一次启动）
DISABLED_KEY = "disabledPlugins"
MANIFEST = "manifest.toml"        # 首选（NcatBot 那套）
MANIFEST_JSON = "plugin.json"     # 旧格式，继续认

# 插件 id 的字符规约：与 Python 的包 / 模块名同一套 —— 字母、数字、下划线，
# 且首字符是字母（数字开头不是合法标识符，当不了包名）。
#
# 为什么不用反向域名那种带点的写法：这个 id 要兼四件事 —— 注册表命名空间、
# 事件名前缀、插件私有目录名，以及**模块名 / import 别名**（bmlplugin.<id>）。
# 带点就只当得成前三样，第四样得一路 `replace(".", "_")` 猜；两种写法并存，
# 迟早对不上。限制成标识符之后，id 与它落成的包名、模块名是同一个字符串。
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 不能用的 id：core 是内置命名空间，其余是加载器/宿主自己要占的名字
RESERVED_IDS = ("core", "src", "main", "bmlcore", "bmlplugin", "bml_plugin")

# 插件包的根：插件加载后就是 `bmlplugin.<id>`，它自己的模块是 `bmlplugin.<id>.<模块>`。
# 好处是「实名」—— 别的插件要拿它的类就 from bmlplugin.<id> import X，
# 不必靠 sys.path 上那条全局路径撞名字（两个插件都带 utils.py 就不会打架了）。
PACKAGE_ROOT = "bmlplugin"

# 插件不得触达的顶层模块名（BMLCore 是唯一的合法入口）
FORBIDDEN_ROOTS = ("src", "main")


class PluginLoadError(Exception):
    """清单不合法 / 入口缺失 / 版本不匹配 —— 属于「这个插件不该被加载」。"""


def _fmt_exc(limit=6):
    """把当前异常格式化成字符串 —— 连格式化都炸时退回最朴素的写法。

    why：traceback 要回读源码（linecache），而取源码本身还要 import。崩的若是
    import 机制（比如 builtins.__import__ 被搞成了不能调的东西），格式化就会
    二次崩溃，于是「一个插件加载失败」升级成「宿主启动失败」，连启动失败弹窗
    都弹不出来（它也要 format_exc）。
    """
    orig = sys.exc_info()[1]
    try:
        return traceback.format_exc(limit=limit)
    except BaseException:
        pass
    if orig is None:
        return "（异常信息也取不到了）"
    try:
        return "".join(traceback.format_exception_only(type(orig), orig))
    except BaseException:
        return "%s: %s" % (type(orig).__name__, orig)


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
    entry_class: str = ""          # 清单里的 entry_class（缺省自动发现）
    author: str = ""
    description: str = ""
    dependencies: tuple = ()         # 依赖的插件 id（清单里的 dependencies）

    source: str = ""                # 来自目录还是 zip 文件（界面显示/排查用）
    disabled: bool = False           # 被标注停用（上次加载失败，见 disabled_ids）
    instance: object = None          # 加载成功后的 Plugin 实例
    error: str = ""                  # 非空 = 加载失败（界面据此标红）
    reported: bool = field(default=False, repr=False)   # 失败日志是否已打过


    @property
    def ok(self):
        return self.instance is not None and not self.error

    @property
    def dir_name(self):
        return os.path.basename(self.path)


# zip 解压的两道上限：分发形态鼓励「下一个 zip 丢进 plugins/ 就能用」，
# 而 zip 头部声明的解压后体积是可以随便写的 —— 一个几十 KB 的 zip 能铺满磁盘。
ZIP_MAX_BYTES = 64 * 1024 * 1024      # 解压后总字节
ZIP_MAX_FILES = 2000                  # 条目数


def _safe_extract(zf, dest):
    """解压前先查一遍：路径不许跑到 dest 外面去（zip slip），体积也不许离谱。

    别人给的 zip 里写个 ../../.. 是常见套路；同理，`file_size` 声明成几百 MB
    的条目也是。两者都在解压**之前**全查完，别边解边发现。
    """
    dest_abs = os.path.abspath(dest)
    infos = zf.infolist()
    if len(infos) > ZIP_MAX_FILES:
        raise PluginLoadError(
            f"zip 里条目太多（{len(infos)} > {ZIP_MAX_FILES}），拒绝解压")
    total = 0
    for info in infos:
        target = os.path.abspath(os.path.join(dest, info.filename))
        if target != dest_abs and not target.startswith(dest_abs + os.sep):
            raise PluginLoadError(f"zip 里有越界路径，拒绝解压：{info.filename}")
        total += max(0, info.file_size)
        if total > ZIP_MAX_BYTES:
            raise PluginLoadError(
                f"zip 解压后超过上限（> {ZIP_MAX_BYTES // (1024 * 1024)}MB），"
                f"拒绝解压")
    zf.extractall(dest)


def _prepare_zip(zip_path, cache_root):
    """把 .zip 插件解压到缓存目录，返回解压后的插件根目录。

    每次发现都重解一遍（先删旧的）：插件很小，这样更新 zip 后自动生效，
    省掉一整套缓存失效判断 —— 而缓存失效搞错的代价是「插件改了没反应」，
    那比多解压几百 KB 难查得多。

    **例外**：这个目录同时是运行期的插件根（`${plugin}/…`、`langs/` 都指着它），
    所以正在被某个已加载插件用着的时候**一个字都不动** —— 否则每次刷新插件列表
    都会把它 rmtree 重建：插件写在自己目录里的东西没了，zip 恰好被删/改名时
    语言包与资源还会当场失效，而界面上一声不吭。
    """
    name = os.path.splitext(os.path.basename(zip_path))[0]
    dest = os.path.join(cache_root, name)
    if any(os.path.abspath(i.path) == os.path.abspath(dest)
           for i in _STATE["loaded"]):
        return dest
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            _safe_extract(zf, dest)
    except zipfile.BadZipFile as e:
        raise PluginLoadError(f"不是有效的 zip：{e}") from None

    # 打包时容易把文件夹一起压进去，多套一层就再往里走一层
    if manifest_path(dest) is None:
        subs = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
        if len(subs) == 1 and manifest_path(os.path.join(dest, subs[0])) is not None:
            return os.path.join(dest, subs[0])
    return dest


def manifest_path(folder):
    """清单文件在哪：manifest.toml 优先，退回 plugin.json；都没有返回 None。"""
    for name in (MANIFEST, MANIFEST_JSON):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def _read_manifest(folder):
    """读 plugin.json 并校验必填项。"""
    path = manifest_path(folder)
    if path is None:
        raise PluginLoadError(f"缺少 {MANIFEST}（或旧的 {MANIFEST_JSON}）")
    try:
        if path.endswith(".toml"):
            import tomllib
            with open(path, "rb") as f:
                data = tomllib.load(f)
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception as e:
        raise PluginLoadError(
            f"{os.path.basename(path)} 读不了或不是合法清单：{e}") from None
    if not isinstance(data, dict):
        raise PluginLoadError(f"{MANIFEST} 顶层必须是一个对象")

    # 每个字段都过一遍 _text()：清单是**别人写的文件**，里面出现什么类型都不奇怪
    # （id 写成数字、name 写成数组…）。这里一律收成字符串或当场报 PluginLoadError ——
    # 直接 .strip() 会在字段是数字时抛 AttributeError，而那是**非清单错误**，
    # 会穿出 discover() 直达启动流程的顶层，表现成「启动失败」弹窗：
    # 一个坏插件因此有了拖垮启动的权力，这条底线不能被清单格式破掉。
    base = os.path.basename(path)
    pid = _text(data.get("id"), "id", base)
    if not pid:
        raise PluginLoadError(f"{base} 缺少 id")
    # id 同时是包名 / 模块名，所以只能是标识符（见 ID_RE 的说明）
    if not ID_RE.match(pid):
        raise PluginLoadError(
            f"id {pid!r} 不合法：只能用字母、数字与下划线，且首字符是字母"
            f"（如 example_hello）。id 会当作包名用，所以不接受点号与短横线")
    if pid.lower() in RESERVED_IDS:
        raise PluginLoadError(f"id {pid!r} 是保留名（{'、'.join(RESERVED_IDS)}）")

    deps = data.get("dependencies") or []
    if isinstance(deps, str):
        deps = [deps]                      # 只依赖一个时写字符串也认
    if not isinstance(deps, list):
        raise PluginLoadError(f"{base} 的 dependencies 必须是数组")
    bad = [d for d in deps if not isinstance(d, str)]
    if bad:
        # 不能 str() 了事：null 会变成 "None"、数字会变成 "123"，
        # 而它们都是「查不到的依赖名」—— 失败会发生在很远的地方
        raise PluginLoadError(f"{base} 的 dependencies 里只能是字符串，收到 {bad!r}")
    deps = tuple(dict.fromkeys(d.strip() for d in deps if d.strip()))
    if pid in deps:
        raise PluginLoadError(f"依赖了自己：{pid}")

    entry = _text(data.get("entry"), "entry", base) or \
        _text(data.get("main"), "main", base) or "main.py"
    # 入口必须是插件目录里的裸文件名：带路径分隔符就可能是「跑到目录外面去」
    if entry != os.path.basename(entry) or entry.startswith("."):
        raise PluginLoadError(
            f"{base} 的入口文件名 {entry!r} 不合法：只能是插件目录里的文件名")
    return PluginInfo(
        id=pid, path=folder, entry=entry,
        entry_class=_text(data.get("entry_class"), "entry_class", base),
        name=_text(data.get("name"), "name", base) or pid,
        version=_text(data.get("version"), "version", base) or "0.0.0",
        api=_text(data.get("api"), "api", base) or "1.x",
        author=_text(data.get("author"), "author", base),
        description=_text(data.get("description"), "description", base),
        dependencies=deps,
    )


def _text(value, field, where):
    """清单字段 → 去掉首尾空白的字符串；类型不对就报清单错误。

    字符串 / 数字 / 布尔都收（`version = 1.0` 这种写法很自然），其余（数组、
    对象、null 归空串）一律报 PluginLoadError。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    raise PluginLoadError(f"{where} 的 {field} 只能是字符串，收到 {type(value).__name__}")


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

# importlib.__import__ 就是内建 import 的实现本身，不经过任何第三方钩子
# （PySide6 会用 __feature_import__ / __lazy_import__ 顶掉 builtins.__import__）。
# 只在闸门拿不到可用转交对象时兜底用，正常路径用不上。
_STD_IMPORT = importlib.__import__


class _SrcImportGuard:
    """加载插件期间禁止 import src.* / main。

    为什么用替换 __import__ 而不是 sys.meta_path：宿主启动时已经把 src.* 装进
    sys.modules 了，meta_path 上的 finder 根本轮不到（import 先查缓存），
    拦不住 `import src.utils.events`。替换 __import__ 是唯一全覆盖的位置。

    只拦绝对 import：插件自己包内的相对 import（level > 0）是它自己的事。
    第三方库（requests 之类）不受影响。

    **装上去的那个闭包必须永远「能调用」** —— 这是踩过的坑：换掉的是全局
    builtins.__import__，别人也会伸手（PySide6 的 post_init 就在换同一个全局，
    而它是 C 函数，出问题时栈里连一帧都留不下）。第一版把「转交给谁」写成读
    self._real、退出时置 None，于是只要有人攥着这个闭包、或在退出之后又把它装
    回去，下一次 import 就是 `TypeError: 'NoneType' object is not callable`,
    而那是**宿主启动阶段**——启动器整个没了，连「启动失败」弹窗都弹不出来
    （弹窗要 format_exc，format_exc 要 import）。

    所以：转交对象在装上那一刻就绑死进闭包（默认参数，之后不再变），闸门
    「还开不开」另放一个可变 cell。退出之后这个闭包只是**不再拦**，绝不再崩。
    """

    def __init__(self):
        self._prev = None       # 进来时那一个：退出时还原给它
        self._mine = None       # 我们自己装上去的闭包，用来判断「还挂着吗」
        self._state = None

    def __enter__(self):
        # 启动期单线程，不需要锁；真要多线程加载插件时这里得补一把
        prev = builtins.__import__
        if not callable(prev):
            prev = _STD_IMPORT
        state = {"active": True}
        self._prev, self._state = prev, state

        def _guarded(name, globals=None, locals=None, fromlist=(), level=0,
                     _prev=prev, _state=state):
            if _state["active"] and level == 0 and name.split(".")[0] in FORBIDDEN_ROOTS:
                raise ImportError(
                    f"插件不得 import {name!r}：内部模块不承诺兼容，"
                    f"而且顺着 main 能摸到宿主对象。"
                    f"插件请只用 `from BMLCore import Plugin, events, registry`。"
                )
            return _prev(name, globals, locals, fromlist, level)

        self._mine = _guarded
        builtins.__import__ = _guarded
        return self

    def __exit__(self, *exc):
        # 先关闸：即使下面不还原，这个闭包也只是穿透，不再拦也不炸
        if self._state is not None:
            self._state["active"] = False
        # 只在自己的闭包还挂着时还原。中途被别人顶掉过就随它去 —— 跟别人抢
        # 同一个全局正是这次崩溃的由来（我们退出时把它装的钩子又踩了回去）。
        if self._mine is not None and builtins.__import__ is self._mine:
            builtins.__import__ = self._prev
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


class _Host:
    """交给插件的显式句柄：工具都在这个对象上，self 上的同名助手只是转发。

    每次加载现建一个（带 id 与自己的目录），卸载后它跟着插件实例一起走。
    """

    def __init__(self, info):
        self.id = info.id
        self.plugin_dir = info.path
        self.data_dir = os.path.join(PLUGIN_DATA, info.id)

    @property
    def logger(self):
        from .events import events
        return events.logger

    @property
    def lang(self):
        from .events import events
        return events.lang

    @property
    def events(self):
        from .events import events
        return events

    @property
    def registry(self):
        from .registry import registry
        return registry

    def log(self, msg, level="info"):
        target = self.logger
        getattr(target, level, target.info)(f"[{self.id}] {msg}")

    def path(self, rel=""):
        """插件目录里的文件 → 绝对路径（整棵子树都是自己的，随便取）。"""
        return os.path.join(self.plugin_dir, *str(rel).split("/")) if rel else self.plugin_dir

    def workspace(self):
        """私有目录（不存在就建），跨 zip 重装也还在。"""
        os.makedirs(self.data_dir, exist_ok=True)
        return self.data_dir

def _add_plugin_paths(info):
    """把 <插件>/libs 加进 sys.path（插件自带的第三方依赖落这儿）。

    以前这里还会把 <插件> 本身也塞进去，好让插件直接 `import 同目录的模块`。
    现在不需要了：插件目录本身就是一个真包（`bmlplugin.<id>`，见 load_one），
    自己的模块用相对导入拿 —— 那个是**实名**的，而 sys.path 上那条是全局的：
    两个插件都带 utils.py 时，谁先加载谁赢，且一声不吭。
    """
    added = []
    libs = os.path.join(info.path, "libs")
    if os.path.isdir(libs) and libs not in sys.path:
        sys.path.insert(0, libs)
        added.append(libs)
    if added:
        _PLUGIN_PATHS[info.id] = added


def _drop_plugin_paths(info):
    """卸载时把自己加的那几条 sys.path 摘掉。"""
    for path in _PLUGIN_PATHS.pop(info.id, ()):
        try:
            sys.path.remove(path)
        except ValueError:
            pass


def _drop_plugin_modules(info):
    """卸载时把插件的包从 sys.modules 里摘掉（连同它的子模块）。

    不摘的话：① `bmlplugin.<id>` 还留着旧模块对象，重装插件时 import 拿到的
    是上一次那份代码；② 子模块（`bmlplugin.<id>.widgets`）也一起陈旧。
    摘干净之后，重装的插件是全新的一份 —— 别的插件手里那些旧引用仍然指向旧
    代码（这是 import 的固有代价，文档里写明了）。
    """
    prefix = f"{PACKAGE_ROOT}.{info.id}"
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
        sys.modules.pop(name, None)


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

# 加载状态机：三张表就是全部状态，别处不再各留一份
#   pending  未加载：已发现、还没轮到（load_all 从它取活，取走就移出）
#   loading  加载中：正在加载的那条链，**有序** —— 报成环时从这儿截
#   loaded   已加载：加载成功的，按加载顺序（plugin_langs 靠它决定谁盖谁的文案）
# 三张表都存 PluginInfo；失败的不进 loaded，失败原因在 info.error 上。
_STATE = {"pending": [], "loading": [], "loaded": []}

# 一批加载的深度：>0 时 _notify_changed 只记账不发（load_all 自己会在末尾收口）。
# 一批中间可能失败、回滚好几回，每回都让宿主重读语言、重建样式表纯属白干。
_BATCH = 0

# 插件语言包相关状态的版本号：已加载集合一变就 +1。Langer 拿它当「要不要重读
# 语言表」的输入之一 —— 语言没变、插件集合也没变，就不该重读、更不该再广播。
_LANGS_REV = 0

# 上次通知时「已加载」长什么样：没它就得无条件 +1，于是一个插件都没有的启动
# 也会被当成「语言包变了」，白读一遍语言。
_LAST_NOTIFIED_IDS = ()


def langs_revision():
    """插件语言包相关状态的版本号（每次插件集合变化 +1）。"""
    return _LANGS_REV


def _batch_begin():
    global _BATCH
    _BATCH += 1


def _batch_end():
    global _BATCH
    if _BATCH:
        _BATCH -= 1


def begin_batch():
    """把一批插件改动收成**一次**通知。成对操作用（重载 = 先全卸再全装）。

    不包起来的话，宿主每卸一个插件就要重读语言、重建整张样式表、重建托盘菜单、
    对账页面 —— 三个插件就是四次全量重算，重载时肉眼可见地闪与卡。
    """
    _batch_begin()


def end_batch():
    """收口这一批：集合稳定之后再通知一次。"""
    _batch_end()
    _notify_changed()


def ensure_dirs(base=None):
    """建好插件目录。

    由宿主在启动时调一次，路径只有 PLUGIN_DIR 这一个出处 —— 原先目录名在
    这里、建目录的代码却在 main.py 里又写了一遍字面量，改一处忘一处就是
    「插件全没了却一声不吭」（discover 发现目录不存在只返回空表）。
    """
    os.makedirs(base or getPath(PLUGIN_DIR), exist_ok=True)


def discover(base=None, cache=None):
    """扫描插件目录，返回清单列表。坏清单也会作为一条（error 非空）返回，
    这样插件管理界面能把它显示出来，而不是「凭空少了一个插件」。

    base / cache 留了参数：测试用临时目录，不必碰真实的 BML/。
    目录与 .zip 两种形态都收。

    每个插件单独 try，而且**接的是 Exception 不是 PluginLoadError**：
    清单是别人写的文件、目录里放什么都有可能，校验里任何一处没想到的类型都
    不该有「穿出去」的权力 —— 那会直达启动流程的顶层，表现成启动失败弹窗。
    条目自己的报错（PluginLoadError）原样显示，其余异常带上异常类型一同显示。
    """
    base = base or getPath(PLUGIN_DIR)
    cache = cache or getPath(PLUGIN_CACHE)
    found = []
    if not os.path.isdir(base):
        return found

    def _bad(name, full, e, source=None):
        if isinstance(e, PluginLoadError):
            why = str(e)
        else:
            why = f"{type(e).__name__}: {e}"
        return PluginInfo(id=f"<{name}>", path=full, source=source or full, error=why)

    for name in sorted(os.listdir(base)):
        if name.startswith((".", "_")):
            continue
        full = os.path.join(base, name)
        if os.path.isdir(full):
            try:
                info = _read_manifest(full)
                info.source = full
                found.append(info)
            except Exception as e:
                found.append(_bad(name, full, e))
        elif name.lower().endswith(".zip") and os.path.isfile(full):
            try:
                root = _prepare_zip(full, cache)
                info = _read_manifest(root)
                info.source = full
                found.append(info)
            except Exception as e:
                found.append(_bad(name, full, e, source=full))

    # 同一个 id 出现两次：以前是 by_id 里后一个盖掉前一个，于是有一个插件
    # 「凭空没加载」而且一声不吭。id 现在短了，撞名的机会更大，所以两个都标错。
    seen = {}
    for info in found:
        if info.error:
            continue
        other = seen.get(info.id)
        if other is None:
            seen[info.id] = info
            continue
        for dup in (other, info):
            dup.error = (f"id 与另一个插件重复：{info.id}"
                         f"（{os.path.basename(other.path)} 与 {os.path.basename(info.path)}）")
    return found


def _find_plugin_class(mod, entry_name, entry_class=""):
    """在入口模块里找插件类：只认**本文件自己定义**的，多个时取最派生那个。

    为什么要卡 `__module__`：插件里写了 `from BMLCore import BMLPlugin` 之后，
    BMLPlugin 本身就是「模块里的一个 Plugin 子类」—— 照 vars(mod) 顺序取第一个，
    拿到的是它，插件本体的装饰器一个都收不到（曾经真踩过）。
    """
    from ..BMLCore import Plugin
    if entry_class:                       # 清单点名的就直接取它
        obj = getattr(mod, entry_class, None)
        if not (isinstance(obj, type) and issubclass(obj, Plugin)):
            raise PluginLoadError(
                f"{entry_name} 里找不到 entry_class = {entry_class!r}"
                f"（要是 Plugin 子类）")
        return obj
    cands = [obj for obj in vars(mod).values()
             if isinstance(obj, type) and issubclass(obj, Plugin)
             and obj is not Plugin and obj.__module__ == mod.__name__]
    if not cands:
        raise PluginLoadError(f"{entry_name} 里找不到 Plugin 子类（要定义在本文件里）")
    cands.sort(key=lambda c: len(c.__mro__), reverse=True)      # 最派生
    return cands[0]


def _accepts_host(cls):
    """这个插件类能不能收下 host 参数（旧写法是 `__init__(self)` 无参构造）。

    用签名判断，而不是「先按新写法调、撞 TypeError 再退回旧写法」那种兜底：
    插件构造里自己抛的 TypeError 会被误判成「签名不对」，于是真实原因被第二次
    调用的报错顶掉（还可能把插件构造两遍，副作用翻倍）。
    """
    try:
        params = inspect.signature(cls).parameters.values()
    except (TypeError, ValueError):     # 签名拿不到（C 实现之类）：按新写法试
        return True
    kinds = (inspect.Parameter.POSITIONAL_ONLY,
             inspect.Parameter.POSITIONAL_OR_KEYWORD,
             inspect.Parameter.VAR_POSITIONAL)
    return any(p.kind in kinds for p in params)


def _drop_plugin_events(info):
    """摘插件的事件：它命名空间下的名字 + 它订的**别人的**名字。

    两条都要做。只按 `<id>.` 前缀摘的话，插件订的那些宿主事件（`plugins_changed`
    之类，正是文档教的写法）会留下来 —— 卸载之后它的回调还在被叫（控件已经销毁），
    而且每重载一次多挂一份，一次广播被响应好几次。
    """
    from .events import events

    n = 0
    try:
        n += events.off_owner(info.id)
    except Exception as e:
        events.logger.error(f"摘插件订阅失败：{info.id}\n{_fmt_exc(limit=4)}", name="Plugin")
    try:
        n += events.drop_namespace(info.id)
    except Exception as e:
        events.logger.error(f"摘插件事件名失败：{info.id}\n{_fmt_exc(limit=4)}", name="Plugin")
    return n


def _abort_session(info, token, why=""):
    """关掉本次加载会话（失败路径）。

    会话凭据攥在 load_one 手里：插件自己在构造里 abort()/commit() 是关不掉的，
    所以这里正常能关；万一凭据对不上（有别的代码动过会话），退回按命名空间清一遍
    —— 无论如何不能让半截登记留在正表里，也不能让会话一直开着（开着的话之后谁都
    开不了新会话，只有重启能救）。
    """
    from .registry import registry

    try:
        return registry.abort(token)
    except Exception:
        # 凭据对不上（有别的代码动过会话）：强行关掉，再按命名空间把它的条目清掉。
        # 会话绝不能留着 —— 留着的话之后谁都开不了新会话，只有重启能救。
        try:
            registry.abort(force=True)
        except Exception:
            pass
        try:
            n = registry.remove_namespace(info.id) if info.id else 0
        except Exception:
            n = 0
        try:
            from .events import events
            events.logger.error(
                f"[{info.id}]加载会话状态异常，已按命名空间清理 {n} 条"
                f"（通常是有代码在插件构造期直接动了注册表会话）：{why}",
                name="Plugin")
        except Exception:
            pass
        return n


def load_one(info):
    """加载单个插件本身（**不解析依赖、不打进度日志**）。

    它是最底层那一步：导入入口、找 Plugin 子类、实例化、setup()。
    任何异常都被吞进 info.error，不往外抛。公开给测试与「手动装一个」用；
    正常启动走 load_all，依赖与日志都在那一层。
    """
    from ..BMLCore import API_VERSION
    from .registry import registry

    # 插件是 `bmlplugin.<id>` 这个包里的模块，包根得先在 sys.modules 里，
    # 否则插件自己的相对导入（from . import x）会找不到父包。
    _expose_api()

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

    # 同一个 id 已经装着一份，就别再装第二份：第二次会因为「条目已存在」失败，
    # 而失败路径会把**第一份（还活着的那份）**的事件、包、控件台账一起拆掉，
    # 第一份却仍然报 ok 还留在 loaded 表里 —— 一个自相矛盾的残局。
    for old in _STATE["loaded"]:
        if old.id == info.id:
            info.error = (f"{info.id} 已经加载着（{old.path}）；"
                          f"要重装先 unload 它")
            return info

    # 模块名就是包名：插件目录即一个真包（bmlplugin.<id>），入口文件是它的顶层模块。
    # 于是插件自己的模块可以用相对导入（from . import widgets），别的插件则可以
    # from bmlplugin.<id> import Widgets —— 都是实名的，不靠 sys.path 上的路径。
    mod_name = f"{PACKAGE_ROOT}.{info.id}"
    inst = None
    # 先记下当前有哪些控件：插件跑完（或炸掉）之后，多出来的就是它造的
    widgets_before = _widget_snapshot()
    # 登记走一次**加载会话**：插件写进暂存区，跑完才并进正表。
    # 这样「构造跑到一半抛异常」不会在正表里留下半截条目（界面会冒出点不动
    # 的项，重试还撞「已存在条目」）—— 而且不必靠事后按命名空间去擦。
    # 会话的主人也在这里告诉注册表：插件顶掉别人条目时，归属才认得出是谁。
    # 凭据（token）攥在自己手里：有主人的会话只有拿着它的一方关得掉，
    # 插件在构造里随手 registry.abort() 是关不掉的（关掉了的话，这里「失败整块
    # 舍弃」的那一下就成了空操作，半截条目会留在正表里）。
    token = registry.begin(info.id)
    try:
        _add_plugin_paths(info)
        with _SrcImportGuard(), _PluginDir(info.path):
            # submodule_search_locations 给上插件目录：这个入口模块于是同时是个包，
            # 插件自己的 .py 用 `from . import x` 就找得到（不必动 sys.path）。
            spec = importlib.util.spec_from_file_location(
                mod_name, entry_path, submodule_search_locations=[info.path])
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"无法为 {info.entry} 建立模块规格")
            mod = importlib.util.module_from_spec(spec)
            # 先登记进 sys.modules：插件自己的模块级代码里若互相 import 才找得到
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            cls = _find_plugin_class(mod, info.entry, info.entry_class)
            host = _Host(info)
            inst = cls(host) if _accepts_host(cls) else cls()
            # 构造里没把 host 存下来（旧写法的无参构造、或忘了 super().__init__）
            # 也补上：self.log / self.path 这些助手全靠它。
            inst.host = host
            # 清单与类上都有 id 时以清单为准（清单才是加载器认的那个）
            inst.id = info.id
            # 装饰器登记的条目 / 订阅在这一步落地（构造之后、界面构建之前）
            from ..BMLCore import registrar
            registrar.apply(inst)
    except (Exception, SystemExit):
        # SystemExit 也要接住：插件在构造里 sys.exit() 时 except Exception
        # 抓不到它，会一路穿到宿主那个「启动失败」弹窗 —— 而这里的规矩是
        # 一个插件坏掉不许拖垮别的（更不能拖垮启动）。
        # KeyboardInterrupt 故意不接：那是用户在按 Ctrl+C，得让它出去。
        info.error = _fmt_exc(limit=6)
        sys.modules.pop(mod_name, None)
        _drop_plugin_modules(info)       # 连它的子模块一起，别留半份代码在 sys.modules 里
        _drop_plugin_paths(info)
        _abort_session(info, token)
        # on_ready 的回调不在注册表里，abort 滚不到（否则重载成功时会把
        # 上一次那个已经回滚掉的旧实例一起叫起来）
        from ..BMLCore import registrar as _reg
        _reg.discard(info.id)
        _cleanup_failed(info, inst, widgets_before)
        return info
    except BaseException:
        # 上面不接的那些（比如 Ctrl+C）：会话必须关掉，否则下一个插件会注册进
        # 一个没人提交的陈旧暂存区
        _abort_session(info, token)
        raise
    else:
        # 跑完了：暂存区并进正表。插件登记到这一刻才对别人可见 ——
        # 也就是说别的插件不可能看到它「一半」的样子。
        #
        # 这一步原来裸写在 else 分支里，而 else 的异常两个 except 都盖不到：
        # commit 中途炸掉（有个点没声明上之类）就带着半截登记穿出 load_all、
        # 直达宿主启动弹窗，而且会话还开着 —— 之后谁都开不了新会话，只能重启。
        # 现在失败一律当成「这个插件没加载起来」处理。
        try:
            registry.commit(token)
        except BaseException as e:
            info.error = f"登记并进正表失败：{type(e).__name__}: {e}"
            _abort_session(info, token, why="commit 失败")
            sys.modules.pop(mod_name, None)
            _drop_plugin_modules(info)
            _drop_plugin_paths(info)
            from ..BMLCore import registrar as _reg
            _reg.discard(info.id)
            _cleanup_failed(info, inst, widgets_before)
            if isinstance(e, (KeyboardInterrupt,)):
                raise
            return info

    # 跑成功了也把「它造了哪些控件」记下来：卸载时已经没法回溯了
    owned = _widgets_since(widgets_before)
    if owned:
        _OWNED_WIDGETS[info.id] = owned
    info.instance = inst
    return info


def _qapp():
    """当前 QApplication；没有 Qt 上下文（纯逻辑测试）时返回 None。"""
    try:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()
    except Exception:
        return None


def _widget_snapshot():
    """当前所有控件的快照。没有 QApplication 时返回 None（那就没什么可管）。"""
    app = _qapp()
    if app is None:
        return None
    try:
        return set(app.allWidgets())
    except Exception:
        return None


def _widgets_since(before):
    """这次加载期间新冒出来的控件。

    加载期间是单线程主线程，除了插件自己没别人在建控件 —— 所以新出现的
    就是它造的。这条判据是「删了不会误伤」的依据。
    """
    if before is None:
        return []
    app = _qapp()
    if app is None:
        return []
    try:
        return [w for w in app.allWidgets() if w not in before]
    except Exception:
        return []


def _destroy_widgets(widgets):
    """删掉一批控件，返回删了几个。

    先 setParent(None) 把它从布局里摘出来再 deleteLater() —— 直接 deleteLater
    也行，但先摘出来能让「正在显示的页」立刻从三栏容器里消失，不留中间态。
    已经没了（C++ 那边被上层顺手删了）就跳过。
    """
    n = 0
    for w in list(widgets or ()):
        try:
            w.setParent(None)
            w.deleteLater()
            n += 1
        except RuntimeError:
            pass                        # 包装对象还在、C++ 对象已经没了
        except Exception:
            pass
    return n


# 加载成功后，这个插件「造出来的控件」记在这儿（卸载时按 id 取出来删）
_OWNED_WIDGETS = {}


def _cleanup_failed(info, inst=None, widgets_before=None):
    """插件没跑完时的收尾，按「先摘登记、再跑析构、最后删控件」来。

    注册表那部分已经由会话回滚了（abort），这里管会话管不到的：
      * 事件 —— 它不在注册表里，没法回滚，按命名空间摘一遍；
      * on_close —— 卸载是插件自己写的（它才知道自己起了什么线程、开了什么文件），
        构造可能只做了一半，所以尽力跑一次、抛什么都吞掉；
      * 控件 —— 最后把它这次造出来的控件全删掉。放在 on_close **之后**，
        因为卸载里可能还要摸自己的控件，先删了它就得撞悬空对象。
    """
    from .events import events

    try:
        _drop_plugin_events(info)
    except Exception:
        events.logger.error(f"回滚插件事件失败：{info.id}\n{_fmt_exc(limit=4)}",
                            name="Plugin")
    if inst is not None:
        try:
            inst.on_close()
        except (Exception, SystemExit):
            events.logger.warning(f"回滚时 on_close 抛异常（已忽略）：{info.id}",
                                  name="Plugin")
    _OWNED_WIDGETS.pop(info.id, None)
    n = _destroy_widgets(_widgets_since(widgets_before))
    if n:
        events.logger.info(f"回滚插件控件：{info.id} 删掉 {n} 个（加载失败时它已经建出来的）",
                           name="Plugin")
    _notify_changed()


def _notify_changed():
    """插件集合变了：让宿主把它盖过的东西收回来（语言包 / 样式 / 托盘项）。

    宿主没 bind、或没注册这个名字时静默跳过 —— emit 对未注册的名字本来就静默，
    加载器不额外假设宿主长什么样。

    一批加载（_batch_begin/_batch_end 之间）里只记账不发：一批中间可能失败、
    回滚好几回，每回都让宿主把语言表重读一遍、样式表重建一遍纯属白干；
    收口在 load_all 末尾那一次。

    版本号只在「已加载集合真的变了」时 +1：Langer 拿它判断「插件语言包这份输入
    变没变」—— 语言没变、插件集合也没变，就不该把同一份表再读一遍、再广播一遍。
    一个插件都没装的启动因此只读一次语言（以前会白读第二次）。
    """
    global _LANGS_REV, _LAST_NOTIFIED_IDS
    ids = tuple(i.id for i in _STATE["loaded"])
    if ids != _LAST_NOTIFIED_IDS:
        _LANGS_REV += 1
        _LAST_NOTIFIED_IDS = ids
    if _BATCH:
        return
    try:
        from .events import events
        events.emit("plugins_changed")
    except Exception:
        pass


def _expose_api():
    """把 BMLCore 与插件包根挂成顶层名字。

    BMLCore 本体住在 src/BMLCore/ 下（会随 exe 一起编译），而插件是 exe 外
    的独立 .py —— 它的 sys.path 里没有 src/，`from BMLCore import ...` 会直接
    找不到。这里显式暴露一个顶层名字：插件只认这一个入口，正是我们想要的。

    `bmlplugin` 是插件自己的包根（`bmlplugin.<id>` 就是某个插件，见 load_one）：
    空壳一个，只提供 __path__，子模块由标准导入机制从插件目录里找。

    （两个名字都不在闸门的禁止名单里 —— 闸门只拦 src.* 和 main。）
    """
    if PACKAGE_ROOT not in sys.modules:
        root = types.ModuleType(PACKAGE_ROOT)
        root.__doc__ = "插件包根：bmlplugin.<插件id> 就是那个插件"
        root.__path__ = []          # 空路径：自己不带子包，子模块都在各插件目录里
        sys.modules[PACKAGE_ROOT] = root
    if "BMLCore" in sys.modules:
        return sys.modules["BMLCore"]
    from .. import BMLCore
    sys.modules["BMLCore"] = BMLCore
    return BMLCore


def disabled_ids():
    """被标注停用的插件 id（上次加载失败的）。

    存在 settings["disabledPlugins"] 里 —— 它得活过一次启动，
    否则「标注禁用」就没意义：下次照样一头撞上去。
    """
    try:
        from .events import events
        settings = events.settings
    except Exception:
        return []
    ids = settings.get(DISABLED_KEY) if settings is not None else None
    if not isinstance(ids, list):
        return []
    # 逐项收成字符串：settings.json 是被手改过的重灾区，列表里塞了 dict / list
    # 时 set(...) 会抛 TypeError，而这条路径在 load_all 里没人接 —— 表现成启动失败。
    out = []
    for x in ids:
        if isinstance(x, str) and x.strip() and x not in out:
            out.append(x)
    return out


def _write_disabled(ids):
    """写停用名单并**立刻**落盘。

    这里原先 `except Exception: return` 静默吞掉了失败 —— 结果是一个 ImportError
    让「标注了禁用」根本没写进文件，下次启动照样一头撞上去，而且一点动静都没有。
    现在：拿不到宿主（测试环境）就安静返回；写不进设置/落不了盘都要吭声。
    """
    from .events import events

    try:
        settings = events.settings
    except Exception:
        return False                    # 没 bind 宿主：没什么可写的
    try:
        settings[DISABLED_KEY] = list(ids)
    except Exception:
        events.logger.error("写停用名单失败：\n" + _fmt_exc(limit=4),
                            name="Plugin")
        return False
    try:
        events.saveSettings()           # 别等退出：下次启动要靠它
    except Exception as e:
        events.logger.warning(f"停用名单没能立刻落盘（退出时还会整体存一次）：{e}",
                              name="Plugin")
    return True


def enable(pid):
    """把某个插件从停用名单里去掉（用户说「我修好了」）。返回是否真的去掉了。"""
    ids = disabled_ids()
    if pid not in ids:
        return False
    ids.remove(pid)
    _write_disabled(ids)
    _notify_changed()
    return True


def disable(pid, why=""):
    """把某个插件标进停用名单并存盘，返回是否新标上。"""
    ids = disabled_ids()
    if pid in ids:
        return False
    ids.append(pid)
    _write_disabled(ids)
    return True


def state():
    """三张表的快照（副本）—— 排查「谁还在加载中 / 谁没轮到」时用。"""
    return {k: list(v) for k, v in _STATE.items()}


def _loading_ids():
    """加载中那条链的 id（有序）。成环时从重复出现的那个截到末尾就是环本身。"""
    return [i.id for i in _STATE["loading"]]


def load_all(base=None, *, retry_disabled=False):
    """发现并加载全部插件（含依赖），返回清单列表（含失败项）。

    必须是「逐个隔离」：一个插件坏掉只写进它自己的 error，
    绝不向外抛 —— 宿主启动流程整个包在一个大 try 里，抛出去就是启动失败弹窗。
    日志格式见模块说明（[id]开始加载 / 加载完成 / 加载失败:\n<traceback>）。

    上次加载失败被标注停用的（settings["disabledPlugins"]）默认**跳过** ——
    不跳过的话每次启动都要重演一遍同样的失败与回滚。用户改好了想重试就传
    retry_disabled=True（宿主的重载动作会这么调），那时名单先清掉。
    """
    from .events import events

    _batch_begin()
    try:
        # 先把自己上一轮加载的卸掉 —— load_all 于是可以反复调（「重载插件」就是
        # 这么用的）。不卸的话第二次会撞「已存在条目」，而且三张表会和正表对不上。
        for old in list(_STATE["loaded"]):
            unload(old)

        _expose_api()
        infos = discover(base)
        by_id = {i.id: i for i in infos}
        if retry_disabled:
            # 用户说「我修好了」：先把名单清掉再试；再失败会重新标上
            _write_disabled([])
            off = set()
        else:
            off = set(disabled_ids())

        # 未加载表：全部已发现的；加载中/已加载清空重来
        _STATE["pending"] = list(infos)
        _STATE["loading"] = []
        _STATE["loaded"] = []

        for info in list(_STATE["pending"]):
            if info.id in off:
                info.disabled = True
                info.reported = True    # 别走到「开始加载」，它这轮就没被加载
                _drop_pending(info)
                events.logger.info(f"[{info.id}]已停用，跳过（上次加载失败已标注；"
                                   f"修好后用 enable() 或把手动触发一次重载）",
                                   name="Plugin")
                continue
            _load_tree(info, by_id)
    finally:
        _batch_end()

    # 加载完也通知一声：谁按注册表建界面（页面 / 托盘 / 样式 / 语言）都得在
    # **集合稳定之后**收口一次。只在卸载/失败时发是不够的 —— 重载这条路最后
    # 一次重建会落在卸载阶段（那时注册表是空的），插件的托盘项就这么没了。
    _notify_changed()
    _run_ready()
    return infos


def _run_ready():
    """所有插件都加载完：跑各自的 on_ready（一个炸了不牵连别的）。

    接的是 `(Exception, SystemExit)`，与 load_one / unload 对齐：插件在
    on_ready（起线程、读文件的地方）里 `sys.exit()` 时，SystemExit 不是
    Exception 的子类，漏接就一路穿到宿主启动流程 —— 而那里的兜底只认
    Exception，表现成「启动器不出声地退了」。一个插件的坏习惯不该有这个权力。
    KeyboardInterrupt 照旧让它出去（那是用户在按 Ctrl+C）。
    """
    from ..BMLCore import registrar
    for info in list(_STATE["loaded"]):
        for cb in registrar.ready(info.id):
            try:
                cb()
            except (Exception, SystemExit):
                from .events import events
                events.logger.error(f"[{info.id}]on_ready 抛异常：{_fmt_exc(limit=4)}",
                                    name="Plugin")


def _load_tree(info, by_id):
    """加载 info —— 先把它的依赖拉起来，再加载自己。

    状态全在三张表里：
      * 要动一个插件，先把它从**未加载**移到**加载中**（移出去就不可能再被
        当作「还没轮到」重来一遍，也就没有重试环）；
      * 依赖若已经在**加载中**表里，那就是图里的一条回边 = 成环；
      * 成功了才进**已加载**表，失败只把原因留在 info.error 上。

    这条链同时就是日志的顺序：依赖递归进来说，读日志的人看到的就是「谁在等谁」。
    """
    from .events import events

    if info.ok or info.reported or info in _STATE["loaded"]:
        return                      # 已经起来了，或失败原因已经报过一遍
    if info.error:
        # 发现期就坏掉的（清单不合法 / zip 解不开）：没有依赖可谈，直接报
        _drop_pending(info)
        _report_fail(info)
        return

    _drop_pending(info)
    _STATE["loading"].append(info)
    try:
        events.logger.info(f"[{info.id}]开始加载", name="Plugin")

        for dep_id in info.dependencies:
            dep = by_id.get(dep_id)
            if dep is None:
                _fail(info, f"缺少依赖：{dep_id}（没有这个插件，或者它的清单没读出来）")
                return
            if dep_id in _loading_ids():
                # 回边：环就是加载中表里从 dep_id 那一段，末尾补回它自己。
                # 这样报出来的是**环本身**，不带「从入口怎么走到这儿」那一段。
                ids = _loading_ids()
                _fail(info, "依赖成环：" + " -> ".join(ids[ids.index(dep_id):] + [dep_id]))
                return
            if dep.disabled:
                # 依赖被停用了：依赖者这轮也起不来。**不**把它也标进停用名单 ——
                # 用户把依赖放行之后，它就该跟着起来。
                _fail(info, f"依赖已被停用：{dep_id}")
                return
            if not dep.ok:
                _load_tree(dep, by_id)
            if not dep.ok:
                _fail(info, f"依赖加载失败：{dep_id}")
                return

        load_one(info)
        if info.ok:
            _STATE["loaded"].append(info)
            events.logger.info(f"[{info.id}]加载完成", name="Plugin")
        else:
            _report_fail(info)
    finally:
        _STATE["loading"].remove(info)


def _drop_pending(info):
    """把它从「未加载」里移出去 —— 已经决定要处理它了。"""
    if info in _STATE["pending"]:
        _STATE["pending"].remove(info)


def _fail(info, why):
    """给「不是异常」的失败定原因（缺依赖 / 成环）并报出去。

    这类失败**不进停用名单**：它们是图上的问题，不是插件自己的毛病 ——
    用户装上缺的那个依赖、或改掉环之后，下次启动就该能起来。写进停用名单
    反而要用户再手动放行一次（而界面里根本没有那个开关）。
    """
    info.error = why
    _report_fail(info, disable_it=False)


def _report_fail(info, disable_it=True):
    """报一次加载失败 —— 同一条只报一次（它可能既是某人的依赖、又轮到它自己）。

    插件自己加载不起来时顺手标进停用名单：下次启动不再重演同样的失败与回滚
    （改好了要重试，走 load_all(retry_disabled=True) 或 enable(id)）。

    两种情况除外：
      * 占位 id（清单都没读出来，id 是 `<目录名>`）—— 写进去就是一条永远清不掉的
        垃圾，用户改好清单后 id 变了，那条再也没人认领；
      * 图上的问题（缺依赖 / 成环，见 _fail）。
    """
    from .events import events

    if info.reported:
        return
    info.reported = True
    events.logger.error(f"[{info.id}]加载失败:\n{info.error}", name="Plugin")
    if not disable_it or not info.id or info.id.startswith("<"):
        return
    # 「已标注停用」单独打一行、排在失败之后 —— 它是**后果**不是原因，
    # 所以不追加进 info.error（那会坑到所有比对错误文本的地方）。
    if disable(info.id, "加载失败"):
        events.logger.info(
            f"[{info.id}]已标注停用，下次启动不再加载它"
            f"（修好后调 pluginLoader.enable(id)，或手动触发一次插件重载）",
            name="Plugin")


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
    if info not in _STATE["loaded"]:
        # 还活着但不在已加载表里：说明是「同一个 id 装了两份」的那种残局，
        # 这里别动它 —— 否则会把活着的那一份的事件/包/控件台账拆掉。
        events.logger.warning(f"[{info.id}]不在已加载表里，跳过卸载（先查重装/重复加载）",
                              name="Plugin")
        return False
    try:
        registry.remove_namespace(info.id)
        _drop_plugin_events(info)
    except Exception:
        events.logger.error(f"插件卸载时摘登记失败：{info.id}\n{_fmt_exc(limit=4)}",
                            name="Plugin")
    try:
        _drop_plugin_paths(info)
        _drop_plugin_modules(info)      # 包名与它的子模块一起从 sys.modules 里摘

        inst = info.instance

        inst.on_close()
    except (Exception, SystemExit):
        # 同 load_one：SystemExit 也得接住，卸载一个插件不该把启动器带走
        events.logger.error(f"插件 teardown 抛异常：{info.id}\n{_fmt_exc(limit=4)}",
                            name="Plugin")
    # 析构跑完再删它加载时造出来的控件（那时没法回溯，所以加载成功时就记下了）。
    # 由扩展点构建出来的那些（页面等）不在这里 —— 那是装配方按注册表建的，
    # 摘条目的时候它们自己会走。
    n = _destroy_widgets(_OWNED_WIDGETS.pop(info.id, ()))
    if n:
        events.logger.info(f"卸载时删掉插件造的控件：{info.id} × {n}", name="Plugin")
    info.instance = None
    info.error = ""
    info.reported = False
    for table in ("pending", "loading", "loaded"):
        _STATE[table] = [i for i in _STATE[table] if i.id != info.id]
    # 摘完登记还得让宿主重算「它盖过的」：语言包、样式片段、托盘菜单项。
    # 这三样都不在注册表里，光摘条目它们不会自己回去。
    _notify_changed()
    return True
