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

import requests, json, time, copy, os, base64, ssl, tempfile, atexit, threading

from PySide6.QtCore import Signal, QObject, QTimer

from . import githubAuth

# ---------------------------------------------------------------
# CA bundle：certifi + Windows 系统证书库（加速器/抓包工具根证书）
# ---------------------------------------------------------------
_bundle_path = None


def _cleanup_bundle(path):
    """进程退出时删除临时 CA bundle 文件。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _get_ca_bundle():
    """合并 certifi 默认 CA 与 Windows 系统证书库为 PEM 文件路径。

    requests 的 verify 只接受 True / CA 文件路径 / False；
    直接传 SSLContext 会在 requests 内部 os.path.exists(SSLContext)
    处崩溃（TypeError: path should be string, bytes, os.PathLike...）。
    加速器把根证书装进 Windows 系统证书库，certifi 不认识 →
    必须两者合并才不误报网络失败。
    返回文件路径；任何一步失败则回退 True（默认 certifi）。
    """
    global _bundle_path
    if _bundle_path and os.path.exists(_bundle_path):
        return _bundle_path
    parts = []
    try:
        import certifi
        with open(certifi.where(), "rb") as f:
            parts.append(f.read().decode("utf-8", "ignore"))
    except Exception:
        pass
    try:
        for der, _enc, _flags in ssl.enum_certificates("ROOT"):
            if not der:
                continue
            b64 = base64.b64encode(der).decode("ascii")
            lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
            parts.append(
                "-----BEGIN CERTIFICATE-----\n"
                + "\n".join(lines)
                + "\n-----END CERTIFICATE-----\n"
            )
    except Exception:
        pass
    text = "\n".join(parts).strip()
    if not text:
        return True
    try:
        fd, path = tempfile.mkstemp(suffix=".pem", prefix="bml_ca_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        _bundle_path = path
        try:
            atexit.register(_cleanup_bundle, path)
        except Exception:
            pass
        return path
    except Exception:
        return True


class GithubAPI(QObject):
    # rate 余量变了（沿用原名：托盘 tooltip 与设置面板都靠它重画余量）
    refreshed = Signal()
    timesreset = Signal(str)
    # 授权包变了：刷新拿到了新的 access / 到期时间，或者整块被清空。
    # 刷新发生在后台线程（网络请求），靠信号回主线程改控件。
    authChanged = Signal()
    # 凭据被判死（refresh 被 GitHub 拒、或刷新之后重试仍然是 401）。
    # 面板接这个信号切回未登录页 —— 8 小时过后用户不会还盯着面板看，
    # 「什么时候掉线」必须由这里主动通知，而不是等他下次打开面板才发现。
    authExpired = Signal()

    def __init__(self, auth=None):
        super().__init__()
        # 内存里只留密文：明文授权包只在真要发请求 / 刷新时才解出来，用完即弃
        self._encrypted_auth = None
        self._key = None
        self._checking = False
        # 落盘用：刷新出来的新授权包必须写回 settings。refresh_token 是单次
        # 使用的，只留在内存里的话，一次重启就等于把它弄丢了。
        self._settings = None
        # 刷新互斥：同一时刻只能有一次 refresh 在飞（refresh_token 单次使用）
        self._refresh_lock = threading.Lock()
        # 正在进行的授权流程的取消旗标（None = 没有流程在等）
        self._auth_cancel = None
        self._session = requests.Session()
        self._session.trust_env = True  # honor system proxy (VPN/accelerator)
        # verify 不能用 SSLContext（requests 内部会 os.path.exists 崩溃），
        # 改用合并 bundle：certifi + Windows 系统证书库（加速器根证书）。
        self._session.verify = _get_ca_bundle()
        self.setAuth(auth)
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

    # ---------- 授权包（内存） ----------
    # 存的是整块授权包（access + refresh + 两个到期时间 + scope），不再是一个
    # 裸 token：GitHub App 勾了「Expire user authorization tokens」之后，只留
    # access 等于把这份登录当成一次性的 —— 8 小时一到就没有凭据可续，只能让
    # 用户重登一遍。

    def _get_auth(self):
        """即用即解密，返回授权包字典后及时释放。"""
        raw = self._decrypt(self._encrypted_auth, self._key)
        if not raw:
            return None
        try:
            blob = json.loads(raw)
        except Exception:
            return None
        return blob if isinstance(blob, dict) else None

    @property
    def auth(self):
        """当前授权包（拆包后的字典；改它不会影响内存里那份密文）。"""
        return self._get_auth()

    def _access(self):
        """当前 access token（明文）；没有授权包时是 None。"""
        blob = self._get_auth() or {}
        return blob.get("access")

    def setAuth(self, blob):
        """加密存下整块授权包，内存中仅保留密文。blob 为空等于清空。"""
        if not blob or not blob.get("access"):
            self._encrypted_auth, self._key = None, None
            return
        self._encrypted_auth, self._key = self._encrypt(
            json.dumps(blob, ensure_ascii=False, sort_keys=True))

    def bindSettings(self, settings):
        """挂上 settings：刷新出来的新授权包要写回磁盘（见 _refresh_now）。"""
        self._settings = settings

    def getMaskedToken(self):
        """返回脱敏的 access token（面板上显示成 gho_1*******abcd 那种）。"""
        raw = self._access()
        if raw is None:
            return None
        if len(raw) > 15:
            return raw[:5] + "*" * (len(raw) - 10) + raw[-5:]
        if len(raw) > 10:
            return raw[:3] + "*" * (len(raw) - 6) + raw[-3:]
        return "*" * len(raw)

    def hasToken(self):
        """有没有可用的授权包（语义不变：有 access 就算有）。"""
        return self._encrypted_auth is not None

    def authExpiresAt(self):
        """access token 的到期时间戳（epoch 秒）；没登录 / 没有过期时间时 None。

        面板拿它显示本地时间，别的什么都不做 —— 「该不该刷新」是 ensure_fresh
        的事，UI 不该自己算「还有几分钟」再决定要不要发请求。
        """
        blob = self._get_auth() or {}
        return blob.get("expires_at")

    # ---------- GitHub App 登录 / 退出 ----------
    # 授权流程本身在 api/githubAuth.py（PKCE + 回环监听 + 换 token）；
    # 这里只做两件属于本类的事：跑完把授权包留住、成功后落盘。

    def authorize(self, settings=None, scope=None, timeout=None):
        """跑一次 GitHub App 授权，返回 (ok, 中文原因, blob)。

        这个调用会阻塞到用户把浏览器里的授权点完（最多 timeout 秒），
        所以只能从后台线程调（UI 那边走 QThTimer.task）。
        拿到授权包后：内存里加密存一份 → settings 里落盘一份 → 通知界面重画。
        """
        if settings is not None:
            # 一挂上就别摘：后面的刷新全靠它把新授权包写回磁盘
            self.bindSettings(settings)
        if self._auth_cancel is not None:
            return False, "上一次登录还在等待浏览器授权，请稍候", None
        cancel = threading.Event()
        self._auth_cancel = cancel
        try:
            kwargs = {"cancel": cancel, "session": self._session}
            if scope is not None:
                kwargs["scope"] = scope
            if timeout is not None:
                kwargs["timeout"] = timeout
            ok, message, blob = githubAuth.authorize(**kwargs)
        finally:
            self._auth_cancel = None
        if not ok or not blob or not blob.get("access"):
            return False, message or "登录失败", None
        self.setAuth(blob)
        if settings is not None:
            store_auth(settings, blob)
            gh = settings.get("github")
            if gh is not None:
                # useful 留空：等下一次 checkToken 拿真实结果来填，
                # 现在写 True 等于替 GitHub 提前打保票。
                gh["useful"] = None
        self.authChanged.emit()
        return True, "", blob

    def cancel_authorize(self):
        """取消正在等待的授权（用户关面板 / 自己按取消）。没有流程在等时是空操作。"""
        cancel = self._auth_cancel
        if cancel is not None:
            cancel.set()

    # ---------- 续期（refresh_token 轮换） ----------

    def ensure_fresh(self):
        """发请求之前的「这块 access 还够用吗」，需要时同步刷新一次。

        返回 (ok, 中文原因)。没授权包、或者还没到点，都返回 (True, "") ——
        这件事不该拦下 search / getRepo 那种不登录也能用（只是次数少）的接口。
        真失败了才返回 (False, 中文原因)，调用方按「凭据问题」处置。

        会打网络，所以只能在后台线程调（QThTimer.task / 工作线程）。
        """
        blob = self._get_auth()
        if not blob or not blob.get("access"):
            return True, ""
        if not githubAuth.needs_refresh(blob.get("expires_at"), time.time()):
            return True, ""
        return self._refresh_now(blob)

    def _refresh_now(self, blob=None):
        """拿 refresh_token 换一块新授权包，成功就写回内存 + 磁盘。

        返回 (ok, 中文原因)。

        refresh_token 是单次使用的：换成功之后新的那份**立刻**存下来，旧的
        当场作废。所以这里的顺序不能反 —— 先落盘再发信号（UI 那边可能马上
        重发请求），而且绝不能出现「只更新内存没更新磁盘」的中间态。
        """
        # 加锁是必需的，不是保守：两个后台任务（比如搜索 + 校验）同时发现
        # access 过期，会各自拿着**同一份** refresh 去换。先到的成功、后到的
        # 拿到 bad_refresh_token，而那条路会清空授权包 —— 于是刚换到的好凭据
        # 被一次本可以避免的并发撞掉了。锁内重新读一遍就能让第二次直接收手。
        with self._refresh_lock:
            return self._refresh_locked(blob)

    def _refresh_locked(self, blob):
        """_refresh_now 的本体（调用方已持锁）。"""
        current = self._get_auth()
        if not current or not current.get("access"):
            return True, ""
        if blob is not None and current.get("access") != blob.get("access"):
            # 手里那块已经被别的线程换掉了：什么都不用做，调用方用新的重试即可
            return True, ""
        blob = current
        refresh = blob.get("refresh") or ""
        if not refresh:
            # 没有 refresh：App 没勾「Expire user authorization tokens」，或者
            # 这是只存过裸 token 的老格式。access 一旦过期就真的无解。
            self._drop_auth()
            return False, "登录已过期，请重新登录"
        refresh_expires_at = blob.get("refresh_expires_at")
        if refresh_expires_at is not None and time.time() >= float(refresh_expires_at):
            # refresh 自己超过 6 个月了：本地就能判死，不必再拿它去问 GitHub
            self._drop_auth()
            return False, "登录已过期，请重新登录"
        client_id, client_secret, err = githubAuth.load_app_config()
        if err:
            # 凭据文件的问题不是「登录失效」：保留授权包，让用户去补配置
            return False, err
        ok, message, new_blob = githubAuth.refresh_access_token(
            client_id, refresh, client_secret=client_secret,
            session=self._session)
        if not ok:
            if githubAuth.NETWORK_ERROR_HINT in (message or ""):
                # 连不上 GitHub 不代表凭据失效 —— 保留授权包，下次再试。
                # 断网时把人登出，是最让人火大的那种「贴心」。
                return False, message
            self._drop_auth()
            return False, message or "登录已过期，请重新登录"
        if not new_blob.get("scope"):
            # 刷新响应偶尔不带 scope：沿用原来那份，别把授权范围记成空的
            new_blob["scope"] = blob.get("scope") or ""
        self.setAuth(new_blob)
        self._persist(new_blob)
        self.authChanged.emit()
        return True, ""

    def _persist(self, blob):
        """把授权包写进 settings（一次算好再赋值，见 store_auth）。"""
        if self._settings is None:
            return
        try:
            store_auth(self._settings, blob)
        except Exception:
            pass

    def _drop_auth(self):
        """授权包彻底作废：内存 + settings 一起清，并通知 UI 切回未登录。

        返回这次是否真的清掉了东西（重复调用就只是重发一次信号，幂等）。
        只在「凭据被 GitHub 明确判死」时调 —— 网络不通、配置缺失都不算，
        那两种清了反而逼用户在同一个问题里再踩一次。
        """
        gh = None
        if self._settings is not None:
            try:
                gh = self._settings.get("github")
            except Exception:
                gh = None
        had = self._encrypted_auth is not None or bool(gh and gh.get("auth_enc"))
        self.setAuth(None)
        self.rate = copy.deepcopy(self.default_rate)
        if gh is not None:
            try:
                clear_auth(self._settings)
                gh["useful"] = False
                gh["user"] = {"name": None, "headurl": None}
            except Exception:
                pass
        if had:
            self.authChanged.emit()
            self.authExpired.emit()
        return had

    # ---------- 带鉴权的请求 ----------

    _ACCEPT = "application/vnd.github.v3+json"

    def _send(self, url, params, timeout, accept):
        """发一次 GET，target 是当前 access token（没有就不带鉴权头）。"""
        token = self._access()
        headers = {"Accept": accept}
        if token:
            headers["Authorization"] = f"token {token}"
        return self._session.get(url, headers=headers, params=params,
                                 timeout=timeout)

    def _request(self, url, params=None, timeout=10, accept=None):
        """带鉴权发一次 GET，返回 (resp, None) 或 (None, 中文原因)。

        两件事都收在这一处，别的请求方法不用各写一遍：
        1. 发之前 ensure_fresh()：快到点的 access 先换掉，省得拿一个「出门时
           还没过期」的 token 去撞 401；
        2. 收到 401 再换一次、重试一遍：GitHub 会提前作废 access（用户改了
           授权范围、在网页上撤销授权），那种情况下 expires_at 还没到，只看
           第 1 条根本拦不住。只有「刷新之后还是 401」才算凭据真的死了。
        """
        ok, reason = self.ensure_fresh()
        if not ok:
            return None, reason
        accept = accept or self._ACCEPT
        token = self._access()
        resp = self._send(url, params, timeout, accept)
        if resp.status_code != 401:
            return resp, None
        ok, reason = True, ""
        if self._access() == token:
            # access 没被别人换过：自己刷一次，用新的重试
            ok, reason = self._refresh_now()
        if ok:
            resp = self._send(url, params, timeout, accept)
            if resp.status_code != 401:
                return resp, None
        # 走到这里说明 401 还是 401。三种可能，处置完全不同：
        if not self.hasToken():
            # 刷新被 GitHub 拒了 / 没有 refresh 可刷：_refresh_now 已经清空并
            # 发过 authExpired，这里只需要一句话
            return None, "登录已过期，请重新登录"
        if not ok:
            # 想续但没续成，而且不是凭据问题（没网 / 没配 App）：授权包留着，
            # 原因原样交回去。断网时把人登出是最让人火大的那种「贴心」。
            return None, reason or "登录失败"
        # 刷过、也重试过，还是 401：这时才算凭据真的没了
        self._drop_auth()
        return None, "登录已过期，请重新登录"

    def logout(self, settings=None):
        """退出登录：内存里的授权包与 settings 里的密文一起清掉。

        rate / user 也得清 —— 只清 token 的话，退出后面板还挂着上一个账号的
        余量和头像，那是最容易被当成「没退干净」的样子。
        """
        self.setAuth(None)
        self.rate = copy.deepcopy(self.default_rate)
        if settings is None:
            settings = self._settings
        if settings is None:
            return
        # 一次清干净：授权包（auth_enc/auth_key）连同老格式的 token_enc/token_key
        # 一起抹掉。老键留着没用 —— 读路径已经不看了，但半个旧 token 躺在
        # settings.json 里既没意义又容易让人以为「还没退干净」。
        clear_auth(settings)
        gh = settings.get("github")
        if gh is None:
            return
        gh["useful"] = None
        gh["user"] = {"name": None, "headurl": None}

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

    def checkToken(self):
        """使用 rate_limit 端点轻量检测当前授权包还能不能用。
        Returns: (ok, error_type, data)
          ok=True,  error_type=None:    凭据有效，data 为 response body
          ok=False, error_type="auth":  认证失败 (401/403)，授权包已清空
          ok=False, error_type="network": 网络/配置问题，授权包保留
          ok=False, error_type="http":   非预期 HTTP 状态码
          ok=False, error_type="busy":   已有检查在进行中
          ok=False, error_type="empty":  没有授权包
        """
        if self._checking:
            return False, "busy", "A check is already in progress"
        if not self.hasToken():
            return False, "empty", "No token set"
        self._checking = True
        try:
            url = "https://api.github.com/rate_limit"
            rest, reason = self._request(url)
            if rest is None:
                # 授权包还在 = 这次失败不是凭据问题（没网 / 没配 App），
                # 要按 network 报，别让调用方把一份好凭据清掉；
                # 授权包没了 = _request 已经把它判死，按 auth 归类。
                return False, ("auth" if not self.hasToken() else "network"), reason
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
                # 走到这里说明 _request 已经「刷新 + 重试」过一次了
                return False, "auth", "登录已过期，请重新登录"
            elif rest.status_code == 403:
                return False, "auth", "Token refused"
            else:
                return False, "http", rest.status_code
        except requests.exceptions.SSLError as e:
            # SSLError 是 ConnectionError 的子类，必须先于它捕获，
            # 否则会被当成"网络不通"误报（加速器 MITM 证书场景）。
            return False, "network", "SSL certificate verify failed: " + str(e)
        except requests.ConnectionError as e:
            return False, "network", str(e)
        except requests.Timeout as e:
            return False, "network", "Timeout: " + str(e)
        except Exception as e:
            return False, "unknown", str(e)
        finally:
            self._checking = False

    def getUser(self):
        """获取当前已认证用户信息。"""
        if not self.hasToken():
            return False, None
        try:
            resp, reason = self._request("https://api.github.com/user")
            if resp is None:
                return False, reason
            if resp.status_code == 200:
                self._refresh(resp)
                return True, {"body": resp.json(), "head": resp.headers}
            elif resp.status_code == 401:
                return False, "登录已过期，请重新登录"
            elif resp.status_code == 403:
                return False, "Token refused"
            else:
                return False, resp.status_code
        except requests.ConnectionError:
            return False, "ConnectionError"
        except Exception as e:
            return False, e

    def search(self, query, page=1):
        url = "https://api.github.com/search/repositories"
        try:
            params = {
                "q": query,
                "page": page,
                "per_page": 50,
                "sort": "stars",
                "order": "desc"
            }
            rest, _reason = self._request(url, params=params, timeout=30)
            if rest is None:
                return False, None
            self._refresh(rest)
            return True, rest.json()
        except Exception:
            return False, None

    def getRepo(self, repo):
        url = f"https://api.github.com/repos/{repo}"
        try:
            rest, _reason = self._request(url, timeout=30)
            if rest is None:
                return False, None
            self._refresh(rest)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None

    def getRelease(self, repo, page=1,per_page=50):
        url = f"https://api.github.com/repos/{repo}/releases"
        try:
            params = {
                "page": page,
                "per_page": per_page
            }
            rest, _reason = self._request(url, params=params, timeout=30)
            if rest is None:
                return False, None
            self._refresh(rest)
            if rest.status_code == 200:
                return True, rest.json()
            else:
                return False, rest.status_code
        except Exception:
            return False, None
    

# ─────────────────── 授权包存盘 / 读回 ───────────────────
# 授权包（access + refresh + 到期时间 + scope）落盘前要过两层：先用随机密钥
# 加密（GithubAPI._encrypt，见上），得到的密文与密钥再抹一层固定 XOR，最后
# base64 进 settings。两层都是混淆而不是加密 —— 防的是「顺手 copy 一份
# settings.json 就把凭据带走」，不防有心的本机攻击者（这一点面板上的提示条
# 也照实写了）。真正让这份凭据不致命的是 scope 只有 read:user。
# 原先这一对方法长在 Main 上（_encrypt_settings_token / _obf_store…），
# 于是「谁要用就得攥着宿主」—— 用到它的是 GitHub 设置页与启动流程，
# 都不是宿主该管的事，收到这里跟加密本身待在一起。

_OBF_BYTE = 0x5A


def _obf(s):
    """固定 XOR → base64：settings 存储前混淆。"""
    return base64.b64encode(bytes(b ^ _OBF_BYTE for b in s.encode())).decode()


def _deobf(s):
    """逆向：base64 解码 → XOR 还原。"""
    return bytes(byte ^ _OBF_BYTE for byte in base64.b64decode(s)).decode()


def store_auth(settings, blob):
    """把整块授权包加密后写进 settings["github"]（auth_enc / auth_key）。

    为什么整块而不是只存 access：refresh_token 和两个过期时间跟 access 是
    一套语义 —— 少了 refresh，8 小时后就只剩「让用户重登」这一条路；
    分开存又迟早会出现「新的 access 配旧的 refresh」，而 refresh 是单次使用
    的，配错一次就是永久失效。一块进、一块出，没有中间态。
    为什么先算再赋值：settings 的写值是逐键通知的（宿主靠通知防抖存盘），
    两个值都算好再一次性赋上去，订阅者才不会拿到「半新半旧」的一对。
    """
    if not blob or not blob.get("access"):
        clear_auth(settings)
        return
    plain = json.dumps(blob, ensure_ascii=False, sort_keys=True)
    enc, key = GithubAPI._encrypt(plain)
    obf_enc, obf_key = _obf(enc), _obf(key)
    gh = settings.get("github")
    if gh is None:
        return
    gh["auth_enc"] = obf_enc
    gh["auth_key"] = obf_key


def read_auth(settings):
    """从 settings["github"] 读回授权包；没存过、存坏了、结构不对都返回 None。

    只认 auth_enc/auth_key。老的 token_enc/token_key 是「一个裸 token」的
    格式，读它等于把一份没有 refresh 的凭据当成完整授权包 —— 那正是「8 小时
    后悄悄失效」的来源，所以干脆不读（logout 时才顺手抹掉）。
    """
    gh = settings.get("github") or {}
    if not gh.get("auth_enc") or not gh.get("auth_key"):
        return None
    try:
        raw = GithubAPI._decrypt(_deobf(gh["auth_enc"]), _deobf(gh["auth_key"]))
        blob = json.loads(raw)
    except Exception:
        return None
    if not isinstance(blob, dict) or not blob.get("access"):
        return None
    return blob


def clear_auth(settings):
    """清空授权包，并把老格式的 token_enc/token_key 一起抹掉。

    退出登录、以及凭据被 GitHub 判死时都走这里 —— 两处的「干净」定义应该
    一样，分开写迟早一边漏一个字段。
    """
    gh = settings.get("github")
    if gh is None:
        return
    gh["auth_enc"] = None
    gh["auth_key"] = None
    gh["token_enc"] = None
    gh["token_key"] = None
