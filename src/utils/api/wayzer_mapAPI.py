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

import re, requests

from PySide6.QtCore import QObject

from .githubAPI import _get_ca_bundle # 还有复用环节

# ---------------------------------------------------------------
# WayZer资源站(www.mindustry.top) 地图部分 API 封装
# ---------------------------------------------------------------
# 站点前端是 Nuxt SPA，后端 API 基址为 https://api.mindustry.top/
# （前端把 "/api/xxx" 路径转换为该基址，跨域需带 cookie）。
#
# 地图接口（无需登录，全部实测）:
#   GET /maps/list?begin={begin}&search={search}
#       -> JSON 数组，每批 15 条；begin 从 0 开始递增分页。
#          筛选 NOT 用 mode=/version=/sort= 参数（会被忽略），
#          而是写在 search 里的 @语法（空格分隔，多个可组合）:
#             @mode:Survive       模式（Survive/Pvp/Attack/Sandbox/Editor/UnKnown）
#             @version:5          版本内部号（见 VERSION_MAP）
#             @sort:download      排序（updateTime/createTime/download/rating/like）
#          排序默认按热度，无需传 @sort。
#   GET /maps/{id}.json
#       -> 地图详情（含完整地图 tags 数据）。
#   GET /maps/{id}.msav
#       -> 地图文件，Content-Type: application/zlib（zlib 压缩流，即标准 .msav）。
#          下载地址由 map_url() 拼出，由调用方（如 QDownloader）负责下载。
#   GET /users/info
#       -> 当前用户信息（未登录为 guest）。
# ---------------------------------------------------------------


class WayzerMapAPI(QObject):
    """www.mindustry.top 地图分享站 API 封装。

    返回约定与 GithubAPI 一致：
      成功 -> (True,  data)
      失败 -> (False, error)
    """

    BASE = "https://api.mindustry.top"

    # 版本筛选：@version 内部号 -> UI 文案（供外部 UI 层作索引）
    VERSION_MAP = {
        "3":  "v5(104-125)", "4": "v6(126-134)", "5": "v7(135)",
        "7":  "v7.5(136-146)", "8": "v8a(147-149)", "9": "v8b(150-151)",
        "10": "v8c(152-154)", "11": "v8(155+)",
    }

    # 模式筛选可用值
    MODES = ("Survive", "Pvp", "Attack", "Sandbox", "Editor", "UnKnown")

    # 排序筛选可用值（不传则按热度）
    SORTS = ("updateTime", "createTime", "download", "rating", "like")

    def __init__(self, parent=None):
        super().__init__(parent)
        # 复用 githubAPI 的合并 CA bundle（certifi + Windows 系统证书库），
        # 加速器/抓包工具把根证书装进系统库时不会误报 SSL 错误。
        self._session = requests.Session()
        self._session.trust_env = True
        self._session.verify = _get_ca_bundle()
        self._session.headers["User-Agent"] = "BookMDTLauncher/1.0"

    # ------------------------------------------------------------------
    def list_maps(self, begin=0, search="", mode="", version="", sort=""):
        """地图列表。

        Args:
            begin: 分页偏移，从 0 开始，每批 15 条（"加载更多"时递增）。
            search: 搜索关键词，可为空字符串；也可直接传完整 @语法
                （如 "@mode:Pvp @version:8"，此时忽略 mode/version/sort 参数）。
            mode: 模式筛选，取值见 MODES（Survive/Pvp/Attack/Sandbox/Editor/UnKnown）。
            version: 版本筛选，@version 内部号（3/4/5/7/8/9/10/11）
                或 VERSION_MAP 的值（UI 文案，如 v8a(147-149)）均可，自动映射。
            sort: 排序方式，取值见 SORTS；留空则按热度（默认）。

        Returns:
            (True, list) 每项字段：
                id     : int    地图编号
                name   : str    地图名（含 Mindustry 颜色标记，如 [red]、[#f7cba4]，
                                可混用多个，显示前用 strip_markup() 去掉）
                desc   : str    描述（含 \\n 换行、颜色标记及 [@banSkills]/[@pure] 等
                                禁项标签，规则：[@xx] 为禁用标签）
                latest : str    该系列最新版本 id（通常与 id 相同）
                preview: str    IPFS 预览图 URL（https://ipfs.mindustry.top/...）
                tags   : list   固定 4 项：[id, "模式§难度色", "v版本", "宽x高"]
                                如 ["25299", "Survive§warning", "v159", "300x300"]
                width  : int    地图宽度（格）
                height : int    地图高度（格）
                mode   : str    模式（Survive / Pvp / Attack / Sandbox / Unknown）
            (False, error)
        """
        if not (mode or version or sort):
            pass  # search 原样传
        else:
            # 组合 @语法：空格分隔，追加到 search 后面
            parts = [s for s in search.split() if s]
            if mode:
                parts.append(f"@mode:{mode}")
            if version:
                # 内部号优先；若传入 UI 文案则反向查回内部号
                v = version if version in self.VERSION_MAP else next(
                    (k for k, val in self.VERSION_MAP.items() if val == version),
                    version)
                parts.append(f"@version:{v}")
            if sort:
                parts.append(f"@sort:{sort}")
            search = " ".join(parts)
        try:
            params = {"begin": begin, "search": search}
            resp = self._session.get(
                self.BASE + "/maps/list", params=params, timeout=15)
            if resp.status_code == 200:
                return True, resp.json()
            return False, resp.status_code
        except requests.exceptions.SSLError as e:
            return False, "SSL certificate verify failed: " + str(e)
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.Timeout as e:
            return False, "Timeout: " + str(e)
        except Exception as e:
            return False, str(e)

    def get_map(self, map_id):
        """地图详情。

        Args:
            map_id: 地图编号（如 25299）。

        Returns:
            (True, dict) 字段：hash/name/tags/preview/user/mode/thread，
                tags 为完整 Mindustry 地图数据（波次、规则、生成单位等）；
            (False, error)
        """
        try:
            resp = self._session.get(
                f"{self.BASE}/maps/{map_id}.json", timeout=15)
            if resp.status_code == 200:
                return True, resp.json()
            return False, resp.status_code
        except requests.exceptions.SSLError as e:
            return False, "SSL certificate verify failed: " + str(e)
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.Timeout as e:
            return False, "Timeout: " + str(e)
        except Exception as e:
            return False, str(e)

    def map_url(self, map_id):
        """地图文件下载地址。

        Args:
            map_id: 地图编号。

        Returns:
            下载地址字符串；map_id 无效时返回 None。
        """
        if not map_id:
            return None
        return f"{self.BASE}/maps/{map_id}.msav"

    def get_user_info(self):
        """当前用户信息（无需登录）。

        Returns:
            (True, dict) 如 {"gid":"","name":"guest","role":"User",
                "isAdmin":false,"authed":false}；
            (False, error)
        """
        try:
            resp = self._session.get(self.BASE + "/users/info", timeout=15)
            if resp.status_code == 200:
                return True, resp.json()
            return False, resp.status_code
        except requests.exceptions.SSLError as e:
            return False, "SSL certificate verify failed: " + str(e)
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.Timeout as e:
            return False, "Timeout: " + str(e)
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    @staticmethod
    def strip_markup(text):
        """去掉 Mindustry Markup 颜色/效果代码。

        如 "[red]你好[] [white]世界" -> "你好 世界"。
        """
        if not text:
            return ""
        return re.sub(r"\[[^\]]*\]", "", text)


# 兼容旧名（如需可 import WayzerMapAPI）
WayzerAPI = WayzerMapAPI
