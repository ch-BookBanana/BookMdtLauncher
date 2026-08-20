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

import requests

from PySide6.QtCore import QObject

from .githubAPI import _get_ca_bundle

# ---------------------------------------------------------------
# STNG蓝图工坊(www.stng.pw) API 封装
# ---------------------------------------------------------------
# 后端为 REST + JWT(Bearer)认证，查询/下载接口无需登录，全部实测。
# 注意：这是蓝图站，文件格式为 .msch(Mindustry 蓝图)，不是地图。
#
# 接口清单(无需登录):
#   GET /api/blueprints?orderBy={download_count|upload_time|id}&orderDir={DESC}&page={n}&limit={n}
#       -> {"data": [...], "total": N, "page": n, "limit": n}
#          orderBy 映射: 热度 -> download_count DESC, 最新 -> upload_time DESC, ID -> id
#   GET /api/blueprints/search?q={kw}&orderBy=&orderDir=&page=&limit=
#       -> 同上结构，关键词匹配名称/作者/描述
#   GET /api/blueprints/{id}
#       -> 详情 dict（字段见 get_blueprint docstring）
#   GET /api/blueprints/user/{uploader_qq}?limit={n}
#       -> {"data": [...], "total": n} 同作者的其他蓝图
#   GET /api/blueprints/{id}/download
#       -> .msch 二进制（msch 魔数 + zlib 压缩），
#          Content-Disposition: attachment; filename="xxx.msch"
#   GET /api/blueprints/{id}/content
#       -> {"success": true, "base64": "..."} 可直接粘贴进游戏的蓝图文本
#   GET /api/stats
#       -> {"users": 91, "blueprints": 2517, "likes": 6, "downloads": "61"}
#
# 需登录(启动器一般不调用): POST /api/blueprints/{id}/like（点赞）、
#   POST /api/blueprints/upload / upload-text（上传）、GET /api/auth/me（登录态检查）
# ---------------------------------------------------------------


class StngAPI(QObject):
    """www.stng.pw 蓝图工坊 API 封装。

    返回约定与 GithubAPI/WayzerMapAPI 一致：
      成功 -> (True,  data)
      失败 -> (False, error)
    """

    BASE = "https://www.stng.pw/api"

    # 排序可用值（orderBy 参数原始值）
    SORTS = ("download_count", "upload_time", "id")

    # UI 文案 -> orderBy 映射（热度/最新/ID）
    SORT_MAP = {
        "热度": "download_count", "download_count": "download_count",
        "最新": "upload_time", "upload_time": "upload_time",
        "ID": "id", "id": "id",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        # 复用 githubAPI 的合并 CA bundle（certifi + Windows 系统证书库），
        # 加速器/抓包工具把根证书装进系统库时不会误报 SSL 错误。
        self._session = requests.Session()
        self._session.trust_env = True
        self._session.verify = _get_ca_bundle()
        self._session.headers["User-Agent"] = "BookMDTLauncher/1.0"

    # ------------------------------------------------------------------
    @staticmethod
    def _sort_value(sort):
        """把 UI 文案 / 原始 orderBy 值统一映射为参数值，无法识别返回空串。"""
        if not sort:
            return ""
        return StngAPI.SORT_MAP.get(sort, "")

    def list_blueprints(self, page=1, limit=12, sort=""):
        """蓝图列表（分页）。

        Args:
            page: 页码，从 1 开始。
            limit: 每页条数，默认 12。
            sort: 排序，可传 UI 文案（"热度"/"最新"/"ID"）或原始 orderBy
                值（download_count/upload_time/id）；留空按热度。

        Returns:
            (True, dict) {"data": [...], "total": N, "page": n, "limit": n}
                列表项字段同 get_blueprint 详情字段；
            (False, error)
        """
        order_by = self._sort_value(sort)
        try:
            params = {"orderBy": order_by, "orderDir": "DESC",
                      "page": page, "limit": limit}
            resp = self._session.get(
                self.BASE + "/blueprints", params=params, timeout=15)
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

    def search_blueprints(self, q, page=1, limit=12, sort=""):
        """按关键词搜索蓝图（匹配名称/作者/描述）。

        Args:
            q: 关键词。
            page: 页码，从 1 开始。
            limit: 每页条数，默认 12。
            sort: 排序，同 list_blueprints。

        Returns:
            (True, dict) 同 list_blueprints；
            (False, error)
        """
        order_by = self._sort_value(sort)
        try:
            params = {"q": q, "orderBy": order_by, "orderDir": "DESC",
                      "page": page, "limit": limit}
            resp = self._session.get(
                self.BASE + "/blueprints/search", params=params, timeout=15)
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

    def get_blueprint(self, bp_id):
        """蓝图详情。

        Args:
            bp_id: 蓝图编号（如 3）。

        Returns:
            (True, dict) 字段：
                id             : int     蓝图编号
                name           : str     名称
                description    : str     描述
                hash           : str     内容哈希
                uploader_qq    : str     作者 QQ
                uploader_name  : str     作者昵称
                group_id       : str     所属群
                group_name     : str     群名
                source         : str     来源（text/文件等）
                upload_time    : str     ISO8601 上传时间
                download_count : int     下载量
                like_count     : int     点赞数
                width          : int     宽度（格）
                height         : int     高度（格）
                power_balance  : int     电力平衡
                cost           : dict    资源消耗 {lead: 354, copper: 29, ...}
                image_url      : str     预览图 URL（相对站点根，如 /images/xxx.png）
                is_liked       : bool    当前用户是否已点赞
            (False, error)
        """
        try:
            resp = self._session.get(
                f"{self.BASE}/blueprints/{bp_id}", timeout=15)
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

    def get_user_blueprints(self, uploader_qq, limit=10):
        """同作者的其他蓝图。

        Args:
            uploader_qq: 作者 QQ（从蓝图详情的 uploader_qq 字段取）。
            limit: 返回条数，默认 10。

        Returns:
            (True, dict) {"data": [...], "total": n}；
            (False, error)
        """
        try:
            params = {"limit": limit}
            resp = self._session.get(
                f"{self.BASE}/blueprints/user/{uploader_qq}",
                params=params, timeout=15)
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

    def blueprint_url(self, bp_id):
        """蓝图 .msch 文件下载地址。

        Args:
            bp_id: 蓝图编号。

        Returns:
            下载地址字符串；bp_id 无效时返回 None。
        """
        if not bp_id:
            return None
        return f"{self.BASE}/blueprints/{bp_id}/download"

    def get_blueprint_content(self, bp_id):
        """获取蓝图 base64 文本（可直接粘贴进游戏）。

        Args:
            bp_id: 蓝图编号。

        Returns:
            (True, str) base64 文本；
            (False, error)
        """
        try:
            resp = self._session.get(
                f"{self.BASE}/blueprints/{bp_id}/content", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("base64"):
                    return True, data["base64"]
                return False, data.get("message", "base64 empty")
            return False, resp.status_code
        except requests.exceptions.SSLError as e:
            return False, "SSL certificate verify failed: " + str(e)
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.Timeout as e:
            return False, "Timeout: " + str(e)
        except Exception as e:
            return False, str(e)

    def get_stats(self):
        """站点统计（无需登录）。

        Returns:
            (True, dict) {"users": 91, "blueprints": 2517,
                "likes": 6, "downloads": "61"}；
            (False, error)
        """
        try:
            resp = self._session.get(self.BASE + "/stats", timeout=15)
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


# 兼容旧名
StngBlueprintAPI = StngAPI
