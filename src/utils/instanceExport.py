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

整实例打包：把一个实例目录收成一个自描述的 zip（纯标准库）。

包内布局
--------
::

    bml-export.json          标记 + 元数据，导入端先认它
    mdt.jar                  客户端本体，**放顶层**
    BML.json                 实例元数据（javaPath 会在导入时重置）
    icon.png                 实例图标
    data/Mindustry/…         存档、设置、模组、蓝图

``mdt.jar`` 必须在顶层：这样接收方即使不用 BML，解压出来也能直接拿这个 jar
去手动导入，包不会变成「只有 BML 能读的黑盒」。

为什么用排除法
--------------
模组会在 ``data/`` 下自建任意名字的目录（logic-tool、BetterLogistics…），
白名单式的「只收 saves/mods/schematics」会静默漏掉它们：导出看着成功，导入
后模组配置全没了。所以口径是「实例目录里的一切，减去明确不该带的」。

不二次压缩
----------
``mdt.jar`` 与 ``mods/*.jar`` 本身已是 deflate 过的容器，再压一遍 CPU 花掉、
体积几乎不变（实测收益 < 1%）。按后缀把它们存成 STORED，其余文本与小文件
照常 deflate。

脱敏
----
``sanitize=True``（默认）时先向 :mod:`instanceSanitize` 要一份计划：哪些文件
不带、``settings.bin`` 剥成什么。它**只改包里的字节**，实例目录一个字节都不动
—— 导出是只读操作，用户导出完继续玩，设置与身份都还在。
"""

import json
import os
import time
import zipfile

from .instanceSanitize import SanitizeError, build_plan
from .jarImport import FORMAT_VERSION, MANIFEST_NAME, MANIFEST_TYPE

# 运行期状态文件，不是实例数据：装进包里只会让接收方看到一堆无意义的残留。
# downloading.json 记录的是「本机正在下载」这件事，换个环境毫无意义。
EXCLUDE_FILES = {"downloading.json"}
# 半截文件同理：.part 是拷贝/下载的中间态，收进去等于把垃圾一起送人。
EXCLUDE_SUFFIX = (".part", ".tmp")

# 已经压过的容器，直接存
STORE_SUFFIX = (".jar", ".zip", ".png", ".jpg", ".jpeg", ".ogg", ".mp3")

# 写入块大小：1 MiB。与 jarImport.CHUNK 同源 —— 进度信号既不能太密
# （100 MB 的包发两万次），也不能太疏（点一下卡住然后突然完成）。
CHUNK = 1024 * 1024

# 失败码：与 jarImport 的 ERR_* 同一套命名，界面按 "err.<code>" 取文案
ERR_EMPTY = "empty"            # 实例目录里没有可打包的内容
ERR_DEST_INSIDE = "destInside"  # 保存位置落在了实例目录内部
ERR_IO = "ioError"
ERR_CANCELLED = "cancelled"
# settings.bin 读不出来（settingsUnreadable）由 instanceSanitize 抛 SanitizeError
# 带过来 —— 失败码只在那一处定义，这里不抄第二份


class _Cancelled(Exception):
    """内部信号：用异常跳出多层写入循环，避免每层都判断返回值。"""


def _should_skip(name):
    if name in EXCLUDE_FILES:
        return True
    return name.lower().endswith(EXCLUDE_SUFFIX)


def collect(instance_dir, include_data=True, plan=None):
    """扫出要打包的文件，返回 ``([(相对路径, 绝对路径, 字节数)], 总字节, 脱敏丢弃数)``。

    相对路径一律用 ``/``：zip 内部路径就是这种写法，Windows 的反斜杠进去会
    变成文件名的一部分，解压时得到一堆 ``data\\Mindustry`` 这样的怪目录。

    include_data=False 时只收实例根上的文件（客户端本体、BML.json、图标），
    用于「只想要这个客户端外壳」的场景。

    plan 非空时按它过滤（``server_list.json``、崩溃日志等整份不进包）。被丢掉的
    文件不计入总字节，也不进进度条 —— 进度分母只算真正要写的量。
    """
    root = os.path.abspath(instance_dir)
    entries = []
    total = 0
    dropped = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        top = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        if not include_data and (top == "data" or top.startswith("data/")):
            dirnames[:] = []   # 整个 data 子树都不进
            continue
        # 整棵剪掉要丢的目录：省掉逐文件判断，也保证空目录不会漏进包
        if plan is not None and dirnames:
            keep = []
            for name in dirnames:
                sub = (top + "/" + name) if top else name
                if plan.drops(sub + "/"):
                    dropped += 1
                    continue
                keep.append(name)
            dirnames[:] = keep
        for fn in filenames:
            if _should_skip(fn):
                continue
            rel = (top + "/" + fn) if top else fn
            if plan is not None and plan.drops(rel):
                dropped += 1
                continue
            abs_path = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                # 扫描后被删了（游戏正在轮转日志之类）：跳过，不要因为它整包失败
                continue
            entries.append((rel, abs_path, size))
            total += size
    return entries, total, dropped


def _zip_info(rel, abs_path, compressed):
    """给一个条目定压缩方式与时间戳。

    mtime 取文件的真实修改时间而不是「现在」：存档的时间信息在导入后仍应
    保留，用户按日期分辨存档时用得上。
    """
    try:
        mtime = time.localtime(os.path.getmtime(abs_path))[:6]
    except OSError:
        mtime = time.localtime()[:6]
    info = zipfile.ZipInfo(rel, date_time=mtime)
    info.compress_type = zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED
    # 0644：解压出来是可读写、所有人可读，不带执行位
    info.external_attr = 0o644 << 16
    return info


def export_instance(instance_dir, dest, meta=None, progress=None, cancel=None,
                    include_data=True, sanitize=True):
    """把实例目录写成 dest，返回 ``(ok, code, stats)``。

    code 成功为 None；失败为 ERR_* 之一，或脱敏层给出的 settingsUnreadable
    （此时 stats 里带 {"detail": 出错的相对路径与原因}，只用于写日志）。
    progress 收 0.0–1.0，在**调用方线程**里被调（界面传 Signal.emit）。
    cancel 是一个无参可调用对象，返回 True 就中止并删掉半成品。

    sanitize=True 时按 :mod:`instanceSanitize` 的计划去掉身份信息：整份丢掉
    服务器收藏夹 / 崩溃日志 / 设置备份，剥掉 settings.bin 里的 usid-*、uuid、
    ip、封禁名单，并从 BML.json 拿掉设置镜像与本机绝对路径。只改包里的字节，
    实例目录本身不动。

    先写 ``dest.part`` 再改名：中途取消/磁盘满时不会留下一个「看起来存在、
    实际打不开」的 zip 让用户以为导出成功了。
    """
    root = os.path.abspath(instance_dir)
    if not os.path.isdir(root):
        return False, "missing", None

    plan = None
    if sanitize:
        try:
            plan = build_plan(root, include_data)
        except SanitizeError as exc:
            # 读不出来就不导出：宁可让用户关掉这个勾、明确选择「照原样打包」，
            # 也不把一个没法确认内容的东西塞进标着「已抹去个人信息」的包
            return False, exc.code, {"detail": exc.detail}

    entries, total, dropped = collect(root, include_data, plan)
    if not entries:
        return False, ERR_EMPTY, None

    dest_abs = os.path.abspath(dest)
    # 保存位置不能落在实例目录里：边写边扫会把正在生成的 zip 也算成一个
    # 待打包文件，轻则包内多一个莫名其妙的大文件，重则写到一半去读自己。
    # 比较用 normcase：Windows 路径大小写不敏感，用户手输的目录大小写稍一不同，
    # commonpath 就判不出「在里面」了。
    try:
        root_cmp = os.path.normcase(root)
        dest_cmp = os.path.normcase(dest_abs)
        if os.path.commonpath([root_cmp, dest_cmp]) == root_cmp:
            return False, ERR_DEST_INSIDE, None
    except ValueError:
        pass   # 不同盘符，commonpath 抛错；那必然不在内部

    manifest = dict(meta or {})
    manifest["format"] = FORMAT_VERSION
    manifest["type"] = MANIFEST_TYPE
    manifest.setdefault("exported_at", int(time.time()))
    manifest["include_data"] = bool(include_data)
    # 标记脱敏与否：接收方（以及事后复盘的自己）能看出这个包里的 usid 是被
    # 剥掉的、还是本来就没有
    manifest["sanitized"] = bool(sanitize)

    part = dest_abs + ".part"
    done = 0
    written = 0
    skipped = 0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            # 标记文件第一个写：即使后面某个文件读失败，至少要让人能看出来
            # 这是个什么包、由哪个版本导出
            zf.writestr(MANIFEST_NAME,
                        json.dumps(manifest, ensure_ascii=False, indent=2))
            for rel, abs_path, size in entries:
                if cancel is not None and cancel():
                    raise _Cancelled()
                blob = plan.rewrite_for(rel) if plan is not None else None
                if blob is not None:
                    # 改写过的条目（settings.bin / BML.json）：字节来自计划，
                    # 时间戳仍取盘上原文件，接收端看起来像「原本就这样」
                    with zf.open(_zip_info(rel, abs_path, True), "w",
                                 force_zip64=True) as wf:
                        wf.write(blob)
                    done += size
                    if progress is not None and total:
                        progress(min(1.0, done / total))
                    written += 1
                    continue
                compressed = not rel.lower().endswith(STORE_SUFFIX)
                try:
                    rf = open(abs_path, "rb")
                except OSError:
                    # 扫描之后被删/被独占：跳过，并让调用方知道有几份没进包。
                    # 游戏运行中导出时日志与被锁的存档会走到这里。
                    skipped += 1
                    continue
                with rf, zf.open(_zip_info(rel, abs_path, compressed), "w",
                                 force_zip64=True) as wf:
                    while True:
                        buf = rf.read(CHUNK)
                        if not buf:
                            break
                        wf.write(buf)
                        done += len(buf)
                        if progress is not None and total:
                            progress(min(1.0, done / total))
                written += 1
        os.replace(part, dest_abs)
    except _Cancelled:
        _remove(part)
        return False, ERR_CANCELLED, None
    except OSError:
        # 磁盘满、路径不可写、文件名过长
        _remove(part)
        return False, ERR_IO, None
    except BaseException:
        # 进程被杀 / KeyboardInterrupt 也要清半成品
        _remove(part)
        raise

    try:
        zip_bytes = os.path.getsize(dest_abs)
    except OSError:
        # zip 已经改名成功了，只是紧接着被别的程序挪走 —— 报失败会让人以为
        # 白导了一遍。大小当 0（界面只拿它显示一行统计）。
        zip_bytes = 0
    stats = {"files": written, "skipped": skipped, "bytes": total,
             "zip_bytes": zip_bytes, "sanitized": bool(sanitize),
             "dropped": dropped}
    if plan is not None:
        stats.update(plan.summary())
    return True, None, stats


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
