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

导入本地 jar：验包、起名、原子落盘（纯标准库）。

为什么单独一个模块
------------------
下载页那条路是「远程 → 临时文件 → 实例目录」，每一步都有下载器盯着；导入这条
路只有一次本地拷贝，**校验反而更要紧** —— 用户手里那个 jar 可能是别的项目、
可能只拷了一半，也可能是只含依赖的构建产物（素材库里那个 dependencies.jar
就是这样：version.properties 有，但没有 Main-Class）。

两条硬性要求都不是这里凭空加的，而是 BML 自己的下游定下的：

- ``mdtManager.isMdtFile`` 认的是 jar 里的 ``version.properties``。缺了它，
  目录建好也**永远不会出现在列表里**，而 ``taken_names`` 仍然把这个目录算作
  已占用 —— 用户看到的是「导入了、列表里没有、这名字还不让用」。
- 启动走的是 ``java -jar``（见 mdtLauncher），要 ``META-INF/MANIFEST.MF``
  里的 ``Main-Class``。缺了它，实例能进列表，点启动才炸在 Java 那句
  「no main manifest attribute」上 —— 错误离操作已经隔了一次点击。

所以先验后拷：验不过一个字节都不写。

版本号从哪来
------------
一个 fork 的 jar 里有两套版本信息，各答各的问题：

- ``mod.hjson`` 的 ``version`` 是它**自己**的发布版本（MindustryX 是
  ``2026.10.X38``）。只读 ``version.properties`` 会把 MDTX 显示成 MDT 的版本号。
- ``version.properties`` 的 ``build`` 是它**从哪个上游构建分出来**（``160.5``）。
  这个值是上游 gradle 构建时写进 jar 的，fork 只改自己的版本线、不动它 ——
  所以它比 ``mod.hjson`` 的 ``minGameVersion`` 可靠：后者是「**最低**能跑的
  游戏版本」，一个基于 160.5 分出来的改端完全可以声明 146 去兼容旧存档。

显示用前者（见 ``version_text``），「（基于 160.5）」的注脚用后者
（见 ``upstream_version``）。``minGameVersion`` 只在 build 不可用时兜底。

本模块不 import Qt，也不 import src 下的任何东西。校验与拷贝都能在子线程里
跑，也能脱离界面单独测（见 ``_selftest`` 段落所对应的手工验证）。
"""

import json
import os
import time
import zipfile

# 实例包的标记文件：导出时写在 zip 顶层，与 mdt.jar 并列。
#
# 为什么用标记文件而不是「猜结构」：一个用户自己压的 zip 里完全可能恰好有
# 个叫 mdt.jar 的条目，靠猜会把它当成 BML 实例包收进来。反过来，标记文件
# 在不在是一个明确事实，判断没有歧义。它顺带还能携带导出时的版本、是否
# 脱敏等信息，导入界面不用为此再解一遍上百 MB 的 mdt.jar。
MANIFEST_NAME = "bml-export.json"
MANIFEST_TYPE = "bml-instance"
# 当前写出的格式版本。读的时候只接受 <= 这个数：比它新说明是后来的启动器
# 导的，可能带本版本不认识的条目，装作能读比直接拒绝更危险。
FORMAT_VERSION = 1

# 失败码：与 mdtManager.importJar 的返回值同一套，界面按 "err.<code>" 取文案
ERR_MISSING = "missing"        # 文件不存在 / 不是文件
ERR_NOT_ZIP = "notZip"         # 打不开的压缩包（半截文件、改名过的 exe）
ERR_NO_VERSION = "noVersion"   # 缺 version.properties，BML 认不出来
ERR_NO_MAIN = "noMain"         # 缺 Main-Class，java -jar 起不来
ERR_NO_CLIENT = "noClient"     # 实例包里没有 mdt.jar
ERR_BAD_MANIFEST = "badManifest"  # 标记文件读不懂 / 格式版本不认识
ERR_UNSAFE = "unsafeArchive"   # 包里有指向目录外的路径（zip slip）

# 拷贝块大小：1 MiB。取 4 KiB 会让 100 MB 的包发三万次进度信号，
# 取整个文件又退化成「点一下卡住、然后突然完成」。
CHUNK = 1024 * 1024

# fork（MindustryX 等）在 jar 根上放的模组说明文件。官方包没有它，所以
# 「有没有这个文件」本身就是「这是不是改端」的判据。
#
# 这里只收它的自我声明：name（界面名）、version（它自己的发布版本，落到
# modVersion）、minGameVersion（最低兼容的游戏版本，原样存着当兜底线索）。
# 注意 minGameVersion **不是**「基于哪一版」—— 那是 version.properties 的
# build 说的（见 upstream_version），别拿它当基座。
MOD_FILE = "mod.hjson"


def _read_props(raw):
    """解析 version.properties（java Properties 的一个够用子集）。

    只认 ``键=值`` 与 ``#`` / ``!`` 开头的注释：游戏自己生成的就这两样。
    续行、``\\uXXXX`` 转义这些在版本号这种短值上不会出现，真出现也只是
    取不到值 —— 不影响「这是不是一个客户端」的判断。
    """
    props = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line[0] in "#!":
            continue
        key, sep, value = line.partition("=")
        if sep:
            props[key.strip()] = value.strip()
    return props


def blank_info():
    """一份空结果，字段固定 —— 界面和 mdtManager 都按这几个键读。"""
    return {"ok": False, "kind": None, "error": None,
            "build": "", "modifier": "", "number": "", "type": "",
            "mod": "", "modVersion": "", "minGameVersion": "",
            "main": "", "size": 0,
            "meta": {}, "members": 0, "unpacked": 0}


def _strip_hjson_comment(text):
    """去掉引号外的行尾注释（`"160.5" # x` / `160.5 // x`）。

    只看引号外的字符：值本身可能含 `#`（名字里少，但别假设），quoted 之后
    这些字符都算正文。
    """
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return text[:i]
        elif ch == "/" and text[i + 1:i + 2] == "/":
            return text[:i]
    return text


def _hjson_value(text):
    """取一个 hjson 标量：去引号、去行尾注释。

    真样本是 `version: "2026.10.X38"` 这种，够用就行 —— 不引 hjson 库
    （这个文件约定不 import 第三方，也避免为了四个字段把整包解析一遍）。
    """
    value = _strip_hjson_comment(text).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _read_mod_hjson(raw):
    """从 mod.hjson 文本里取 name / version / minGameVersion。

    只做行级的 `键: 值` 匹配，键名**精确**比较（`xversion:` / `versions:`
    都不许命中）。取不到的键留空串。
    """
    out = {"mod": "", "modVersion": "", "minGameVersion": ""}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line[0] in "#/":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if key == "name":
            out["mod"] = _hjson_value(value)
        elif key == "version":
            out["modVersion"] = _hjson_value(value)
        elif key == "minGameVersion":
            out["minGameVersion"] = _hjson_value(value)
    return out


def read_fork_info(zf):
    """从已打开的 jar 里读 fork 声明（mod.hjson），返回那三个字段。

    读不到 / 不是 fork 都返回空串，调用方拿 `modVersion` 判「这是不是改端」。
    真样本只有 ~170 B；超过 64 KiB 的不猜 —— 那不是一个正经的 mod.hjson。
    """
    empty = {"mod": "", "modVersion": "", "minGameVersion": ""}
    try:
        entry = zf.getinfo(MOD_FILE)
        if entry.file_size > 64 * 1024:
            return empty
        raw = zf.read(MOD_FILE).decode("utf-8", "replace")
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile, ValueError):
        return empty
    return _read_mod_hjson(raw)


def inspect_package(path):
    """看这个 .jar/.zip 是什么，返回 blank_info() 那套字段。

    ``kind`` 只有两种合法值：

    - ``"jar"``      客户端 jar，只有一个 mdt.jar 的分量，导入后是空存档的新实例
    - ``"instance"`` BML 导出的整实例包，带存档、模组、蓝图

    判别顺序是**先标记、后内容**：顶层有 ``bml-export.json`` 就是实例包，没有
    才按 ``version.properties`` 认客户端。这个顺序不能反 —— 实例包里的
    ``mdt.jar`` 是个嵌套 zip，顶层并没有 version.properties，按内容先判会得到
    「noVersion」，让用户以为自己的包坏了。

    只读 zip 中央目录，90 MB 的包也是毫秒级；实例包不解压、不展开 mdt.jar，
    版本信息直接取标记文件里记的。
    """
    info = blank_info()
    try:
        if not os.path.isfile(path):
            info["error"] = ERR_MISSING
            return info
        info["size"] = os.path.getsize(path)
    except OSError:
        info["error"] = ERR_MISSING
        return info

    try:
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            names = {i.filename for i in infos}
            if MANIFEST_NAME in names:
                return _inspect_instance(zf, infos, names, info)
            if "version.properties" in names:
                return _inspect_client(zf, info)
            if "mdt.jar" in names:
                # 结构像实例包但没有标记：可能是用户解压后重新压缩时漏了这个
                # 文件，也可能是别的启动器的包。两种都不该按「坏 jar」报错，
                # 那样提示的是「缺 version.properties」，跟真正的原因无关。
                info["error"] = ERR_BAD_MANIFEST
                return info
            info["error"] = ERR_NO_VERSION
            return info
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        # BadZipFile：不是 zip；OSError：读不动（权限/占用）；RuntimeError：
        # 加密包。三种在用户眼里是同一件事——「这文件不能当包用」。
        info["error"] = ERR_NOT_ZIP
        return info


def _inspect_client(zf, info):
    """按客户端 jar 检查：version.properties 与 Main-Class 缺一不可。"""
    props = _read_props(zf.read("version.properties"))
    for key in ("build", "modifier", "number", "type"):
        info[key] = props.get(key, "")
    # fork 的 mod.hjson 与 version.properties 并列：前者说「我是谁、我这一版叫什么」，
    # 后者说「我基于哪个官方构建」。两者都要，显示时取前者、注脚用后者。
    info.update(read_fork_info(zf))
    info["main"] = _main_class(zf)
    info["kind"] = "jar"
    info["members"] = 1
    if not info["main"]:
        info["error"] = ERR_NO_MAIN
        return info
    info["ok"] = True
    return info


def _inspect_instance(zf, infos, names, info):
    """按实例包检查：标记文件可解析、格式版本认识、mdt.jar 在场。"""
    try:
        meta = json.loads(zf.read(MANIFEST_NAME).decode("utf-8", "replace"))
    except (KeyError, ValueError, UnicodeError, OSError):
        info["error"] = ERR_BAD_MANIFEST
        return info
    if not isinstance(meta, dict) or meta.get("type") != MANIFEST_TYPE:
        info["error"] = ERR_BAD_MANIFEST
        return info
    fmt = meta.get("format")
    if not isinstance(fmt, int) or isinstance(fmt, bool) or not (1 <= fmt <= FORMAT_VERSION):
        info["error"] = ERR_BAD_MANIFEST
        return info
    if "mdt.jar" not in names:
        info["error"] = ERR_NO_CLIENT
        return info

    files = [i for i in infos if not i.is_dir()]
    info["kind"] = "instance"
    info["meta"] = meta
    info["members"] = len(files)
    info["unpacked"] = sum(i.file_size for i in files)
    # 版本信息取标记文件里记的：解一遍 mdt.jar 只为读几个字段不值当。
    # build 是上游构建号，导入方据此算基座（见 upstream_version）；mod /
    # modVersion / minGameVersion 是 fork 的自我声明，老包没有这几个键，
    # 取到空串就按官方包显示（与 jarImport 那侧同一套回落）。
    for key in ("build", "modifier", "number", "type",
                "mod", "modVersion", "minGameVersion"):
        info[key] = str(meta.get(key) or "")
    info["ok"] = True
    return info


def inspect_jar(path):
    """只认客户端 jar 的旧接口；新代码请用 inspect_package。

    传入实例包时故意判成失败：这个函数的所有调用方都以为「成功 = 拿到了一个
    能直接当 mdt.jar 用的文件」，把整包当 jar 收进去会得到一个几百 MB 的
    mdt.jar，启动时才炸。
    """
    info = inspect_package(path)
    if info["kind"] == "instance":
        info["ok"] = False
        info["error"] = ERR_NO_VERSION
    return info


def _main_class(zf):
    """取 MANIFEST.MF 的 Main-Class（没有就返回空串）。

    manifest 规范是每行不超过 72 字节、长值折行后以单个空格续行；Main-Class
    这种类名不会那么长，这里只处理不折行的情况，取不到就当没有 —— 宁可让
    用户看到「缺 Main-Class」也不去猜一个类名出来。
    """
    try:
        manifest = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except KeyError:
        return ""
    for line in manifest.splitlines():
        if line.lower().startswith("main-class:"):
            return line.split(":", 1)[1].strip()
    return ""


def version_text(info, prefix="v", sep=" "):
    """把客户端声明的版本拼成一句人看的版本号：``v160.4`` / ``2026.10.X38``。

    两个来源，先看 fork 自己的：

    - ``modVersion``：jar 根上 ``mod.hjson`` 的 ``version``。MindustryX 这类
      改端**自己有版本线**（``2026.10.X38``），而 ``version.properties`` 里的
      build 记的是它基于的官方构建 —— 只读后者会把 MDTX 显示成 MDT 的版本，
      这正是「明明装的是 X38，界面上却是 v160.5」的来源。fork 的版本串自带
      一套写法，原样显示，不加 ``v`` 前缀（官方界面也不加）。
    - ``build``：没有 ``mod.hjson`` 的包走这条 —— 官方包，以及 CN-ARC、
      MindustryY 这类直接把自己的构建号写进 build 的 fork（ARC 的 build 就是
      ``30936``，本来就不带上游版本）。``number`` 是**主版本号**（Mindustry
      源码注释 *Number specifying the major version*，v8 就是 8），官方界面
      从不显示它，只用来判断「这是哪一代」；``modifier`` 是通道标记（release /
      beta / steam），不是版本的一部分。以前三样点号一连，出来的是
      ``v8.160.4release`` —— 前头多了个主版本号、后头缺分隔符、还把通道塞进
      了版本号里。

    ``sep`` 给名字用：实例名不允许空格，传 ``"-"`` 得到 ``160.4-beta``。

    取不到可用的版本（自定义构建写 0 或 -1，或字段整个缺失）时返回空串，由
    调用方当「没有版本号」处理 —— 显示 ``v0`` 比空着更容易让人以为装错了。
    """
    if not info:
        return ""
    fork = str(info.get("modVersion") or "").strip()
    if fork:
        return fork
    build = str(info.get("build") or "").strip()
    # 0 / -1 是 Mindustry 给自定义构建的占位值，不是真版本号。
    # build 缺失时退一级用主版本号：老 jar 或第三方打包可能只写了 number。
    core = build if build not in ("", "0", "-1") else str(info.get("number") or "").strip()
    if core in ("", "0", "-1"):
        return ""
    modifier = str(info.get("modifier") or "").strip()
    # 正式版不缀 modifier：用户要看的是版本，不是「它属于 release 通道」
    if modifier and modifier != "release":
        return prefix + core + sep + modifier
    return prefix + core


def _looks_like_version(value):
    """像不像一个版本号：首字符必须是数字，其余只允许数字/点/字母/`-`/`_`。

    专挡 gradle 的默认值 ``"custom"``（``upstreamBuild ?: "custom"``）：真出现
    时它表示「没设基座」，不是「基座叫 custom」。不挡的话界面上会写出
    「基于 custom」。宁可返回 False（退化成不显示基座）。
    """
    if not value or not value[0].isdigit():
        return False
    return all(ch.isdigit() or ch.isalpha() or ch in ".-_" for ch in value)


def _usable_build(value):
    """``version.properties`` 里的 build 能不能当版本串用。

    0 / -1 是 Mindustry 给自定义构建的占位值（``build = -1`` 表示「不是从
    某个 release tag 构建的」），既不是版本号也不该出现在「基于 X」里。
    """
    build = str(value or "").strip()
    if build in ("", "0", "-1"):
        return ""
    return build if _looks_like_version(build) else ""


def upstream_version(info):
    """这个 jar 从哪个官方构建分出来 —— ``version.properties`` 的 ``build``。

    返回**裸版本串**（``160.5``），拼成什么话由界面决定（「基于 160.5」）。

    为什么是 build 而不是 ``mod.hjson`` 的 ``minGameVersion``：改端有两类，
    build 对两类都说真话，``minGameVersion`` 只对一类勉强沾边。

    - **保留上游 version.properties 的**（MindustryX）：build 仍是上游构建号
      （``160.5``），只额外声明自己的版本线（``mod.hjson`` 的 ``version``）。
      这时 build 精确回答「我从哪一版分出来」。
    - **直接改 build 的**（CN-ARC、MindustryY 这类纯 fork）：build 就是它自己
      的构建号（ARC 是 ``30936``）。这时它与显示版本相同，本函数返回空串 ——
      不显示注脚，正好。

    ``minGameVersion`` 回答的是另一个问题：「**最低**兼容哪个游戏版本」，是给
    模组加载器做兼容判断的，可以远低于实际分支点（基于 160.5 的改端完全可以
    声明 146 去兼容旧存档）。拿它当基座，界面上会写出「基于 146」而实例里跑
    的其实是 160.5 的代码。

    ``minGameVersion`` 只在 build 不可用时兜底：build 为 0 / -1（自定义构建的
    占位值）或字段整个缺失时，它至少是个线索，比什么都不显示强。

    返回空串的情形，都是有意的：

    - 官方包 / 直接改 build 的 fork：build 就是显示版本，缀一句「基于 160.4」
      只是同义反复；
    - 兜底值也不像版本号（gradle 默认的 ``custom``）—— 那是「没设」，不是版本。
    """
    if not info:
        return ""
    shown = version_text(info, prefix="", sep="-")
    base = _usable_build(info.get("build"))
    if not base:
        fallback = str(info.get("minGameVersion") or "").strip()
        if _looks_like_version(fallback):
            base = fallback
    if not base or base == shown:
        return ""
    return base


def suggest_name(info, path, prefix="Mindustry"):
    """给实例起个默认名：``Mindustry-<build>`` / ``MindustryX-<版本>``。

    与下载页的「<界面名>-<版本>」同源（见下载页的 _init_name_input），
    于是在列表里，导入的实例和下载来的实例长得一样，不会一半叫
    「Mindustry-146」一半叫「Mindustry-149-beta」。fork 连界面名一起换：
    MindustryX 的包默认叫 ``MindustryX-2026.10.X38``，与下载页那边
    「MindustryX-<release 名>」对得上。

    取不到版本（version.properties 写了别的字段）就退回文件名 —— 名字只是
    默认值，用户在弹窗里可以改，猜错不比留空更糟。

    实例包优先用包里记的原实例名：用户导出的可能就叫「我的整合」，按 build
    重起一个「Mindustry-160.4」反而把他自己的命名弄丢了。
    """
    if info.get("kind") == "instance":
        original = str((info.get("meta") or {}).get("name") or "").strip()
        if original:
            return original
    # fork 自报的名字优先（MindustryX），官方包没有这一项就沿用调用方给的。
    # 只在这种名字「看起来能当目录名」时采用：太长的、带 Windows 非法字符的
    # 都退回调用方的前缀 —— 默认名再准也只是默认值，不该先给一个存不下去的。
    mod = str((info or {}).get("mod") or "").strip()
    if mod and len(mod) <= 16 and not any(ch in mod for ch in '\\/:*?"<>|'):
        prefix = mod
    # 名字里不能有空格，拼接规则本身与界面上的版本号同源，只换个分隔符
    core = version_text(info, prefix="", sep="-")
    if core:
        return "%s-%s" % (prefix, core)
    stem = os.path.splitext(os.path.basename(path or ""))[0]
    return stem or prefix


def copy_jar(src, dst, progress=None):
    """把 jar 拷到 dst：先写 ``dst.part``，拷完再改名。

    ``.part`` 那一步不是洁癖。直接往 mdt.jar 上写，中途失败（磁盘满、源文件
    被拔、进程被杀）会留下一个半截文件：zipfile 打不开它，``isMdtFile`` 因此
    判定「这不是实例」，而目录已经占了名字，用户得自己去 .Mindustrys 里删。

    progress 收到 0.0–1.0 的浮点；它在**调用方的线程**里被调用（导入时是子
    线程），所以传进来的必须是线程安全的东西（界面传的是 Signal.emit）。
    """
    part = dst + ".part"
    total = max(1, os.path.getsize(src))
    done = 0
    try:
        with open(src, "rb") as rf, open(part, "wb") as wf:
            while True:
                buf = rf.read(CHUNK)
                if not buf:
                    break
                wf.write(buf)
                done += len(buf)
                if progress is not None:
                    progress(min(1.0, done / total))
            wf.flush()
            os.fsync(wf.fileno())
        os.replace(part, dst)
    except BaseException:
        # 含 KeyboardInterrupt / 进程退出：半截文件一律不留在实例目录里，
        # 否则下次同名导入会看到「目录已存在」而其实里面什么都没有。
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def extract_package(path, target, progress=None):
    """把实例包解到 target，返回 ``(ok, code)``。

    三道防护，都不是可选的：

    1. **zip slip**：条目名形如 ``../../Windows/System32/x.dll`` 或直接是绝对
       路径时，解压会写到目标目录之外。判断用 realpath 而不是字符串前缀 ——
       目录里若有符号链接，字符串前缀会给出错误的安全感。
    2. **加密包**：读加密条目时 zipfile 抛 RuntimeError，转成 notZip，不让它
       半途而废地留下一半文件。
    3. **mtime 还原**：存档的修改时间按日期排序时有用，解出来全变成「现在」
       会让用户分不清哪个是新档。

    解压本身不校验包内结构：验客户端交给调用方（解出来的 mdt.jar 还要过一遍
    inspect_jar），这里只负责「把字节安全地放到位」。
    """
    root = os.path.realpath(target)
    os.makedirs(root, exist_ok=True)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            files = [i for i in zf.infolist() if not i.is_dir()]
            total = sum(i.file_size for i in files) or 1
            done = 0
            for info in files:
                name = info.filename.replace("\\", "/")
                dest = os.path.realpath(os.path.join(root, *name.split("/")))
                if dest != root and not dest.startswith(root + os.sep):
                    return False, ERR_UNSAFE
                parent = os.path.dirname(dest)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with zf.open(info) as rf, open(dest, "wb") as wf:
                    while True:
                        buf = rf.read(CHUNK)
                        if not buf:
                            break
                        wf.write(buf)
                        done += len(buf)
                        if progress is not None:
                            # 留 1% 给调用方的收尾（搬运、写元数据），
                            # 进度条走到 100% 却还在转是最难受的
                            progress(min(0.99, done / total))
                try:
                    stamp = time.mktime(info.date_time + (0, 0, -1))
                    os.utime(dest, (stamp, stamp))
                except (OSError, OverflowError, ValueError):
                    pass
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        return False, ERR_NOT_ZIP
    return True, None
