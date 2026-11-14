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

导出前的脱敏策略：哪些文件整份不带、哪些键当场剥掉。

为什么需要这一层
----------------
整实例导出会把 ``data/Mindustry/settings.bin`` 原样打进包，而它装着：

  * ``usid-<服务器>`` —— Mindustry 的服务器身份（``Packets$ConnectPacket.usid``）。
    Administration 拿它判管理员 / 封禁，**没有任何签名**：谁拿到这串，在那一台
    服务器上就是你。这是全包里唯一真能导致「冒充」的东西。
  * ``uuid`` —— 与 usid 并列的客户端身份值。
  * ``ip`` —— 上次连的服务器地址。
  * ``ip-bans`` / ``banned-names`` —— 你封过的人。**别人的 IP 与昵称**，与
    「给自己脱敏」无关，纯属不该外流。

同一个目录下还有几份等价物，只剥主文件等于没剥：

  * ``server_list.json`` —— 你去过哪些服务器（本机实测 89 台）；
  * ``settings_backups/`` 与 ``settings_backup.bin`` —— 设置文件的副本，
    主文件里剥掉的 usid 它们里面照旧；
  * ``crashes/`` / ``last_log.txt`` / ``*.log`` —— 故障证据，带设置转储与
    完整本机路径。

另外 ``BML.json`` 里有一份设置的 JSON 镜像（``mdtData``）和两个绝对路径
（``javaPath``、``icon_path``），它们同样指向这台机器、同样复制了身份键。

两条纪律（与安卓端的 SharePack 同源）
------------------------------------
① **只删该删的**：没有敏感键时直接沿用原字节，连重编码都不做 —— 保证
   「本来就没有身份信息 ⇒ 打出来的包与不脱敏时逐字节相同」。
② **读不出来就不导出**：``settings.bin`` 解析失败时抛 :class:`SanitizeError`，
   由调用方拒绝导出，而不是「原样塞进去 + 小字提示」。一个「没法确认里面
   有什么」的文件混进标着「已抹去个人信息」的包里，是把风险留给用户自己发现。
   想强行导出的人可以关掉那个勾 —— 那是一次有意识的选择。

刻意不动的
----------
  * ``name`` —— 游戏昵称。它是身份**关联**、不是凭据（冒充不了任何人），
    删掉会让收包的人进游戏后发现自己没名字。
  * ``data/Mindustry/mods/**`` —— 模组自己的文件。``mods/config/settings.bin``
    与 ``mods/x/server_list.json`` 是别的模组的数据，判据只认数据根**顶层**，
    不做 ``endswith`` 之类的模糊匹配，否则会把它们一起吃掉。
  * 存档 / 蓝图里可能带作者名 —— 那是「这图是谁做的」，不是凭据。
"""

import json
import os

# 数据根（相对实例目录）。规范位置是 data/Mindustry，data 本身是重构前
# 启动器把数据目录直接设在数据根上留下的位置，两个都扫。
DATA_DIRS = ("data/Mindustry", "data")

SETTINGS_NAME = "settings.bin"

# 精确匹配就剥掉的键。出处见模块开头：桌面真实 settings.bin 里的身份值。
IDENTITY_EXACT = ("uuid", "usid", "ip", "ip-bans", "banned-names")
# 前缀匹配就要剥的键：usid-<服务器>，后面那串（ip:port）无法穷举
IDENTITY_PREFIX = ("usid-",)

# 数据根顶层要整份丢掉的条目（文件或目录，目录按前缀算）。
# 只认顶层：mods 里同名文件是模组的，一个字节都不许动。
DROP_NAMES = ("server_list.json", "servers.json", "crashes", "last_log.txt",
              "log.txt", "settings_backups", "settings_backup.bin")
# 数据根**顶层**的日志（log.txt / last_log.txt 之类在 DROP_NAMES 里，其余按后缀）
DROP_SUFFIX = (".log",)

# 失败码：与 instanceExport.ERR_* 同一套命名，界面按 "err.<code>" 取文案
ERR_SETTINGS = "settingsUnreadable"


class SanitizeError(Exception):
    """脱敏过程里「不能继续」的情况。code 供界面取文案。"""

    def __init__(self, code, detail=""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def is_identity(key):
    """这个键算不算要剥掉的身份信息。★ 唯一判据 —— 剥键与自检都走它。"""
    if not key:
        return False
    if key in IDENTITY_EXACT:
        return True
    for prefix in IDENTITY_PREFIX:
        if key.startswith(prefix):
            return True
    return False


def strip_settings(raw):
    """settings.bin 字节 → ``(新字节, 被剥掉的键名列表)``。

    没有敏感键时原样返回 ``raw``（同一个对象，调用方可用 ``is`` 判断要不要重写）。
    解析不了抛 ValueError —— 由调用方决定是拒绝导出还是照原样打包。
    """
    # 延迟导入：编解码归 mdtManager（读设置与剥键共用同一套实现，不在这里抄
    # 第二份 —— 抄出来的那份迟早与真实现漂开）。延迟是为了避开模块级循环导入。
    from .mdtManager import _settings_decode_typed, _settings_encode_typed

    typed = _settings_decode_typed(raw)
    removed = [k for k in typed if is_identity(k)]
    if not removed:
        return raw, []
    for key in removed:
        del typed[key]
    return _settings_encode_typed(typed), removed


class Plan:
    """一次导出要用到的脱敏决定：丢哪些、改写哪些，以及给界面的计数。"""

    def __init__(self):
        self._drop_files = set()    # 精确相对路径（小写）
        self._drop_dirs = ()        # "data/Mindustry/crashes/" 这类前缀
        self._log_dirs = ()         # 这些目录下的 *.log 都丢
        self.rewrites = {}          # 相对路径 -> 新字节
        self._rewrites_low = {}     # 同一批，键是小写（查表见 rewrite_for）
        self.settings = []          # 参与剥键的 settings.bin 相对路径
        self.removed = []           # [(settings 相对路径, 键名)]

    # ---- 判定 ----

    def drops(self, rel):
        low = rel.lower()
        if low in self._drop_files:
            return True
        for prefix in self._drop_dirs:
            if low.startswith(prefix):
                return True
        if low.endswith(DROP_SUFFIX):
            # 只认数据根**顶层**的 *.log：mods/ 下面别人写的日志不是我们的
            for prefix in self._log_dirs:
                if low.startswith(prefix) and "/" not in low[len(prefix):]:
                    return True
        return False

    def set_rewrite(self, rel, data):
        """登记一个改写：正表按原样存，旁边再存一份小写索引。"""
        self.rewrites[rel] = data
        self._rewrites_low[rel.lower()] = data

    def rewrite_for(self, rel):
        """取某个相对路径的改写字節；没有就 None。

        查表按小写：计划里的路径是常量拼出来的（"data/Mindustry/settings.bin"），
        而打包时用的是 os.walk 给出的**磁盘真实大小写**。Windows 上两者可能不同
        （目录被别的程序建成 "Data"），精确匹配会查不到 —— 那样原始 settings.bin
        就会带着 usid-* 进包，而包上还标着 sanitized=true。
        """
        hit = self.rewrites.get(rel)
        if hit is None:
            hit = self._rewrites_low.get(rel.lower())
        return hit

    # ---- 计数 ----

    def removed_count(self):
        return len(self.removed)

    def server_id_count(self):
        """其中 usid-* 有几条 —— 这是最要紧的一类，界面上单独说。"""
        return sum(1 for _, key in self.removed if key.startswith(IDENTITY_PREFIX))

    def summary(self):
        return {"removed": self.removed_count(),
                "serverIds": self.server_id_count(),
                "settings": len(self.settings)}


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _plan_settings(plan, root, data_dir):
    """剥一份 settings.bin。解析失败抛 SanitizeError（纪律②）。"""
    rel = data_dir + "/" + SETTINGS_NAME
    path = os.path.join(root, *rel.split("/"))
    if not os.path.isfile(path):
        return
    try:
        raw = _read(path)
    except OSError as exc:
        raise SanitizeError(ERR_SETTINGS, "%s: %r" % (rel, exc))
    try:
        new, removed = strip_settings(raw)
    except ValueError as exc:
        raise SanitizeError(ERR_SETTINGS, "%s: %s" % (rel, exc))
    plan.settings.append(rel)
    plan.removed.extend((rel, key) for key in removed)
    if new is not raw:
        plan.set_rewrite(rel, new)


def _plan_bml(plan, root):
    """BML.json：去掉设置镜像与两个本机绝对路径。

    mdtData 是 settings.bin 的 JSON 副本 —— 只剥 bin 而留着它，身份键照样在包里。
    去掉整块而不是逐键剥：镜像与 bin 之间还有两个指纹（binHash/jsonHash），
    只改一半会让接收端判成「bin 与镜像都变过」。整块拿掉后 getSettings 会
    发现没有镜像，直接从 bin 重建，自愈且不留残影。

    javaPath / icon_path 同理：绝对路径里带着这台机器的用户名，而接收端
    本来就要把 javaPath 重置成「跟随全局」（见 mdtManager._import_instance）。
    """
    path = os.path.join(root, "BML.json")
    if not os.path.isfile(path):
        return
    try:
        raw = _read(path)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, TypeError):
        # 读不懂的 BML.json 本身就没有可用信息，交给导入端按默认值重建
        return
    if not isinstance(data, dict):
        return
    changed = False
    if "mdtData" in data:
        del data["mdtData"]
        changed = True
    if data.get("javaPath") != _follow_token():
        data["javaPath"] = _follow_token()
        changed = True
    if data.get("icon_path"):
        # 实例目录里的 icon.png 优先级更高，清空它不会丢图标
        data["icon_path"] = ""
        changed = True
    if not changed:
        return
    plan.set_rewrite("BML.json", json.dumps(
        data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _follow_token():
    """「跟随全局」的标识符。真值只在 mdtManager.FOLLOW 一处，这里延迟取。

    最后那行字面量是兜底：Java 路径重置只是「顺手多做一层」，万一这里取不到，
    也不该让整个导出失败。
    """
    try:
        from .mdtManager import mdtManager
        return mdtManager.FOLLOW
    except Exception:
        return "<:|follow|:>"


def build_plan(root, include_data=True):
    """扫一遍实例目录，返回 :class:`Plan`。解析失败抛 :class:`SanitizeError`。

    include_data=False 时实例数据整个不进包，也就不必去读 settings.bin ——
    一个已经损坏的设置文件不该拦住「我只想要这个客户端」的导出。
    """
    plan = Plan()
    if include_data:
        drop_files, drop_dirs, log_dirs = set(), [], []
        for data_dir in DATA_DIRS:
            base = os.path.join(root, *data_dir.split("/"))
            if not os.path.isdir(base):
                continue
            for name in DROP_NAMES:
                target = os.path.join(base, name)
                rel = data_dir + "/" + name
                if os.path.isdir(target):
                    drop_dirs.append(rel.lower() + "/")
                elif os.path.exists(target):
                    drop_files.add(rel.lower())
            log_dirs.append(data_dir.lower() + "/")
            _plan_settings(plan, root, data_dir)
        plan._drop_files = drop_files
        plan._drop_dirs = tuple(drop_dirs)
        plan._log_dirs = tuple(log_dirs)
    _plan_bml(plan, root)
    return plan
