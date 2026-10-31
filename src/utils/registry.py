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

扩展点注册中心（v2）：**按 owner 归档**，接口与内容分区。

数据长这样
----------
    data[owner] = {
        "meta":      {名字 / 版本 / api / 来源 / 权限},        # 谁
        "declares":  {<接口名>: <契约>},                       # 它声明的接口
        "registers": {<父 owner>: {<接口名>: {<条目 key>: [层…]}}},   # 它往谁的接口里放了什么
    }

三条规矩（v2 的核心）

1. **归属即桶**。条目长在谁的 `registers` 下就是谁登记的 —— 不需要从 key 前缀去猜，
   卸载就是删一棵子树。往 `core` 的接口登记，也照样落在**你自己**的桶里，
   所以「插件声明 core/ 前缀的接口」在结构上不可能发生。
2. **接口与内容分区**。`declares` 只有契约（字段、callingMode、覆盖许可、产物槽位），
   `registers` 只有内容。今天那种「同一个 dict 里混着 __fields__ 和条目、
   靠三套保留键区分」的写法没有了。
3. **覆盖是一条栈**。同一条目被别人顶掉时，被顶掉的那份留在下面，栈顶生效；
   顶的人走了（卸载）就弹栈，回到上一个提供者 —— 界面按注册表重建即可。

引用形态
--------
    接口：  core/pages            （owner/接口名）
    条目：  core/pages#core/start  （接口路径#条目 key）
            owner 段可以省略，省略时取「当前发起方」（登记时=登记方，取用时=调用方）

会话
----
`begin(owner)` 开一次加载会话：之后的写都进暂存区（按 owner 分桶），
`commit(token)` 一次并进正表（**先全校验再落盘**，不可半途而废），
`abort(token)` 整块丢掉。有主人的会话只有拿着凭据的一方关得掉，
插件在构造里动 `abort()/commit()` 是关不掉的 —— 那是「失败整块舍弃」的前提。

边界
----
本模块只做「登记 / 校验 / 查询」，**不含任何 Qt 代码、不负责构造控件**。
"""

import copy
import re

__all__ = ["RegistryError", "Entry", "Box", "Registry", "registry", "page",
           "simple", "normalize"]

# 每一段（owner / 接口名的段）的字符规约：与插件 id 同一套
_SEG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# 宿主命名空间：remove_namespace 不许碰它们
HOST_NAMESPACES = ("core", "src", "main", "bmlcore", "bmlplugin", "bml_plugin")

# 条目里的内部键：不算登记字段（归属 / 产物 / 层序）
_INTERNAL = ("by", "built", "seq")

# 会话凭据的默认值：有主人的会话必须带对凭据，没主人的照旧裸调
_ANY_TOKEN = object()


class RegistryError(Exception):
    """注册表用法错误：接口未声明、字段越界、key 冲突或格式不对。"""


# ─────────────────────────── 路径与 key ───────────────────────────

def normalize(path):
    """把旧写法统一成 v2 的路径写法：`core.pages` → `core/pages`。

    迁移期两套写法都要认（宿主里还有大量 `core.setting.items` 这种点号写法），
    但存下来的永远是斜杠形态 —— 这样 v2 只有一套路径语义。
    """
    return str(path).replace(".", "/")


def _split_point(point):
    """接口路径 → (owner, 接口名)。`core/pages` → ("core", "pages")。"""
    path = normalize(point)
    owner, _, name = path.partition("/")
    if not owner or not name:
        raise RegistryError(
            f"接口 {point!r} 不合法：要写成 <owner>/<接口名>（如 core/pages）")
    for seg in path.split("/"):
        if not _SEG_RE.match(seg):
            raise RegistryError(
                f"接口 {point!r} 的段 {seg!r} 不合法：只能用字母、数字、下划线，"
                f"且首字符是字母")
    return owner, name


def _split_key(key):
    """条目 key → (owner, 名字)。`core/start` → ("core", "start")。

    没写 owner（`#settings` 这种）时返回 ("", 名字)，由调用方按当前发起方补齐。
    """
    path = normalize(key)
    if "/" not in path:
        if not path:
            raise RegistryError("条目 key 不能为空")
        return "", path
    owner, _, name = path.partition("/")
    if not owner or not name:
        raise RegistryError(
            f"条目 key {key!r} 不合法：要写成 <owner>/<名字>（如 core/start）")
    return owner, name


def _same(a, b):
    """宽松相等：两个字符串都规范化再比 —— 迁移期点号与斜杠两种写法算同一个。"""
    if isinstance(a, str) and isinstance(b, str):
        return normalize(a) == normalize(b)
    return a == b


# ─────────────────────────── 条目视图 ───────────────────────────

class Entry:
    """一个登记项：身份 + 登记字段 + 构建产物（只读视图）。

    字段既可以用 `e.title` 直读，也可以用 `e.get("title", 默认值)`；
    查找顺序是「登记字段 → 构建产物」，所以页面装配好之后 `e.main / e.btn`
    也能直接读（那两个是 bind() 的产物，不是登记字段）。
    """

    __slots__ = ("key", "namespace", "name", "fields", "built", "built_fields",
                 "_point", "_registrant", "_by")

    def __init__(self, point, key, registrant, raw_fields, built_fields=()):
        self._point = point
        self._registrant = registrant
        self.key = key
        self.fields = {k: v for k, v in raw_fields.items()
                       if k not in _INTERNAL}
        self.built = dict(raw_fields.get("built") or {})
        self.built_fields = tuple(built_fields)
        owner, name = _split_key(key)
        self.namespace = owner
        self.name = name
        self._by = raw_fields.get("by") or registrant

    def __getattr__(self, item):
        try:
            fields = object.__getattribute__(self, "fields")
        except AttributeError:
            raise AttributeError(item) from None
        if item in fields:
            return fields[item]
        built = object.__getattribute__(self, "built")
        if item in built:
            return built[item]
        slots = object.__getattribute__(self, "built_fields")
        if item in slots:
            raise AttributeError(
                f"{self._point} 的条目 {self.key!r} 声明了产物槽位 {item!r}，"
                f"但还没有 bind() 回填")
        avail = (sorted(fields)
                 + [f"{k}(产物)" for k in sorted(built)]
                 + [f"{k}(槽位)" for k in sorted(slots) if k not in built])
        raise AttributeError(
            f"{self._point} 的条目 {self.key!r} 没有字段 {item!r}"
            f"（可用：{', '.join(avail) or '无'}）")

    def get(self, item, default=None):
        """先查登记字段，再查构建产物。"""
        if item in self.fields:
            return self.fields[item]
        return self.built.get(item, default)

    def is_built(self):
        """构建产物是否已回填（页面装配完成、main/btn 就位）。"""
        return bool(self.built)

    def __repr__(self):
        mark = f" +built{sorted(self.built)}" if self.built else ""
        return f"<Entry {self.key} fields={sorted(self.fields)}{mark}>"


class Box:
    """构建一个条目时交给 init 的「匣子」。

    box.parent  该条目该挂到哪个容器
    box.entry   条目自身，可读 title / icon / order / name / key 等
    box.btn     配套按钮（接口声明了 btn 产物槽位时才有，否则为 None）

    关键词参数就是**本次上下文**：`Box(parent=…, entry=…, game="<:|default|:>")`，
    init 里 `b.game` 就取得到。静态元信息该写在条目字段里，上下文只放一次性的；
    两者重名时以本次上下文为准。没给又去读，会当场抛 AttributeError 并列出可用项。
    """

    __slots__ = ("parent", "entry", "btn", "_ctx")

    def __init__(self, parent=None, entry=None, btn=None, **ctx):
        self.parent = parent
        self.entry = entry
        self.btn = btn
        self._ctx = ctx

    def __getattr__(self, item):
        try:
            ctx = object.__getattribute__(self, "_ctx")
        except AttributeError:
            ctx = {}
        if item in ctx:
            return ctx[item]
        try:
            entry = object.__getattribute__(self, "entry")
        except AttributeError:
            entry = None
        if entry is not None:
            return getattr(entry, item)
        raise AttributeError(item)


def simple(cls, **extra):
    """便捷 init：控件构造签名正好是 (parent, title, **extra) 时用它。"""
    return lambda b: cls(b.parent, b.title, **extra)


# ─────────────────────────── 注册中心 ───────────────────────────

class Registry:
    """扩展点登记中心。实例只有一个（模块底部 registry），但类可单独实例化便于测试。"""

    RESERVED = ()

    def __init__(self):
        # owner → {"meta": {}, "declares": {}, "registers": {}}
        self.data = {}
        self._stage = None          # 会话期间的同形暂存区（按 owner 分桶）
        self._session_owner = None  # 会话主人（插件 id）
        self._session_token = None  # 有主人的会话的凭据
        self._watchers = []         # [(接口路径, 回调)]
        self._seq = 0               # 层序号：决定覆盖栈里的先后

    # ── 内部：桶 ──

    def _bucket(self, owner, create=False, table=None):
        table = self.data if table is None else table
        b = table.get(owner)
        if b is None:
            if not create:
                return None
            b = table[owner] = {"meta": {}, "declares": {}, "registers": {}}
            b["meta"]["id"] = owner
        return b

    def _write_bucket(self, owner):
        """写落到哪个表：会话里落暂存区，否则落正表。"""
        if self._stage is None:
            return self._bucket(owner, create=True)
        return self._bucket(owner, create=True, table=self._stage)

    def _tables(self):
        """[正表, 暂存区(可能有)]"""
        out = [self.data]
        if self._stage is not None:
            out.append(self._stage)
        return out

    def _interface(self, point):
        """找接口契约（暂存区优先）。找不到就报错并列出已有的。"""
        owner, name = _split_point(point)
        for table in reversed(self._tables()):
            b = table.get(owner)
            if b and name in b["declares"]:
                return owner, name, b["declares"][name]
        known = ", ".join(sorted(self.points())) or "（尚未声明任何接口）"
        raise RegistryError(
            f"接口 {point!r} 尚未声明，请先 registry.declare(...)；已声明：{known}")

    def _layers(self, iface_owner, iface_name, key):
        """某条目在合并视图里的层栈（按登记先后排序），没有就是 []。"""
        return self._all_entries(iface_owner, iface_name).get(key, [])

    def _all_entries(self, iface_owner, iface_name):
        """合并所有 owner 在这个接口下的条目：key → 层栈（按 seq 排序，栈顶生效）。

        层可以躺在不同 owner 的桶里（谁 set 的就在谁那儿），所以合并时按
        seq 排 —— 卸载某个 owner 时只掉它那几层，其余层顺序不变。
        """
        stacks = {}
        for table in self._tables():
            for b in table.values():
                regs = b["registers"].get(iface_owner)
                if not regs:
                    continue
                for key, stack in regs.get(iface_name, {}).items():
                    stacks.setdefault(key, []).extend(stack)
        for stack in stacks.values():
            stack.sort(key=lambda layer: layer.get("seq", 0))
        return stacks

    # ── 声明接口 ──

    def declare(self, point, *, registrant=None, fields=(), required=(),
                built=(), kind="class", doc="", callingMode=None, override=True):
        """声明一个接口。字段表钉死它能接受哪些字段。

        callingMode  : ["modifier"] 只允许加载期声明；["modifier","function"] 也允许运行期增删
        override     : 该接口下的条目默认允不允许被别人顶掉（默认允许；个别条目在条目上单独关）
        """
        owner, name = _split_point(point)
        decl_label = registrant or owner
        if decl_label != owner:
            np_, nl = normalize(point), normalize(decl_label)
            if not (np_ == nl or np_.startswith(nl + "/")):
                raise RegistryError(
                    f"接口 {point!r} 的 owner 是 {owner!r}，"
                    f"registrant {decl_label!r} 既不是它、也不是它的前缀")
        for arg_name, value in (("fields", fields), ("required", required),
                                ("built", built)):
            if isinstance(value, str):
                raise RegistryError(
                    f"{point}: declare 的 {arg_name} 要的是序列（元组/列表），"
                    f"不是字符串 —— 传字符串会被逐字符拆开。收到 {value!r}")
        fields = tuple(fields)
        required = tuple(required)
        built = tuple(built)
        clash = sorted((set(fields) | set(required) | set(built)) & {"built", "by"})
        if clash:
            raise RegistryError(f"{point}: {clash} 是注册表保留字段名，不能当字段")
        stray = [f for f in required if f not in fields]
        if stray:
            raise RegistryError(f"{point}: required 里的 {stray} 不在 fields 中")
        overlap = [f for f in built if f in fields]
        if overlap:
            raise RegistryError(
                f"{point}: {overlap} 同时出现在 fields 和产物槽位里；两者必须分开")
        modes = tuple(callingMode or ("modifier", "function"))
        for m in modes:
            if m not in ("modifier", "function"):
                raise RegistryError(
                    f"{point}: callingMode 只能是 modifier / function，收到 {m!r}")

        block = {
            "fields": fields,
            "required": required,
            "built": built,
            "kind": kind,
            "doc": doc,
            "callingMode": modes,
            "override": bool(override),
            "label": decl_label,
        }
        target = self._write_bucket(owner)
        cur = target["declares"].get(name)
        if cur is not None:
            if cur != block:
                diff = [k for k in block if cur.get(k) != block[k]]
                raise RegistryError(
                    f"接口 {point!r} 已声明且契约不同（{', '.join(diff)}）")
            return point
        target["declares"][name] = block
        self._notify(_path(owner, name))
        return point

    # ── 写条目 ──

    def add(self, point, key, **fields):
        """新建一条（`new`）：撞名报错。返回 Entry。"""
        return self._write(point, key, "new", **fields)

    def new(self, point, key, **fields):
        return self.add(point, key, **fields)

    def set(self, point, key, *, by=None, **fields):
        """顶掉已有条目：被顶掉的那份压进栈里，栈顶生效。返回 Entry。"""
        return self._write(point, key, "set", override_by=by, **fields)

    def update(self, point, key, **fields):
        """改**自己那条**的字段（不产生新层）。"""
        return self._write(point, key, "update", **fields)

    def _write(self, point, key, mode, override_by=None, **fields):
        iface_owner, iface_name, contract = self._interface(point)
        owner, name = _split_key(key)
        # 省略 owner（`#settings`）时按当前发起方算：新建时是会话主人，否则看 key
        if not owner:
            owner = self._current_owner()
        full_key = f"{owner}/{name}"
        actor = self._session_owner or owner
        block = self._write_bucket(actor)
        path = _path(iface_owner, iface_name)
        regs = block["registers"].setdefault(iface_owner, {})
        # 每个 owner 只写自己那份；别人的层靠合并视图读到
        table = regs.setdefault(iface_name, {})
        mine = table.setdefault(full_key, [])
        stack = self._layers(iface_owner, iface_name, full_key)
        self._check_write(contract, point, full_key, fields, mode, stack, actor)

        if mode == "new":
            if stack:
                raise RegistryError(
                    f"{path} 里已存在条目 {full_key!r}（要顶掉它用 set）")
            mine.append(self._layer(actor, fields))
        elif mode == "set":
            mine.append(self._layer(actor, fields))
        else:                                        # update
            if not stack:
                raise RegistryError(f"{path} 里没有条目 {full_key!r}，无法 update")
            idx = next((i for i in range(len(mine) - 1, -1, -1)
                        if mine[i].get("by") == actor), None)
            if idx is None:
                raise RegistryError(
                    f"{path}#{full_key} 不是你登记的（是 {stack[-1].get('by')!r}），"
                    f"不能 update")
            merged = dict(mine[idx])
            merged.update(fields)
            mine[idx] = merged
        if not mine:
            table.pop(full_key, None)
        self._notify(path)
        return self.get(point, full_key)

    def _layer(self, owner, fields):
        self._seq += 1
        return dict(fields, by=owner, seq=self._seq)

    def _layers_existing(self, iface_owner, iface_name):
        """把别的 owner 已登记的条目收进当前写桶（同一 key 只出现一次）。"""
        out = {}
        for table in self._tables():
            for b in table.values():
                regs = b["registers"].get(iface_owner)
                if not regs:
                    continue
                for key, stack in regs.get(iface_name, {}).items():
                    out.setdefault(key, stack)
        return out

    def _check_write(self, contract, point, key, fields, mode, stack, owner):
        allowed = set(contract["fields"])
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise RegistryError(
                f"{point}#{key}: 未知字段 {unknown}；该接口只接受 {sorted(allowed)}")
        merged = dict(stack[-1]) if stack else {}
        merged.update(fields)
        missing = sorted(set(contract["required"]) - set(merged))
        if missing:
            raise RegistryError(f"{point}#{key}: 缺必填字段 {missing}")
        if stack and stack[-1].get("by") != owner:
            if not contract.get("override", True):
                raise RegistryError(
                    f"{point}#{key}: 这条不开放覆盖（接口声明 override=false），"
                    f"不能顶掉 {stack[-1].get('by')!r} 的那一份")
        if self._session_owner is None and "function" not in contract.get("callingMode", ()):
            raise RegistryError(
                f"{point}: 这个接口只接受加载期声明（callingMode 不含 function），"
                f"不能在运行期增删")

    def remove(self, point, key):
        """摘掉自己的条目（运行期增删要接口 callingMode 含 function）。"""
        iface_owner, iface_name, contract = self._interface(point)
        owner, name = _split_key(key)
        full_key = f"{owner}/{name}"
        if self._session_owner is None and "function" not in contract.get("callingMode", ()):
            raise RegistryError(f"{point}: 这个接口只接受加载期声明，不能运行期 remove")
        for table in self._tables():
            b = table.get(owner)
            if not b:
                continue
            regs = b["registers"].get(iface_owner)
            if not regs:
                continue
            sec = regs.get(iface_name, {})
            stack = sec.get(full_key)
            if not stack:
                continue
            stack = [x for x in stack if x.get("by") != owner]
            if stack:
                sec[full_key] = stack
            else:
                sec.pop(full_key, None)
            self._notify(_path(iface_owner, iface_name))
            return True
        raise RegistryError(f"{_path(iface_owner, iface_name)} 里没有条目 {full_key!r}")

    # ── 取 ──

    def get(self, point, key):
        """取条目（合并视图）。"""
        iface_owner, iface_name, contract = self._interface(point)
        full_key = self._normalize_key(key)
        stack = self._all_entries(iface_owner, iface_name).get(full_key)
        if not stack:
            have = sorted(self._all_entries(iface_owner, iface_name))
            raise RegistryError(
                f"{_path(iface_owner, iface_name)} 里没有条目 {full_key!r}；现有：{have or '（空）'}")
        return self._entry(point, full_key, stack, contract)

    def entry(self, point, key):
        return self.get(point, key)

    def list(self, point, *, where=None):
        return self.entries(point, where=where)

    def entries(self, point, *, where=None):
        """按登记顺序取条目；where 做等值筛选，未知字段当场报错。

        顺序 = 谁先登记谁在前（清单里的插入顺序），没有 order 这种数字权重 ——
        和 Qt 摆控件一样：先 addWidget 的先出现。
        """
        iface_owner, iface_name, contract = self._interface(point)
        allowed = set(contract["fields"])
        unknown = sorted(k for k in (where or {}) if k not in allowed)
        if unknown:
            raise RegistryError(
                f"{_path(iface_owner, iface_name)}: where 里的 {unknown} "
                f"不是这个接口的字段；可用：{sorted(allowed)}")
        out = []
        for key, stack in self._all_entries(iface_owner, iface_name).items():
            e = self._entry(point, key, stack, contract)
            if where and any(not _same(e.fields.get(k), v) for k, v in where.items()):
                continue
            out.append(e)
        return out

    def owned(self, point, owner=None):
        """只看某个 owner 登记的条目。"""
        owner = owner or self._current_owner()
        iface_owner, iface_name, contract = self._interface(point)
        out = []
        for key, stack in self._all_entries(iface_owner, iface_name).items():
            if stack[-1].get("by") == owner:
                out.append(self._entry(point, key, stack, contract))
        return out

    def contract(self, point):
        """接口契约（字段、必填、产物槽位、callingMode、覆盖许可、文档）。"""
        owner, name, contract = self._interface(point)
        return dict(contract)

    def _locate(self, iface_owner, iface_name, full_key):
        """找到真正持有这条目的桶：返回 (该桶的接口条目表, 层栈)。

        产物归「登记它的那个 owner」，不能按 key 前缀去猜 —— 比如宿主构建页面时
        回填 main/btn，条目可能长在插件自己的桶里。
        """
        for table in (self.data, self._stage or {}):
            for b in table.values():
                regs = b["registers"].get(iface_owner)
                if not regs:
                    continue
                sec = regs.get(iface_name, {})
                if full_key in sec:
                    return sec, sec[full_key]
        return {}, []

    def _entry(self, point, key, stack, contract):
        top = stack[-1]
        return Entry(point, key, top.get("by", ""), top, contract.get("built", ()))

    def _normalize_key(self, key):
        owner, name = _split_key(key)
        if not owner:
            owner = self._current_owner()
        return f"{owner}/{name}"

    def _current_owner(self):
        """当前发起方：会话主人优先，否则 core（宿主代码的默认身份）。"""
        return self._session_owner or "core"

    # ── 查询接口 ──

    def points(self):
        out = []
        for table in reversed(self._tables()):
            for owner, b in table.items():
                for name in b["declares"]:
                    p = _path(owner, name)
                    if p not in out:
                        out.append(p)
        return sorted(out)

    def declared(self, point):
        try:
            self._interface(point)
            return True
        except RegistryError:
            return False

    def meta(self, point=None):
        """接口契约；不传则给出全部接口的契约表。"""
        if point is not None:
            return self.contract(point)
        return {p: self.contract(p) for p in self.points()}

    def table(self):
        """可用接口查询表：{接口: {fields, required, built, registrant, doc, callingMode}}。"""
        out = {}
        for p in self.points():
            owner, name, c = self._interface(p)
            out[p] = {
                "fields": list(c["fields"]),
                "required": list(c["required"]),
                "built": list(c["built"]),
                "registrant": owner,
                "doc": c.get("doc") or "",
                "callingMode": list(c.get("callingMode", ())),
                "override": bool(c.get("override", True)),
            }
        return out

    def owners(self):
        return sorted({o for table in self._tables() for o in table})

    def owner_meta(self, owner):
        for table in reversed(self._tables()):
            b = table.get(owner)
            if b is not None:
                return dict(b["meta"])
        return {}

    def set_meta(self, owner, **info):
        """记录某个 owner 的元信息快照（名字/版本/api/来源/权限）。"""
        self._write_bucket(owner)["meta"].update(info)

    # ── 构建产物 ──

    def provide(self, point, key, obj, **meta):
        """登记一个**已经存在**的对象（登记完立刻可查）。"""
        self.add(point, key, **dict(meta, init=lambda b: obj))
        return self.bind(point, key, obj=obj)

    def bind(self, point, key, **built):
        """回填构建产物（页面实例 main、导航按钮 btn…）。"""
        iface_owner, iface_name, contract = self._interface(point)
        full_key = self._normalize_key(key)
        slots = contract["built"]
        unknown = sorted(set(built) - set(slots))
        if unknown:
            raise RegistryError(
                f"{_path(iface_owner, iface_name)}#{full_key}: 未声明的产物 {unknown}；"
                f"该接口声明的产物槽位是 {list(slots) or '（无）'}")
        sec, stack = self._locate(iface_owner, iface_name, full_key)
        if not stack:
            raise RegistryError(
                f"{_path(iface_owner, iface_name)} 里没有条目 {full_key!r}，无法回填产物")
        top = dict(stack[-1])
        top.setdefault("built", {})
        top["built"].update(built)
        sec[full_key] = list(stack[:-1]) + [top]
        return self._entry(point, full_key, sec[full_key], contract)

    def unbind(self, point, key, *names):
        """摘掉构建产物。"""
        iface_owner, iface_name, contract = self._interface(point)
        full_key = self._normalize_key(key)
        sec, stack = self._locate(iface_owner, iface_name, full_key)
        if not stack:
            raise RegistryError(
                f"{_path(iface_owner, iface_name)} 里没有条目 {full_key!r}，无法摘除产物")
        top = dict(stack[-1])
        slot = dict(top.get("built") or {})
        if not names:
            n = len(slot)
            slot = {}
        else:
            n = 0
            for name_ in names:
                if name_ in slot:
                    del slot[name_]
                    n += 1
        top["built"] = slot
        sec[full_key] = list(stack[:-1]) + [top]
        return n

    # ── 变更通知 ──

    def watch(self, point=None, callback=None):
        """盯接口的变更（增删改）：callback(接口路径)。"""
        self._watchers.append((point, callback))

    def unwatch(self, callback):
        self._watchers = [(p, cb) for p, cb in self._watchers if cb is not callback]

    def _notify(self, path):
        for point, cb in list(self._watchers):
            if point is not None and normalize(point) != path:
                continue
            try:
                cb(path)
            except Exception:
                pass

    # ── 加载会话 ──

    def in_session(self):
        return self._stage is not None

    def begin(self, registrant=None):
        """开一次加载会话。registrant 是会话主人（插件 id），返回凭据。"""
        if self._stage is not None:
            raise RegistryError("已经在加载会话里，不能嵌套（插件构造里别再开一个）")
        self._stage = {}
        self._session_owner = registrant
        self._session_token = object() if registrant is not None else None
        return self._session_token

    def _end_session(self, token=_ANY_TOKEN, force=False):
        if (not force and self._session_token is not None
                and token is not self._session_token):
            raise RegistryError(
                "这不是本次加载会话：有主人的会话只能由开始它的那一方（加载器）"
                "用自己拿到的凭据 commit/abort —— 插件在自己的构造里不要关会话")
        stage, self._stage = self._stage, None
        self._session_owner = None
        self._session_token = None
        return stage

    def commit(self, token=_ANY_TOKEN, *, force=False):
        """并进正表：**先全校验再落盘**，不会半途而废。返回并进去的条数。"""
        stage = self._end_session(token, force)
        if not stage:
            return 0
        problems = self._validate_stage(stage)
        if problems:
            raise RegistryError("登记校验失败，整块丢弃：\n  - " + "\n  - ".join(problems))
        n = 0
        for owner, sb in stage.items():
            b = self._bucket(owner, create=True)
            for name, contract in sb["declares"].items():
                b["declares"].setdefault(name, contract)
            for iface_owner, ifaces in sb["registers"].items():
                for iface_name, entries in ifaces.items():
                    sec = b["registers"].setdefault(iface_owner, {}).setdefault(iface_name, {})
                    for key, stack in entries.items():
                        sec[key] = stack
                        n += 1
            b["meta"].update(sb["meta"])
        for owner in stage:
            self._notify_owner(owner)
        return n

    def abort(self, token=_ANY_TOKEN, *, force=False):
        """丢掉这次会话的全部登记。"""
        stage = self._end_session(token, force)
        if not stage:
            return 0
        return sum(len(entries)
                   for sb in stage.values()
                   for ifaces in sb["registers"].values()
                   for entries in ifaces.values())

    def _validate_stage(self, stage):
        problems = []
        for owner, sb in stage.items():
            for name, contract in sb["declares"].items():
                path = _path(owner, name)
                if not contract.get("callingMode"):
                    problems.append(f"{path}: callingMode 必须显式声明")
            for iface_owner, ifaces in sb["registers"].items():
                for iface_name, entries in ifaces.items():
                    path = _path(iface_owner, iface_name)
                    if not self._declared_in(iface_owner, iface_name, stage):
                        problems.append(f"{path}: 接口未声明（{owner} 往它登记了东西）")
                        continue
                    contract = self._contract_of(iface_owner, iface_name, stage)
                    allowed = set(contract["fields"])
                    for key, stack in entries.items():
                        top = stack[-1]
                        unknown = sorted(set(top) - allowed - set(_INTERNAL))
                        if unknown:
                            problems.append(f"{path}#{key}: 未知字段 {unknown}")
                        missing = sorted(set(contract["required"]) - set(top))
                        if missing:
                            problems.append(f"{path}#{key}: 缺必填字段 {missing}")
        return problems

    def _declared_in(self, owner, name, stage):
        for table in list(reversed(self._tables())) + [stage]:
            b = table.get(owner)
            if b and name in b["declares"]:
                return True
        return False

    def _contract_of(self, owner, name, stage):
        for table in list(reversed(self._tables())) + [stage]:
            b = table.get(owner)
            if b and name in b["declares"]:
                return b["declares"][name]
        return {"fields": (), "required": (), "built": ()}

    # ── 卸载 / 清空 ──

    def remove_namespace(self, ns):
        """摘掉某个 owner 的全部痕迹：它自己的桶 + 别人桶里「往它接口登记」的部分。"""
        if self._stage is not None:
            raise RegistryError("加载会话里不能 remove_namespace（它直接改正表）")
        if ns in HOST_NAMESPACES:
            raise RegistryError(
                f"不能按 owner 摘宿主的条目（{ns!r}）：内置接口只在启动时声明一次")
        n = 0
        b = self.data.pop(ns, None)
        if b is not None:
            n += sum(len(entries) for ifaces in b["registers"].values()
                     for entries in ifaces.values())
            n += len(b["declares"])
        for owner, ob in list(self.data.items()):
            regs = ob["registers"]
            gone = regs.pop(ns, None)
            if gone:
                n += sum(len(entries) for entries in gone.values())
            for ifaces in regs.values():
                for entries in ifaces.values():
                    for key in list(entries):
                        kept = [x for x in entries[key] if x.get("by") != ns]
                        if kept != entries[key]:
                            entries[key] = kept
                            if not kept:
                                entries.pop(key, None)
            for iface_owner in [k for k, v in regs.items() if not v]:
                regs.pop(iface_owner, None)
        self._notify_owner(ns)
        return n

    def _notify_owner(self, owner):
        for point in self.points():
            if point.split("/", 1)[0] == owner:
                self._notify(point)

    def clear(self):
        self.data.clear()
        self._stage = None
        self._session_owner = None
        self._session_token = None
        self._watchers = []

    # ── 校验 / 转储 ──

    def validate(self):
        """全表扫一遍，返回问题清单（空列表 = 通过）。"""
        problems = []
        for owner, b in self.data.items():
            for name, contract in b["declares"].items():
                path = _path(owner, name)
                if not contract.get("callingMode"):
                    problems.append(f"{path}: callingMode 缺失")
            for iface_owner, ifaces in b["registers"].items():
                for iface_name, entries in ifaces.items():
                    path = _path(iface_owner, iface_name)
                    if not self.declared(path):
                        problems.append(f"{path}: 接口未声明（{owner} 往它登记了东西）")
                        continue
                    contract = self.contract(path)
                    allowed = set(contract["fields"])
                    for key, stack in entries.items():
                        if "/" not in key:
                            problems.append(f"{path}#{key}: key 不是 <owner>/<名字> 形式")
                        top = stack[-1]
                        unknown = sorted(set(top) - allowed - set(_INTERNAL))
                        if unknown:
                            problems.append(f"{path}#{key}: 未知字段 {unknown}")
                        missing = sorted(set(contract["required"]) - set(top))
                        if missing:
                            problems.append(f"{path}#{key}: 缺必填字段 {missing}")
        return problems

    def dump(self):
        """深拷贝一份（改它不会影响注册表；__ 开头的内部键也一并给出）。"""
        return copy.deepcopy(self.data)


def _path(owner, name):
    return f"{owner}/{name}"


# 全局单例：与 src/utils/bus.py 的 bus、src/utils/events.py 的 events 同一风格
registry = Registry()


def page(key, *, point="core/pages", **meta):
    """把一个 Page 子类登记进接口（装饰器）。

        @page("core/start")
        class Start(Page):
            name    = "core.wid.pages.start"
            icon    = BTN_START
            order   = 10
            default = True
    """
    def deco(cls):
        fields = registry.meta(point).get("fields", ())
        kw = dict(meta)
        kw.setdefault("init", lambda b: cls(btn=getattr(b, "btn", None)))
        kw.setdefault("title", cls.name)
        if "icon" in fields:
            kw.setdefault("icon", cls.icon)
        if "default" in fields:
            kw.setdefault("default", getattr(cls, "default", False))
        registry.add(point, key, **kw)
        return cls
    return deco
