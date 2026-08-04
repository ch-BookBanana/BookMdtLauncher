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

import requests, json, time, copy, os, base64

from PyQt5.QtCore import pyqtSignal, QObject, QTimer

class GithubAPI(QObject):
    refreshed = pyqtSignal()
    timesreset = pyqtSignal(str)

    def __init__(self, token=None):
        super().__init__()
        self._encrypted_token = None
        self._key = None
        self._checking = False
        self._session = requests.Session()
        self._session.trust_env = True  # honor system proxy (VPN/accelerator)
        self.setToken(token)
        self.default_rate = {
            "core":   {"remaining": None, "reset": [], "reset_ts": 0},
            "search": {"remaining": None, "reset": [], "reset_ts": 0},
        }
        self.rate = copy.deepcopy(self.default_rate)
        self._timers = {
            "core":   self._make_timer("core"),
            "search": self._make_timer("search"),
        }
        # 确保 _schedule_reset 通过信号回主线程执行（QTimer 不能跨线程操作）
        self.refreshed.connect(self._schedule_reset)

    def _make_timer(self, name):
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(lambda n=name: self._on_times_reset(n))
        return t

    def _refresh(self, resp):
        resource = resp.headers.get("X-RateLimit-Resource", "core")
        # 仅处理 v3 REST API（core/search），忽略 graphql 等
        if resource not in ("core", "search"):
            return
        entry = self.rate.get(resource)
        if entry is None:
            return
        entry["remaining"] = int(resp.headers.get("X-RateLimit-Remaining", entry["remaining"]))
        reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
        if reset_ts:
            entry["reset_ts"] = reset_ts
            lt = time.localtime(reset_ts)
            entry["reset"] = [lt.tm_year, lt.tm_mon, lt.tm_mday,
                              lt.tm_hour, lt.tm_min, lt.tm_sec]
        self.refreshed.emit()

    def _schedule_reset(self):
        """为每个计数器安排独立的 reset 定时器"""
        now = time.time()
        for name, entry in self.rate.items():
            ts = entry.get("reset_ts", 0)
            if ts > now:
                delay_ms = int((ts - now) * 1000) + 500
                self._timers[name].start(delay_ms)

    def _on_times_reset(self, name):
        """某个计数器 reset 时间到，发出信号（携带名称）"""
        self.rate[name] = copy.deepcopy(self.default_rate[name])
        self.timesreset.emit(name)

    @staticmethod
    def _encrypt(plaintext):
        """使用随机密钥加密明文。返回 (encrypted_b64, key_b64)。"""
        if plaintext is None:
            return None, None
        key = os.urandom(32)
        data = plaintext.encode('utf-8')
        encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])
        return base64.b64encode(encrypted).decode(), base64.b64encode(key).decode()

    @staticmethod
    def _decrypt(encrypted_b64, key_b64):
        """用密钥解密密文，返回明文。"""
        if encrypted_b64 is None or key_b64 is None:
            return None
        encrypted = base64.b64decode(encrypted_b64)
        key = base64.b64decode(key_b64)
        plain = bytes([b ^ key[i % len(key)] for i, b in enumerate(encrypted)])
        return plain.decode('utf-8')

    def _get_token(self):
        """即用即解密，返回明文字符串后及时释放。"""
        return self._decrypt(self._encrypted_token, self._key)

    def getMaskedToken(self):
        """返回脱敏 token。"""
        raw = self._get_token()
        if raw is None:
            return None
        if len(raw) > 15:
            return raw[:5] + "*" * (len(raw) - 10) + raw[-5:]
        if len(raw) > 10:
            return raw[:3] + "*" * (len(raw) - 6) + raw[-3:]
        return "*" * len(raw)

    def setToken(self, token_):
        """加密存储 token，内存中仅保留密文。"""
        self._encrypted_token, self._key = self._encrypt(token_)

    def hasToken(self):
        """是否已设置 token。"""
        return self._encrypted_token is not None

    def checkConnection(self):
        """测试到 GitHub 的网络延迟（不消耗 API 次数）。"""
        try:
            start = time.perf_counter()
            resp = self._session.get(
                "https://github.com/",
                timeout=5
            )
            latency = int((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                return latency
            else:
                return abs(resp.status_code) * -1

        except requests.exceptions.Timeout:
            return -2
        except requests.exceptions.ConnectionError:
            return -3
        except requests.exceptions.SSLError:
            return -4
        except:
            return -99

    def checkToken(self, token_=None):
        """使用 rate_limit 端点轻量检测 token 有效性。
        Returns: (ok, error_type, data)
          ok=True,  error_type=None:    token 有效，data 为 response body
          ok=False, error_type="auth":  认证失败 (401/403)，应清除 token
          ok=False, error_type="network": 网络不通，保留 token 等待重试
          ok=False, error_type="http":   非预期 HTTP 状态码
          ok=False, error_type="busy":   已有检查在进行中
          ok=False, error_type="empty":  未设置 token
        """
        if self._checking:
            return False, "busy", "A check is already in progress"
        if token_ is None:
            if self._encrypted_token is None:
                return False, "empty", "No token set"
            token_ = self._get_token()
        self._checking = True
        try:
            url = "https://api.github.com/rate_limit"
            headers = {
                "Authorization": f"token {token_}",
                "Accept": "application/vnd.github.v3+json",
            }
            rest = self._session.get(url, headers=headers, timeout=10)
            if rest.status_code == 200:
                self._refresh(rest)
                # /rate_limit body 同时含 core + search，补全 header 拿不到的
                body = rest.json()
                resources = body.get("resources", {})
                for name in ("core", "search"):
                    info = resources.get(name, {})
                    if info:
                        entry = self.rate.get(name)
                        if entry is not None:
                            entry["remaining"] = info.get("remaining", entry["remaining"])
                            reset_ts = info.get("reset", 0)
                            if reset_ts:
                                entry["reset_ts"] = reset_ts
                                lt = time.localtime(reset_ts)
                                entry["reset"] = [lt.tm_year, lt.tm_mon, lt.tm_mday,
                                                  lt.tm_hour, lt.tm_min, lt.tm_sec]
                self.refreshed.emit()
                return True, None, body
            elif rest.status_code == 401:
                return False, "auth", "Invalid token"
            elif rest.status_code == 403:
                return False, "auth", "Token refused"
            else:
                return False, "http", rest.status_code
        except requests.ConnectionError:
            return False, "network", "ConnectionError"
        except requests.Timeout:
            return False, "network", "Timeout"
        except Exception as e:
            return False, "unknown", str(e)
        finally:
            self._checking = False

    def getUser(self):
        """获取当前已认证用户信息。"""
        if self._encrypted_token is None:
            return False, None
        token_ = self._get_token()
        url = "https://api.github.com/user"
        headers = {
            "Authorization": f"token {token_}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            rest = self._session.get(url, headers=headers, timeout=10)
            if rest.status_code == 200:
                self._refresh(rest)
                return True, {"body": rest.json(), "head": rest.headers}
            elif rest.status_code == 401:
                return False, "Invalid token"
            elif rest.status_code == 403:
                return False, "Token refused"
            else:
                return False, rest.status_code
        except requests.ConnectionError:
            return False, "ConnectionError"
        except Exception as e:
            return False, e

    def search(self, query, page=1):
        _tkn = self._get_token()
        headers = {"Accept": "application/vnd.github.v3+json"}
        if _tkn:
            headers["Authorization"] = f"token {_tkn}"
        _tkn = None
        url = "https://api.github.com/search/repositories"
        try:
            params = {
                "q": query,
                "page": page,
                "per_page": 50,
                "sort": "stars",
                "order": "desc"
            }

            rest = self._session.get(url, headers=headers, params=params, timeout=30)
            self._refresh(rest)
            return True, rest.json()
        except Exception:
            return False, None

    def getRepo(self, repo):
        _tkn = self._get_token()
        url = f"https://api.github.com/repos/{repo}"
        headers = {}
        if _tkn:
            headers["Authorization"] = f"token {_tkn}"
        _tkn = None
        try:
            rest = self._session.get(url, headers=headers, timeout=30)
            self._refresh(rest)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None

    def getRelease(self, repo, page=1,per_page=50):
        _tkn = self._get_token()
        url = f"https://api.github.com/repos/{repo}/releases"
        headers = {}
        if _tkn:
            headers["Authorization"] = f"token {_tkn}"
        _tkn = None
        try:
            params = {
                "page": page,
                "per_page": per_page
            }

            rest = self._session.get(url, headers=headers, params=params, timeout=30)
            self._refresh(rest)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None
    