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
"""

import socket
import struct
import time

# Mindustry 服务器信息通过 UDP discovery 协议获取（不是 TCP！）
# 依据官方源码：core/src/mindustry/net/ArcNetProvider.pingHostImpl
#   socket.send(new DatagramPacket(new byte[]{-2, 1}, 2, ...))
# 服务器回包格式见 core/src/mindustry/net/NetworkIO.writeServerData()
# （arc ByteBuffer，大端序）：
#   [1B长度][UTF-8] 服务器名(max100)
#   [1B长度][UTF-8] 地图名(max64)
#   i32 人数  i32 波次  i32 版本build
#   [1B长度][UTF-8] 版本类型("official"等)
#   b 模式序号  i32 最大人数
#   [1B长度][UTF-8] 描述  [1B长度][UTF-8] modeName
#   i16 端口(0 时用默认 6567)


class mdtServer:
    """Mindustry 服务器信息查询模块（UDP discovery）。"""

    DEFAULT_PORT = 6567
    # Gamemode.all 序号（core/src/mindustry/game/Gamemode.java）
    MODES = {0: "survival", 1: "sandbox", 2: "attack", 3: "pvp", 4: "editor"}

    @staticmethod
    def _read_string(data, off):
        """解析 [1字节长度][UTF-8] 字符串，返回 (字符串, 新偏移)。"""
        n = data[off]
        s = data[off + 1: off + 1 + n].decode("utf-8", "replace")
        return s, off + 1 + n

    @classmethod
    def _parse(cls, data):
        """解析 UDP 响应字节为字典。"""
        off = 0
        name, off = cls._read_string(data, off)
        mapname, off = cls._read_string(data, off)
        players = struct.unpack_from(">i", data, off)[0]
        off += 4
        wave = struct.unpack_from(">i", data, off)[0]
        off += 4
        version = struct.unpack_from(">i", data, off)[0]
        off += 4
        vtype, off = cls._read_string(data, off)
        mode_num = data[off]
        off += 1
        limit = struct.unpack_from(">i", data, off)[0]
        off += 4
        desc, off = cls._read_string(data, off)
        mode_name, off = cls._read_string(data, off)
        sport = struct.unpack_from(">h", data, off)[0]
        off += 2
        return {
            "name": name,
            "map": mapname,
            "players": players,
            "playerLimit": limit,
            "wave": wave,
            "version": version,
            "versionType": vtype,
            "mode": cls.MODES.get(mode_num, "unknown(%d)" % mode_num),
            "modeNum": mode_num,
            "description": desc,
            "modeName": mode_name,
            "port": sport if sport else cls.DEFAULT_PORT,
        }

    @classmethod
    def query(cls, host, port=DEFAULT_PORT, timeout=3.0):
        """查询单个服务器信息。

        返回信息字典（含 ping 毫秒）；连接失败/超时/解析失败返回 None。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        t0 = time.time()
        try:
            sock.sendto(b"\xfe\x01", (host, port))
            data, _ = sock.recvfrom(4096)
            ping = int((time.time() - t0) * 1000)
            info = cls._parse(data)
            info["ping"] = ping
            info["host"] = host
            return info
        except (socket.timeout, OSError, struct.error, IndexError):
            return None
        finally:
            sock.close()

    @classmethod
    def query_many(cls, servers, timeout=3.0):
        """批量查询服务器列表。

        servers: 可迭代对象，元素为 (host, port) 或 host 字符串。
        返回 {host: 信息dict 或 None}，None 表示不可达/失败。
        """
        results = {}
        for item in servers:
            if isinstance(item, (tuple, list)):
                host, port = item[0], item[1]
            else:
                host, port = item, cls.DEFAULT_PORT
            results[host] = cls.query(host, port, timeout)
        return results
