"""飞书事件订阅回调加解密"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class FeishuCallbackError(Exception):
    pass


def _sha256_signature(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
    raw = f"{timestamp}{nonce}{encrypt_key}{body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _aes_key(encrypt_key: str) -> bytes:
    key = (encrypt_key or "").strip()
    if not key:
        raise FeishuCallbackError("FEISHU_ENCRYPT_KEY 未配置")
    return hashlib.sha256(key.encode("utf-8")).digest()


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise FeishuCallbackError("解密结果为空")
    pad = data[-1]
    if pad < 1 or pad > 32:
        raise FeishuCallbackError("解密 padding 无效")
    return data[:-pad]


def decrypt_event(encrypt_key: str, encrypt: str) -> dict[str, Any]:
    key = _aes_key(encrypt_key)
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    try:
        plain = decryptor.update(base64.b64decode(encrypt)) + decryptor.finalize()
        plain = _pkcs7_unpad(plain)
        return json.loads(plain.decode("utf-8"))
    except Exception as exc:
        raise FeishuCallbackError("事件解密失败") from exc


def verify_signature(
    *,
    timestamp: str,
    nonce: str,
    encrypt_key: str,
    body: str,
    signature: str,
) -> None:
    expected = _sha256_signature(timestamp, nonce, encrypt_key, body)
    if expected != signature:
        raise FeishuCallbackError("签名校验失败")
