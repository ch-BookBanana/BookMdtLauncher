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

GitHub App 授权：OAuth 授权码 + PKCE(S256) + 本地回环（loopback）。

为什么不再要一个 PAT
--------------------
PAT 是长期凭据，得用户自己去网页上建、复制、粘贴：粘错了界面上看不出，权限
给大了也没人知道，过期了还得重来一遍。GitHub App 的授权码流程把这些事全交给
浏览器 —— 用户只点一次「登录 GitHub」，授权码由浏览器带回本机回环端口，启动器
再拿 code + PKCE verifier 去换授权包（access_token + refresh_token）。用户
全程不接触任何凭据；access 每 8 小时由 refresh 自动续，用户只在真的被撤销
授权时才需要再点一次。

用户需要在 GitHub App 后台做两件事（面板里的提示文案也写了这两条）：
  1. 把 App 的 **Authorization callback URL** 设为 `http://127.0.0.1/callback`
     （端口任意 —— 本机回环按 RFC 8252 §7.3 允许动态端口，端口由内核分配）；
  2. 把 App 的 client_id 与 client_secret 填进 `BML/githubApp.json`：
        {"client_id": "Iv1.xxxxxxxx", "client_secret": "…"}
     （secret 是 token 端点硬性要求的；桌面端留不住它，别当机密）

还有一件事不在面板提示里，但必须做：App 后台要勾上
**Expire user authorization tokens**（中文界面是「让用户授权令牌过期」），
否则 GitHub **不会下发 refresh_token** —— access token 照样 8 小时过期，
可手里没有续期的凭据，到点只能让用户重新登录一遍。勾上之后换 token 的
响应里才会带 refresh_token（单次使用：刷一次就轮换出一个新的，旧的当场
作废，所以收到就必须存下来）。

PKCE 不是可选项：回环端口对本机所有进程都是敞开的，光靠 state 拦不住抢授权码
的人。verifier 只在这个进程的内存里出现，唯一一次离开内存就是换 token 的那个
HTTPS 请求体 —— 它不经过浏览器，也就不可能被拦在回调地址上。

这里的函数**不抛异常**：网络不通、用户取消、超时、配置缺失一律收敛成
`(ok, 中文原因, blob)`，UI 只需要看这个三元组。blob 是「授权包」而不是一个
裸 token —— 见下面「授权包与过期判断」那一节：access 只有 8 小时，光有它
等于把登录当成一次性的。
"""

import base64
import hashlib
import html
import json
import logging
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtCore import QCoreApplication, QObject, Qt, QUrl, Signal, Slot

from .. import path_utils
from . import secretbox

__all__ = [
    "AUTHORIZE_ENDPOINT", "TOKEN_ENDPOINT", "CALLBACK_PATH", "APP_CONFIG_REL",
    "NETWORK_ERROR_HINT",
    "make_code_verifier", "code_challenge", "make_state", "build_authorize_url",
    "load_app_config", "LoopbackServer", "exchange_code", "refresh_access_token",
    "expires_at_from", "needs_refresh", "authorize", "open_in_browser",
]

AUTHORIZE_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
CALLBACK_PATH = "/callback"

# 本启动器只读：抓公开仓库的发布列表、读自己的头像和用户名。scope 给到
# read:user 就到顶了 —— 授权页上写得越窄，用户越敢点那个按钮。
DEFAULT_SCOPE = "read:user"

# 用户可能先去 GitHub 后台建 App 再回来点登录，所以等得久一点；
# 超过这个时间基本就是人走开了，留着监听没有意义。
DEFAULT_TIMEOUT = 180

# GitHub App 的凭据：BML/ 是用户本地数据目录（已在 .gitignore 里），
# 走 getPath 而不是 __file__ 自己拼 —— 打包后它是 exe 同目录，开发时是仓库根，
# 冒烟/自测里还会被重定向到临时目录。
APP_CONFIG_REL = "BML/githubApp.json"

# 启动器自己那个 GitHub App 的凭据。
# 填好这两行，用户点「登录 GitHub」就能直接用，不用碰任何配置文件。
# GitHub App 后台的 Authorization callback URL 设成 http://127.0.0.1/callback
# （回环地址允许任意端口，端口由内核分配）。
BUILTIN_CLIENT_ID = "Iv23lihqub0l2I1s17LI"

# client_secret：GitHub 的 token 端点硬性要求（实测不带会被判
# incorrect_client_credentials，PKCE 替代不了）。
# 别把它当机密 —— 桌面端留不住 secret，谁都能从二进制里抠出来。
# 真正的安全边界是 PKCE（钉住授权发起方）+ 可撤销 + refresh 轮换 + 加密落盘。
# 现在这个值确实随仓库公开：它只能用来和你这个 App 交换授权码（换不出别人
# 的 token，也读不到任何仓库），代价是 GitHub 的 secret scanning 若把它
# 判成泄露会自动撤销 —— 撤销后所有人登录都会失败，届时换一个新 secret 即可。
# 这个常量为空：真正随二进制分发的那个值改走下面的密封常量（_SEALED_CLIENT_SECRET），
# 目的只是别让明文出现在源码里；要换 secret 就去跑 scripts/seal_secret.py。
BUILTIN_CLIENT_SECRET = ""

# 本机凭据放 src/env.py（已在 .gitignore 里）：源码公开、secret 不公开。
# 导入失败（别人 clone 后没有这个文件）就当没有 secret —— 他自己建 App 填自己的。
try:
    from ...env import CLIENT_SECRET as _LOCAL_CLIENT_SECRET
except Exception:            # 文件不存在 / 字段没写，都走「没有本机凭据」这条路
    _LOCAL_CLIENT_SECRET = ""


# ─────────────── 内置 secret 的加密封装（见 secretbox.py）───────────────
# 这里放的不是明文，是 secretbox 封出来的 base64 密文；解开它要一把由
# **三段分开存放**的素材经 PBKDF2 派生出来的密钥：
#   第一段在本文件（_SB_A），第二段在 secretbox.py（_SB_B），
#   第三段写死在 _sb_key_material() 函数体里。
# 分开只是为了不让人扫一眼源码就把「密钥怎么拼的」串起来 —— 单独看到
# 任何一段都只是一串普通 base64，`strings` 抓出来也不起眼。
# 换 secret 就重跑 scripts/seal_secret.py，四样东西必须一起换。
_SEALED_CLIENT_SECRET = "sbBKvu8jlhK3GkbbLqPA0NiXyW8+SSLnj1EN3ifgCkK0oxreB5O6NtAMiW+qhgvdkxiwo7IekaWvePTatftZYGEMjRL79DQNRJvoG7NVaLOcKHxY"

# 第一段素材（base64）。长度跟另外两段一样，免得「哪段短哪段假」
_SB_A = "deMfAH3RGh8bXI0fKg+JN4MJ"

# 派生结果缓存：PBKDF2 十二万轮，每次启动只该算一次，别在登录路径上反复烧
_SB_MATERIAL_CACHE = None


def _sb_key_material():
    """把散在三处的素材拼成 32 字节密钥；拼不出来返回 b""（不抛）。

    顺序是 A → B → C，跟 scripts/seal_secret.py 里完全一致 —— 顺序错了
    密钥就不是同一把，密文解不开（tag 校验失败），表现成「解出来是空串」。
    """
    global _SB_MATERIAL_CACHE
    if _SB_MATERIAL_CACHE is not None:
        return _SB_MATERIAL_CACHE
    try:
        _SB_MATERIAL_CACHE = secretbox.derive_key(
            base64.b64decode(_SB_A),
            base64.b64decode(secretbox._SB_B),
            base64.b64decode("mTVmSzPtW3vsN6WJN00SUYfj"),      # 第三段
            salt=secretbox._SB_SALT,
        )
    except Exception:
        return b""
    return _SB_MATERIAL_CACHE


def _sealed_secret():
    """解出随二进制分发的 client_secret；解不出来一律返回空串。

    解不开的现实原因只有一个：改了源码里的常量却没重跑
    scripts/seal_secret.py（或只换了三段素材里的某几段）。这时 client_id
    照常可用，登录会在 GitHub 那侧报 incorrect_client_credentials ——
    面板上已有中文解释，所以这里不报错、只留一条 debug 级日志。
    """
    if not _SEALED_CLIENT_SECRET:
        return ""
    key = _sb_key_material()
    plain = secretbox.open_sealed(_SEALED_CLIENT_SECRET, key) if key else None
    if plain is None:
        # 用 debug 而不是 error：这是构建期的问题，不该打扰用户
        logging.getLogger(__name__).debug(
            "内置凭据解不开（构建时可能没跑 seal 脚本）")
        return ""
    try:
        return plain.decode("utf-8").strip()
    except Exception:
        return ""


# ───────────────────────── PKCE ─────────────────────────
# RFC 7636：verifier 是 43~128 个「A-Z a-z 0-9 - . _ ~」，challenge 是
# base64url(sha256(verifier)) 去掉 '=' 填充。

def make_code_verifier():
    """造一个 code_verifier。

    token_urlsafe(64) 出 86 个字符（64 字节 → base64url 无填充），落在
    RFC 允许的 43~128 之间，字符集就是 A-Za-z0-9-_ —— 正好是合法的那个集合。
    """
    return secrets.token_urlsafe(64)


def code_challenge(verifier):
    """S256：base64url(sha256(verifier))，去掉 '=' 填充。"""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_state():
    """一次性的 state。

    它唯一的作用是「这个回调是不是我这次发的」：回环端口谁都能连，
    state 不对的请求一律不能当授权结果。
    """
    return secrets.token_urlsafe(24)


def build_authorize_url(client_id, redirect_uri, state, challenge,
                        scope=DEFAULT_SCOPE):
    """拼授权页 URL（浏览器打开的就是它）。"""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": scope,
    }
    return AUTHORIZE_ENDPOINT + "?" + urllib.parse.urlencode(params)


# ───────────────────── Github App 凭据 ─────────────────────

def _secret_from_file():
    """从 BML/githubApp.json 里只取 client_secret（没有就返回空串）。

    为什么单独一个函数：client_id 内置在源码里没问题，secret 不行 ——
    仓库公开时它跟着源码一起公开，GitHub 的 secret scanning 还会直接把它撤销掉。
    """
    try:
        with open(path_utils.getPath(APP_CONFIG_REL), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("client_secret") or "").strip()


def load_app_config():
    """取 App 凭据：内置常量 → src/env.py → 内置密封常量 → BML/githubApp.json。

    返回 (client_id, client_secret, 错误文案)。

    三个返回值里**最多只有一个**非 None：要么拿到 client_id，要么带一句话
    说明为什么没有。调用方不需要自己判空文件、判空字段、判坏 JSON。

    四个来源的优先级是有讲究的：先让「自带一份」的用户无感可用（内置常量 /
    密封常量），再让本机开发者随手盖掉（src/env.py，已 gitignore），最后才
    读用户自己填的 json。拿不到 secret 时 client_id 照样能用：登录会在
    GitHub 那侧报 incorrect_client_credentials，面板里有中文解释。
    """
    builtin = str(BUILTIN_CLIENT_ID or "").strip()
    if builtin:
        # 内置一份就直接用：普通用户不该为了登录去建 App、填 json
        secret = str(BUILTIN_CLIENT_SECRET or "").strip()
        if not secret:
            secret = str(_LOCAL_CLIENT_SECRET or "").strip()
        if not secret:
            # 随二进制分发的那个：密文常量 + 三段素材，解不开就是空串
            secret = _sealed_secret()
        if not secret:
            # 仓库是公开的：client_id 晒在源码里无所谓，secret 不该跟着走。
            # 本机的 BML/githubApp.json 里只写 {"client_secret": "…"} 也能用。
            secret = _secret_from_file()
        return builtin, (secret or None), None

    path = path_utils.getPath(APP_CONFIG_REL)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, None, "还没有配置 GitHub App：请在 BML/githubApp.json 里填 client_id"
    except Exception as e:
        return None, None, f"BML/githubApp.json 读不出来（不是合法 JSON）：{e}"
    if not isinstance(data, dict):
        return None, None, "还没有配置 GitHub App：请在 BML/githubApp.json 里填 client_id"
    client_id = str(data.get("client_id") or "").strip()
    # secret 只有 confidential client（GitHub App 生成了 client secret）才有；
    # public client 没它也够 —— PKCE 已经把「谁换的 code」钉住了。
    client_secret = str(data.get("client_secret") or "").strip() or None
    if not client_id:
        return None, None, "还没有配置 GitHub App：请在 BML/githubApp.json 里填 client_id"
    return client_id, client_secret, None


# ───────────────────── 本地回环监听 ─────────────────────

def _page(message):
    """回调落地页：极简一屏，只用来说「可以关掉了」。"""
    return _PAGE_TMPL.format(msg=html.escape(message))


_PAGE_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book MDT Launcher</title>
<style>
  html,body{{height:100%;margin:0}}
  body{{display:flex;align-items:center;justify-content:center;
        font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
        background:#f6f8fa;color:#24292f}}
  .card{{padding:30px 42px;border-radius:12px;background:#fff;
        box-shadow:0 2px 16px rgba(0,0,0,.08);text-align:center;font-size:15px}}
  .t{{font-size:18px;font-weight:600;margin-bottom:8px}}
</style>
</head>
<body>
<div class="card"><div class="t">Book MDT Launcher</div><div>{msg}</div></div>
</body>
</html>
"""


class LoopbackServer:
    """127.0.0.1 上的一次性回环监听：等浏览器把 code 带回来。

    端口由内核分配（bind 到 0），所以不会跟用户机器上别的服务抢端口，也不
    需要事先约定一个固定端口。只认 /callback 一条路径，别的一律 404 ——
    等待期间这个端口对本机所有进程都是敞开的，能少给一个入口就少给一个。

    生命周期是 start() → wait() → close()，三步都可以单独测：
    wait() 返回 True/False（等到 / 超时或取消），结果看 .code / .error。
    """

    def __init__(self, expected_state, timeout=DEFAULT_TIMEOUT):
        self.expected_state = expected_state
        self.timeout = timeout
        self.code = None
        self.error = None
        self.port = None
        self._server = None
        self._thread = None
        self._got = threading.Event()

    # ---------- 起停 ----------

    def start(self):
        """起监听并返回实际端口（调用方据此拼 redirect_uri）。"""
        self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._serve, name="bml-github-oauth", daemon=True)
        self._thread.start()
        return self.port

    def _serve(self):
        try:
            self._server.serve_forever(poll_interval=0.1)
        except Exception:
            # close() 会从别的线程关掉 socket，这里退出来就好
            pass

    def close(self):
        """停线程 + 关 socket；重复调用安全。"""
        srv, self._server = self._server, None
        if srv is not None:
            try:
                # shutdown() 必须由 serve_forever 之外的线程调用 —— 本方法
                # 永远是从等待方（工作线程）进来的，正好满足。
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        thr, self._thread = self._thread, None
        if thr is not None and thr is not threading.current_thread():
            thr.join(timeout=2.0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---------- 等待 ----------

    def wait(self, cancel=None, timeout=None):
        """等回调；拿到 code / 出错返回 True，超时或取消返回 False。

        不能直接 event.wait(180)：取消是用户在别的线程按的，得让等待方每隔
        一小会儿回来看一眼 cancel，否则「取消」要等满三分钟才生效。
        """
        limit = self.timeout if timeout is None else timeout
        deadline = time.time() + limit
        while True:
            if cancel is not None and cancel.is_set():
                return False
            remain = deadline - time.time()
            if remain <= 0:
                return False
            if self._got.wait(min(0.2, remain)):
                return True

    # ---------- 请求处理 ----------

    def _make_handler(self):
        owner = self
        expected_state = self.expected_state

        class _Handler(BaseHTTPRequestHandler):
            # 回环端口上的访问不打日志：一次授权会带出好几条 noisy 的请求行
            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/favicon.ico":
                    # 浏览器会顺手来要图标。给个 404 就行，别当错误、别结束流程。
                    self._empty(404)
                    return
                # 只认这两条：我们自己拼的是 /callback；万一 App 里填成
                # http://127.0.0.1（不带路径），浏览器回到的就是 "/"
                if parsed.path not in (CALLBACK_PATH, "/"):
                    self._empty(404)
                    return

                query = urllib.parse.parse_qs(parsed.query)
                got_state = (query.get("state") or [""])[0]
                if got_state != expected_state:
                    # state 不对：这不是本次授权发出的回调。回 400 但**不结束等待**
                    # —— 真正的回调可能还在后面，别让一个陌生请求把流程废掉。
                    self._html(400, "state 校验失败，这次请求已被忽略。")
                    return

                err = (query.get("error") or [""])[0]
                if err:
                    owner.error = err
                    self._html(400, "授权没有完成，可以关闭此页面。")
                    owner._got.set()
                    return

                code = (query.get("code") or [""])[0]
                if not code:
                    self._html(400, "回调里没有 code，请回到启动器重新登录。")
                    return

                owner.code = code
                self._html(200, "授权完成，可以关闭此页面。")
                # 先把响应写回浏览器，再放等待方走：反过来的话等待方可能
                # 立刻 close() 掉 socket，用户那边看到的是「连接被重置」。
                owner._got.set()

            def _empty(self, status):
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except Exception:
                    pass

            def _html(self, status, message):
                try:
                    body = _page(message).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception:
                    # 浏览器提前断开是常事（用户点得快），不该把等待方吵醒
                    pass

        return _Handler


# ───────────────────── 打开系统浏览器 ─────────────────────

class _BrowserBridge(QObject):
    """住在 GUI 线程上的「打开浏览器」代理。

    QDesktopServices 是 GUI 线程的活，而授权流程本身跑在后台线程（它要阻塞
    等回调）。所以后台线程不直接调它，而是把请求发给这个代理、再等回话。
    """

    requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._done = threading.Event()
        self._ok = False
        self.requested.connect(self._on_requested, Qt.QueuedConnection)

    @Slot(str)
    def _on_requested(self, url):
        try:
            self._ok = _open_url_now(url)
        finally:
            self._done.set()

    def open(self, url, timeout=15.0):
        """子线程调用：请主线程打开，阻塞到它给结果为止。"""
        self._done.clear()
        self.requested.emit(url)
        if not self._done.wait(timeout):
            # 主线程没有事件循环（或卡住了）—— 当作没打开，让调用方给出兜底
            return False
        return self._ok


_BRIDGE = None
_BRIDGE_LOCK = threading.Lock()


def _open_url_now(url):
    """真正调用 QDesktopServices 的那一行（必须在 GUI 线程）。"""
    try:
        from PySide6.QtGui import QDesktopServices
        return bool(QDesktopServices.openUrl(QUrl(url)))
    except Exception:
        return False


def open_in_browser(url, timeout=15.0):
    """用系统浏览器打开 URL，返回是否成功派发。"""
    app = QCoreApplication.instance()
    if app is None:
        # 没有 Qt 应用（纯脚本里）就不存在线程问题，就地调用即可
        return _open_url_now(url)
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = _BrowserBridge()
        if _BRIDGE.thread() is not app.thread():
            _BRIDGE.moveToThread(app.thread())
        bridge = _BRIDGE
    return bridge.open(url, timeout=timeout)


# ─────────────────── 授权包与过期判断 ───────────────────
# 换回来的不是一个裸 token，而是一块「授权包」：
#     {"access", "refresh", "expires_at", "refresh_expires_at",
#      "scope", "token_type"}
# 原因是 GitHub App 勾了「Expire user authorization tokens」之后，access_token
# 只有 8 小时，续期全靠同一个响应里的 refresh_token（6 个月、单次使用 + 轮换）。
# 只留 access 等于把这份授权当成一次性的，8 小时后用户就得重登一遍。

def expires_at_from(now, expires_in):
    """把「还有多少秒过期」换算成绝对时间戳（epoch 秒）。

    存绝对值而不是 GitHub 给的秒数：settings.json 是长期文件，相对秒数一重启
    就失去意义（过两天再打开，「还有 28800 秒」到底是当初的 8 小时还是现在的，
    没人算得清）。
    `expires_in` 缺失或不是正数时返回 None —— 那是「这块 token 不过期」
    （App 没勾「Expire user authorization tokens」），不是「已经过期」。
    """
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return int(now) + seconds


def needs_refresh(expires_at, now, skew=60):
    """这块 access token 是不是该刷新了。

    expires_at 为 None（没有过期时间）时永远 False。
    skew=60 是提前量：一次请求要排队、发出去、GitHub 处理、HTTP 往返回来，
    卡在 expires_at 前最后一秒刷新等于拿一个「出门时还没过期」的 token 去
    撞 401。宁可早一分钟换，也别让用户在一次点击里看到莫名的失败。
    时间戳看不懂（存坏了 / 老格式）时按「不需要刷新」处理，让请求自己去撞
    401 —— 那条路上还有一次「刷新后重试」，不会白丢授权包。
    """
    if expires_at is None:
        return False
    try:
        return float(now) >= float(expires_at) - float(skew)
    except (TypeError, ValueError):
        return False


# ───────────────────── 换 token ─────────────────────

# 失败有两种，处置完全不同：
#   * GitHub 明确拒了 refresh_token（bad_refresh_token）—— 凭据真的死了，
#     必须清掉授权包让用户重登，留着只会让每个请求白撞一次 401；
#   * 这会儿连不上 GitHub —— 凭据一点问题都没有，清了等于逼用户断网时重登。
# 两者都收敛成 (False, 中文原因, None)，所以用这个字样区分：githubAPI 靠它
# 决定要不要清授权包。换 token 与刷新 token 两处必须拼同一句话 ——
# 少一个字就变成「断网即登出」。
NETWORK_ERROR_HINT = "网络出错"

# token 端点被挡时（HTTP 404）给用户的话。写成常量是因为换 code 与刷新两条
# 路都要说同一句话：用户看到的应该是「换条网络 / 查代理」，而不是去翻参数。
# 开头必须是 NETWORK_ERROR_HINT —— 它同时是「别把这次失败当成凭据失效」的
# 标记，见 githubAPI._refresh_now：被挡一次就把人登出，是最难解释的 bug。
_BLOCKED_HINT = (NETWORK_ERROR_HINT + "：token 端点返回 404（被网络或代理挡了），"
                 "请检查系统代理 / 加速器，或换个网络后重试")

# GitHub 的 error 码 → 用户看得懂的一句话。error 码本身是英文短横线词，
# 直接甩给用户等于没解释；error_description 是英文长句，附在括号里当细节。
_OAUTH_ERRORS = {
    "bad_verification_code": "授权码无效或已过期，请重新登录",
    "incorrect_client_credentials":
        "client_id 或 client_secret 不正确，请检查 BML/githubApp.json",
    "redirect_uri_mismatch":
        "回调地址对不上：请把 GitHub App 的 Authorization callback URL "
        "设为 http://127.0.0.1/callback（端口任意）",
    "unsupported_grant_type": "GitHub 不接受这次换取 token 的请求",
    "access_denied": "授权被拒绝（在授权页点了取消）",
    "device_flow_disabled": "这个 GitHub App 没有开启 OAuth 授权",
    "unverified_user_email": "GitHub 账号还没验证邮箱",
    # 刷新链路专用。refresh_token 是单次使用的：轮换后旧值、超过 6 个月、
    # 或用户在网页上撤销了授权，换回来的都是这一条。对用户来说只有一句话
    # 有意义 —— 重新登录：refresh 自身不能自愈，重试多少次都一样。
    "bad_refresh_token": "登录已失效，请重新登录",
}


def _explain_oauth_error(error, description=""):
    """把 GitHub 的 error/error_description 变成一句中文。"""
    key = (error or "").strip().lower()
    desc = (description or "").strip()
    zh = _OAUTH_ERRORS.get(key)
    if zh:
        return f"{zh}（{desc}）" if desc else zh
    if key:
        return f"GitHub 返回错误 {key}" + (f"：{desc}" if desc else "")
    return desc or "GitHub 没有给出原因"


def _post_token(data, session, timeout):
    """POST 一次 access_token 端点，返回 (kind, payload)。

    换 token 与刷新 token 打的是同一个端点、同一套 JSON、同一套错误码，差别
    只在请求体（code + verifier 还是 grant_type=refresh_token），所以请求本身
    收在一处。失败分四种，中文话术由调用方按 kind 拼：

        "ok"       payload 是响应 body（dict）
        "net"      payload 是异常对象（连不上 / 超时 / SSL）
        "http"     payload 是状态码（非 200）
        "blocked"  payload 是 404：这个端点被网络/代理挡了（实测过：某些网络
                   对 github.com/login/oauth/access_token 直接回 404 JSON，
                   而同域的 /login/oauth/authorize 一切正常 —— 所以这不是
                   我们请求写错了，单列一类，话术才能指向「代理」而不是
                   「请检查参数」；这一类的文案里带 NETWORK_ERROR_HINT，
                   于是调用方也不会把它当成「凭据失效」）
        "json"     payload 是 None（200 但不是 JSON：多半被代理或加速器拦了）

    session 传 githubAPI 那个 session：它已经配好系统代理和合并后的 CA
    bundle（加速器把根证书装进 Windows 证书库，裸 requests 会误报 SSL 失败）。
    """
    headers = {"Accept": "application/json"}
    try:
        if session is not None:
            resp = session.post(TOKEN_ENDPOINT, data=data,
                                headers=headers, timeout=timeout)
        else:
            import requests
            resp = requests.post(TOKEN_ENDPOINT, data=data,
                                 headers=headers, timeout=timeout)
    except Exception as e:
        return "net", e
    if resp.status_code == 404:
        # 见上面 "blocked" 那一行：我们的请求体没问题，是这条路被挡了
        return "blocked", resp.status_code
    if resp.status_code != 200:
        return "http", resp.status_code
    try:
        return "ok", resp.json()
    except Exception:
        return "json", None


def _blob_from_body(body, now=None):
    """把 GitHub 的换 token 响应整理成授权包。

    refresh 与 expires_at 一律走这里，形状就不会两处漂移 —— 而这份形状是
    要原样加密进 settings 的，漂一次就是「存下来的东西读不回来」。

    expires_in 缺失时 expires_at 是 None（App 没勾「Expire user authorization
    tokens」→ 这块 token 不过期），needs_refresh 见到 None 就当「不用刷新」，
    不会每来一个请求就白刷一次。
    """
    now = time.time() if now is None else now
    return {
        "access": body.get("access_token") or None,
        "refresh": body.get("refresh_token") or None,
        "expires_at": expires_at_from(now, body.get("expires_in")),
        "refresh_expires_at":
            expires_at_from(now, body.get("refresh_token_expires_in")),
        "scope": body.get("scope") or "",
        "token_type": body.get("token_type") or "bearer",
    }


def exchange_code(client_id, code, redirect_uri, verifier, client_secret=None,
                  session=None, timeout=30):
    """用 code + verifier 换授权包，返回 (ok, 中文原因, blob)。

    换回来的是**一个字典**而不是裸 token：GitHub App 勾了「Expire user
    authorization tokens」之后，access_token 8 小时就过期，同一次响应里的
    refresh_token（6 个月、单次使用 + 轮换）才是下次还能用的凭据。只要
    access 不要 refresh，等于把这份登录当成一次性的。
    """
    data = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    kind, payload = _post_token(data, session, timeout)
    if kind == "net":
        return False, f"换取 token 时{NETWORK_ERROR_HINT}：{payload}", None
    if kind == "blocked":
        return False, _BLOCKED_HINT, None
    if kind == "http":
        return False, f"GitHub 拒绝了这次换取 token 的请求（HTTP {payload}）", None
    if kind == "json":
        return False, "GitHub 返回的不是 JSON（可能被代理或加速器拦了）", None
    blob = _blob_from_body(payload)
    if blob["access"]:
        return True, "", blob
    return False, _explain_oauth_error(payload.get("error"),
                                       payload.get("error_description")), None


def refresh_access_token(client_id, refresh_token, client_secret=None,
                         session=None, timeout=30):
    """用 refresh_token 换一块新的授权包，返回 (ok, 中文原因, blob)。

    响应形状与 exchange_code 一模一样，所以两处共用 _blob_from_body。

    **单次使用 + 轮换**：成功拿到的 refresh_token 是新的，旧的当场作废。
    调用方必须把返回的整块存下来 —— 拿旧的那份再试一次只会得到
    bad_refresh_token，那时就真的只能重登了。

    客户端身份：我们走的是 PKCE public client（BML/githubApp.json 通常只填
    client_id，桌面端不放 secret），所以默认**不带 client_secret**。GitHub
    文档说这个端点「可以」带 client_secret（confidential client 必带）；
    没配置就不带 —— 实测 public client 不带 secret 也能换（这一条要真连上
    GitHub 才能确认，纯本地自测只验到请求体形状）。万一哪天这个 App 被要求
    带 secret 而我们没配，这里会返回 bad_refresh_token；那时的退路是**不勾**
    「Expire user authorization tokens」，退回不过期的 access token（见模块
    顶部说明）。
    """
    if not refresh_token:
        # 老格式（只存过一个裸 token）或 App 没勾过期：手里没有续期凭据
        return False, "没有可用的 refresh_token，请重新登录", None
    data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret
    kind, payload = _post_token(data, session, timeout)
    if kind == "net":
        return False, f"刷新 token 时{NETWORK_ERROR_HINT}：{payload}", None
    if kind == "blocked":
        return False, _BLOCKED_HINT, None
    if kind == "http":
        return False, f"GitHub 拒绝了这次刷新 token 的请求（HTTP {payload}）", None
    if kind == "json":
        return False, "GitHub 返回的不是 JSON（可能被代理或加速器拦了）", None
    blob = _blob_from_body(payload)
    if blob["access"]:
        return True, "", blob
    return False, _explain_oauth_error(payload.get("error"),
                                       payload.get("error_description")), None


# ───────────────────── 完整流程 ─────────────────────

def authorize(scope=DEFAULT_SCOPE, timeout=DEFAULT_TIMEOUT, cancel=None,
              open_url=None, session=None):
    """跑一次完整授权：起监听 → 开浏览器 → 等回调 → 换授权包。

    返回 (ok, message, blob)。message 是给用户看的中文；成功时为空串；
    blob 是 exchange_code 那块授权包（含 refresh_token 与两个过期秒数换算
    出来的时间戳），调用方要整块存下来 —— 只剩 access 的话，8 小时后就没
    东西可续了。
    监听一定会在返回前关掉 —— 无论走的是哪条分支。

    cancel 是一个 threading.Event：置位即视为用户取消（关面板就会置它）。
    open_url 可以注入一个假的「打开浏览器」，测试里用它避开真实外跳。
    """
    client_id, client_secret, err = load_app_config()
    if err:
        # 凭据都没有就别起监听了：端口开着等一个永远不会来的回调，
        # 用户只会看到「正在等待浏览器授权…」卡三分钟。
        return False, err, None

    state = make_state()
    verifier = make_code_verifier()
    server = None
    try:
        server = LoopbackServer(state, timeout=timeout)
        try:
            port = server.start()
        except OSError as e:
            return False, f"没能在 127.0.0.1 上打开本地端口：{e}", None

        redirect_uri = f"http://127.0.0.1:{port}{CALLBACK_PATH}"
        url = build_authorize_url(client_id, redirect_uri, state,
                                  code_challenge(verifier), scope)
        opener = open_url or open_in_browser
        try:
            opened = bool(opener(url))
        except Exception:
            opened = False
        if not opened:
            return False, "打不开系统浏览器，请手动打开这个地址完成授权：" + url, None

        if not server.wait(cancel=cancel):
            if cancel is not None and cancel.is_set():
                return False, "已取消授权", None
            return False, f"等待授权超时（{int(timeout)} 秒），请重试", None
        if server.error:
            return False, "授权没有完成：" + _explain_oauth_error(server.error), None
        if not server.code:
            return False, "没有拿到授权码，请重试", None

        return exchange_code(client_id, server.code, redirect_uri, verifier,
                             client_secret=client_secret, session=session)
    except Exception as e:
        # 这一层兜的是「意料之外」：任何异常都不该冒到 UI 线程上去
        return False, f"授权流程出错：{e}", None
    finally:
        if server is not None:
            server.close()
