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

本模块不 import Qt，也不 import src 下的任何东西。校验与拷贝都能在子线程里
跑，也能脱离界面单独测（见 ``_selftest`` 段落所对应的手工验证）。
"""

import os
import zipfile

# 失败码：与 mdtManager.importJar 的返回值同一套，界面按 "err.<code>" 取文案
ERR_MISSING = "missing"        # 文件不存在 / 不是文件
ERR_NOT_ZIP = "notZip"         # 打不开的压缩包（半截文件、改名过的 exe）
ERR_NO_VERSION = "noVersion"   # 缺 version.properties，BML 认不出来
ERR_NO_MAIN = "noMain"         # 缺 Main-Class，java -jar 起不来

# 拷贝块大小：1 MiB。取 4 KiB 会让 100 MB 的包发三万次进度信号，
# 取整个文件又退化成「点一下卡住、然后突然完成」。
CHUNK = 1024 * 1024


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


def inspect_jar(path):
    """看这个 jar 能不能当实例用。返回字典：

        ok        能不能收（下面三项全过才是 True）
        error     失败码（见模块顶部 ERR_*），成功为 None
        build / modifier / number / type   version.properties 里的四项
        main      MANIFEST.MF 里声明的 Main-Class
        size      字节数（界面上的大小提示）

    只读 zip 的中央目录：90 MB 的包也是毫秒级，所以「先验一下」不会变成
    选完文件后那段莫名的等待。
    """
    info = {"ok": False, "error": None, "build": "", "modifier": "",
            "number": "", "type": "", "main": "", "size": 0}
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
            names = zf.namelist()
            if "version.properties" not in names:
                info["error"] = ERR_NO_VERSION
                return info
            props = _read_props(zf.read("version.properties"))
            for key in ("build", "modifier", "number", "type"):
                info[key] = props.get(key, "")
            info["main"] = _main_class(zf)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        # BadZipFile：不是 zip；OSError：读不动（权限/占用）；RuntimeError：
        # 加密包。三种在用户眼里是同一件事——「这文件不能当 jar 用」。
        info["error"] = ERR_NOT_ZIP
        return info

    if not info["main"]:
        info["error"] = ERR_NO_MAIN
        return info
    info["ok"] = True
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


def suggest_name(info, path, prefix="Mindustry"):
    """给实例起个默认名：``Mindustry-<build>``（非正式版再加 ``-<modifier>``）。

    与下载页的「<界面名>-<版本>」同源（见下载页的 _init_name_input），
    于是在列表里，导入的实例和下载来的实例长得一样，不会一半叫
    「Mindustry-146」一半叫「Mindustry-149-beta」。

    取不到 build（version.properties 写了别的字段）就退回文件名 —— 名字只是
    默认值，用户在弹窗里可以改，猜错不比留空更糟。
    """
    build = str(info.get("build") or "").strip()
    modifier = str(info.get("modifier") or "").strip()
    if build:
        name = "%s-%s" % (prefix, build)
        if modifier and modifier != "release":
            name += "-" + modifier
        return name
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
