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

密封盒：ChaCha20 + HMAC-SHA256，只用标准库。

**这不是「防止拿到」，只是「提高成本」。**
随二进制一起发出去的对称密钥，理论上总能被逆出来 —— 它就在同一个进程的
内存里，谁愿意反编译谁就能拿到。这一层只解决三件具体的事：

  1. `strings <exe> | grep` 抓不到明文（密文是 base64，看着就是一串噪音）；
  2. 明文不再躺在源码里，被 GitHub 的 secret scanning 判成泄露的概率降低；
  3. 改密文/改 tag 任意一个字节，认证就失败（不会静默解出一串垃圾）。

所以：**不要在这层之上放任何「安全假设」**。真正的边界依旧是 PKCE（钉住
授权发起方）+ 可撤销 + refresh 轮换；client_secret 本来就是 token 端点
强制要求的半公开凭据（桌面端留不住它），这里只是别让它裸奔。

为什么不引入 `cryptography`
---------------------------
为一个几十字节的常量装一整个第三方依赖（还要跟着 Python 版本重装）不划算，
ChaCha20 在 RFC 8439 里只有几十行，纯 Python 跑几十字节的开销可以忽略。
"""

import base64
import hashlib
import hmac
import secrets
import struct

__all__ = ["derive_key", "seal", "open_sealed", "chacha20_xor", "KEY_WORDS"]

_MASK = 0xFFFFFFFF

# "expand 32-byte k"
_CONST = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)

# 三段素材的中间一段（base64）。三段分开放在三个文件/函数里，就是为了
# 不让「key 是怎么拼出来的」一眼被串起来 —— 单独看到任何一段都没用。
# 由 scripts/seal_secret.py 每次随机生成，不同构建的二进制里这一段不同。
_SB_B = "wmadwSeFESLhsOgD6ap/tWLt"

# PBKDF2 的盐。盐不是机密，放在这里当唯一真源：生成工具和运行时都读它，
# 免得两边各写一份、改了一边忘了另一边，结果「解不开」。
_SB_SALT = "bml-github-app-salt-2026"

# 迭代次数：故意偏高。总共只算一次（githubAuth 会缓存派生结果），
# 每次启动多花几十毫秒，换篡改/爆破的成本高一个量级。
_KDF_ROUNDS = 120000

# 认证标签的域分隔串：同一把 key 干别的事时标签前缀不同，防止跨用途重放。
_TAG_AAD = b"bml-secretbox"

KEY_WORDS = 32


# ───────────────────── ChaCha20（RFC 8439） ─────────────────────

def _rotl(v, n):
    """32 位循环左移。"""
    return ((v << n) & _MASK) | (v >> (32 - n))


def _quarterround(s, a, b, c, d):
    """RFC 8439 §2.1 的 quarter round，就地修改 16 个字里的四个。"""
    s[a] = (s[a] + s[b]) & _MASK
    s[d] = _rotl(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & _MASK
    s[b] = _rotl(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & _MASK
    s[d] = _rotl(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & _MASK
    s[b] = _rotl(s[b] ^ s[c], 7)


def _block(key, counter, nonce):
    """算一个 64 字节的密钥流块（§2.3：state = 常量|key|counter|nonce）。"""
    init = (list(_CONST)
            + list(struct.unpack("<8I", key))
            + [counter & _MASK]
            + list(struct.unpack("<3I", nonce)))
    w = init[:]
    for _ in range(10):          # 10 轮，每轮 4 列 + 4 对角
        _quarterround(w, 0, 4, 8, 12)
        _quarterround(w, 1, 5, 9, 13)
        _quarterround(w, 2, 6, 10, 14)
        _quarterround(w, 3, 7, 11, 15)
        _quarterround(w, 0, 5, 10, 15)
        _quarterround(w, 1, 6, 11, 12)
        _quarterround(w, 2, 7, 8, 13)
        _quarterround(w, 3, 4, 9, 14)
    # 最后一步是和初始 state 相加（不是异或）—— 漏了这步加密照样「能跑」，
    # 但解出来的东西就跟标准 ChaCha20 不是一个东西了
    return struct.pack("<16I", *[(w[i] + init[i]) & _MASK
                                 for i in range(16)])


def chacha20_xor(key32, nonce12, counter, data):
    """ChaCha20 加/解密（对称，同一函数两用）。

    数据只有几十字节，所以按块老老实实算就行，不做任何优化。
    """
    if len(key32) != KEY_WORDS:
        raise ValueError("ChaCha20 需要 32 字节密钥")
    if len(nonce12) != 12:
        raise ValueError("ChaCha20 需要 12 字节 nonce")
    out = bytearray()
    data = bytes(data)
    for i in range(0, len(data), 64):
        ks = _block(key32, counter + i // 64, nonce12)
        chunk = data[i:i + 64]
        out += bytes(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


# ───────────────────── 密钥派生 ─────────────────────

def _as_bytes(x):
    return x if isinstance(x, (bytes, bytearray)) else str(x).encode("utf-8")


def derive_key(*materials, salt):
    """把若干段素材拼起来，PBKDF2-HMAC-SHA256 派生出 32 字节密钥。

    为什么用 KDF 而不是直接 sha256(素材)：素材每段只有十几字节，拼接后
    直接哈希快到没成本，PBKDF2 至少让「拿到密文后猜素材」变慢。

    素材和盐都可以是 bytes 或 str；顺序就是传参顺序 —— 生成工具与运行
    时**必须**用同一个顺序，否则解不开。
    """
    if not materials:
        raise ValueError("derive_key 至少需要一段素材")
    joined = b"".join(_as_bytes(m) for m in materials)
    return hashlib.pbkdf2_hmac("sha256", joined, _as_bytes(salt),
                               _KDF_ROUNDS, KEY_WORDS)


# ───────────────────── 封 / 开 ─────────────────────

def seal(plaintext, key32):
    """把明文封成 base64 串：nonce(12) | tag(32) | 密文。

    nonce 每次随机 —— 同一把 key 封两次（比如两次构建填了同一个 secret）
    出来的串也不同，不会有「两条密文一样」这种一眼能看出关系的东西。
    counter 从 1 开始（RFC 8439 §2.4 的惯例），0 号块留着备用。
    """
    if len(key32) != KEY_WORDS:
        raise ValueError("seal 需要 32 字节密钥")
    nonce = secrets.token_bytes(12)
    ct = chacha20_xor(key32, nonce, 1, plaintext)
    tag = hmac.new(key32, _TAG_AAD + nonce + ct, hashlib.sha256).digest()
    return base64.b64encode(nonce + tag + ct).decode("ascii")


def open_sealed(blob, key32):
    """解封；任何不对劲的地方都返回 None，绝不抛给调用方。

    调用方（githubAuth）在启动/登录路径上，这里抛异常等于让「构建时少跑
    了一次 seal 脚本」变成用户看到的崩溃。所以：空串、乱码 base64、长度
    不够、tag 对不上、密钥错 —— 一律 None。
    """
    try:
        if not blob:
            return None
        if len(key32) != KEY_WORDS:
            return None
        raw = base64.b64decode(_as_bytes(blob), validate=True)
        if len(raw) < 12 + 32:
            return None
        nonce, tag, ct = raw[:12], raw[12:44], raw[44:]
        want = hmac.new(key32, _TAG_AAD + nonce + ct, hashlib.sha256).digest()
        # 常数时间比较：这里虽然没有远程攻击者，但没必要留一个「按字节比」
        # 的坏习惯在代码里被人抄走
        if not hmac.compare_digest(want, tag):
            return None
        return chacha20_xor(key32, nonce, 1, ct)
    except Exception:
        return None
