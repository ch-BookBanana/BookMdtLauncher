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
    ├── plugin.json     元信息（id / name / version / api / entry / dependencies）
    ├── main.py         入口，里面得有一个 Plugin 子类
    ├── lang/*.json     可选，自己的语言包
    └── assets/*        可选，自己的图标

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

    [com.example.a]开始加载
    [com.example.b]开始加载      ← 依赖走同一套，递归进来说
    [com.example.b]加载完成
    [com.example.a]加载完成

已经起来的、以及正在这条链上的（成环），都不会再打一遍「开始加载」。
失败打 [id]加载失败:\n<traceback>；缺依赖、依赖成环、清单不合法这类没有
traceback，就写原因 —— 格式一样，排查时不必分两种读法。

插件失败之后
--------------
**登记的是全有或全无**：插件写注册表走一次加载会话（见 registry.begin/commit/abort），
setup 跑到一半抛异常就整块丢掉 —— 不会在正表里留下半截条目（那会让界面冒出点不动
的项，重试还撞「已存在条目」），连它自己 declare 出来的扩展点也一起消失。

会话管不到的另外两样由加载器自己收：
  * 事件订阅 —— 不在注册表里，按命名空间摘一遍；
  * teardown —— setup 可能只做了一半，尽力试一次，抛什么都吞掉。

**插件能盖的三样，卸载/失败后会自己回来**：语言包、样式片段（core.qss）、
托盘菜单项。做法是加载器发一条 plugins_changed，宿主收到后重载语言、重收样式、
重建托盘 —— 这三样都不在注册表里，光摘条目它们不会自己回去。

**有一处回不来：页面（core.pages）**。左栏按钮与三栏控件是启动时建好的，
要让插件页面能热摘得让页容器支持重建，那是另一件事。所以卸掉一个带页面的插件
要重启才干净 —— 这是已知限制，不是忘了做。

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

__all__ = ["PluginInfo", "PluginLoadError", "discover", "load_all", "load_one",
           "unload", "loaded", "state", "ensure_dirs",
           "plugin_langs", "PLUGIN_DIR", "PLUGIN_CACHE", "MANIFEST"]

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
    dependencies: tuple = ()         # 依赖的插件 id（清单里的 dependencies）

    source: str = ""                # 来自目录还是 zip 文件（界面显示/排查用）
    instance: object = None          # 加载成功后的 Plugin 实例
    error: str = ""                  # 非空 = 加载失败（界面据此标红）
    reported: bool = field(default=False, repr=False)   # 失败日志是否已打过


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

    deps = data.get("dependencies") or []
    if isinstance(deps, str):
        deps = [deps]                      # 只依赖一个时写字符串也认
    if not isinstance(deps, list):
        raise PluginLoadError("plugin.json 的 dependencies 必须是数组")
    bad = [d for d in deps if not isinstance(d, str)]
    if bad:
        # 不能 str() 了事：null 会变成 "None"、数字会变成 "123"，
        # 而它们都是「查不到的依赖名」—— 失败会发生在很远的地方
        raise PluginLoadError(f"plugin.json 的 dependencies 里只能是字符串，收到 {bad!r}")
    deps = tuple(dict.fromkeys(d.strip() for d in deps if d.strip()))
    if pid in deps:
        raise PluginLoadError(f"依赖了自己：{pid}")

    entry = (data.get("entry") or "main.py").strip()
    return PluginInfo(
        id=pid, path=folder, entry=entry,
        name=(data.get("name") or pid).strip(),
        version=str(data.get("version") or "0.0.0"),
        api=str(data.get("api") or "1.x"),
        author=(data.get("author") or "").strip(),
        description=(data.get("description") or "").strip(),
        dependencies=deps,
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

# 加载状态机：三张表就是全部状态，别处不再各留一份
#   pending  未加载：已发现、还没轮到（load_all 从它取活，取走就移出）
#   loading  加载中：正在加载的那条链，**有序** —— 报成环时从这儿截
#   loaded   已加载：加载成功的，按加载顺序（plugin_langs 靠它决定谁盖谁的文案）
# 三张表都存 PluginInfo；失败的不进 loaded，失败原因在 info.error 上。
_STATE = {"pending": [], "loading": [], "loaded": []}


def ensure_dirs(base=None):
    """建好插件目录。

    由宿主在启动时调一次，路径只有 PLUGIN_DIR 这一个出处 —— 原先目录名在
    这里、建目录的代码却在 main.py 里又写了一遍字面量，改一处忘一处就是
    「插件全没了却一声不吭」（discover 发现目录不存在只返回空表）。
    """
    os.makedirs(base or getPath(PLUGIN_DIR), exist_ok=True)


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
    """加载单个插件本身（**不解析依赖、不打进度日志**）。

    它是最底层那一步：导入入口、找 Plugin 子类、实例化、setup()。
    任何异常都被吞进 info.error，不往外抛。公开给测试与「手动装一个」用；
    正常启动走 load_all，依赖与日志都在那一层。
    """
    from ..BMLCore import API_VERSION
    from .registry import registry

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
    inst = None
    # 登记走一次**加载会话**：插件写进暂存区，跑完才并进正表。
    # 这样「setup 跑到一半抛异常」不会在正表里留下半截条目（界面会冒出点不动
    # 的项，重试还撞「已存在条目」）—— 而且不必靠事后按命名空间去擦。
    registry.begin()
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
    except (Exception, SystemExit):
        # SystemExit 也要接住：插件在 setup 里 sys.exit() 时 except Exception
        # 抓不到它，会一路穿到宿主那个「启动失败」弹窗 —— 而这里的规矩是
        # 一个插件坏掉不许拖垮别的（更不能拖垮启动）。
        # KeyboardInterrupt 故意不接：那是用户在按 Ctrl+C，得让它出去。
        info.error = traceback.format_exc(limit=6)
        sys.modules.pop(mod_name, None)
        registry.abort()
        _cleanup_failed(info, inst)
        return info
    except BaseException:
        # 上面不接的那些（比如 Ctrl+C）：会话必须关掉，否则下一个插件会注册进
        # 一个没人提交的陈旧暂存区
        registry.abort()
        raise
    else:
        # 跑完了：暂存区并进正表。插件登记到这一刻才对别人可见 ——
        # 也就是说别的插件不可能看到它「一半」的样子。
        registry.commit()

    info.instance = inst
    return info


def _cleanup_failed(info, inst=None):
    """插件没跑完时的收尾。

    注册表那部分已经由会话回滚了（abort），这里管会话管不到的：
      * 事件 —— 它不在注册表里，没法回滚，按命名空间摘一遍；
      * teardown —— setup 可能只做了一半，尽力试一次，抛什么都吞掉。
    """
    from .events import events

    try:
        events.drop_namespace(info.id)
    except Exception:
        events.logger.error(f"回滚插件事件失败：{info.id}\n{traceback.format_exc(limit=4)}",
                            name="Plugin")
    if inst is not None:
        try:
            inst.teardown()
        except (Exception, SystemExit):
            events.logger.warning(f"回滚时 teardown 抛异常（已忽略）：{info.id}",
                                  name="Plugin")
    _notify_changed()


def _notify_changed():
    """插件集合变了：让宿主把它盖过的东西收回来（语言包 / 样式 / 托盘项）。

    宿主没 bind、或没注册这个名字时静默跳过 —— emit 对未注册的名字本来就静默，
    加载器不额外假设宿主长什么样。
    """
    try:
        from .events import events
        events.emit("plugins_changed")
    except Exception:
        pass


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


def state():
    """三张表的快照（副本）—— 排查「谁还在加载中 / 谁没轮到」时用。"""
    return {k: list(v) for k, v in _STATE.items()}


def _loading_ids():
    """加载中那条链的 id（有序）。成环时从重复出现的那个截到末尾就是环本身。"""
    return [i.id for i in _STATE["loading"]]


def load_all(base=None):
    """发现并加载全部插件（含依赖），返回清单列表（含失败项）。

    必须是「逐个隔离」：一个插件坏掉只写进它自己的 error，
    绝不向外抛 —— 宿主启动流程整个包在一个大 try 里，抛出去就是启动失败弹窗。
    日志格式见模块说明（[id]开始加载 / 加载完成 / 加载失败:\n<traceback>）。
    """
    _expose_api()
    infos = discover(base)
    by_id = {i.id: i for i in infos}
    # 未加载表：全部已发现的；加载中/已加载清空重来
    _STATE["pending"] = list(infos)
    _STATE["loading"] = []
    _STATE["loaded"] = []

    for info in list(_STATE["pending"]):
        _load_tree(info, by_id)
    return infos


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
    """给「不是异常」的失败定原因（缺依赖 / 成环）并报出去。"""
    info.error = why
    _report_fail(info)


def _report_fail(info):
    """报一次加载失败 —— 同一条只报一次（它可能既是某人的依赖、又轮到它自己）。"""
    from .events import events

    if info.reported:
        return
    info.reported = True
    events.logger.error(f"[{info.id}]加载失败:\n{info.error}", name="Plugin")


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
    except (Exception, SystemExit):
        # 同 load_one：SystemExit 也得接住，卸载一个插件不该把启动器带走
        events.logger.error(f"插件 teardown 抛异常：{info.id}\n{traceback.format_exc(limit=4)}",
                            name="Plugin")
    info.instance = None
    info.error = ""
    info.reported = False
    for table in ("pending", "loading", "loaded"):
        _STATE[table] = [i for i in _STATE[table] if i.id != info.id]
    # 摘完登记还得让宿主重算「它盖过的」：语言包、样式片段、托盘菜单项。
    # 这三样都不在注册表里，光摘条目它们不会自己回去。
    _notify_changed()
    return True
