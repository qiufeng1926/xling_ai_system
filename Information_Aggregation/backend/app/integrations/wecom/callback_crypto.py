"""企业微信回调 URL 校验与消息加解密（文档 path/90930）"""

from __future__ import annotations

import base64
import hashlib
import socket
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCallbackError(Exception):
    pass


def _sha1_signature(*parts: str) -> str:
    items = sorted(str(p) for p in parts if p is not None)
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def _decode_aes_key(encoding_aes_key: str) -> bytes:
    key = (encoding_aes_key or "").strip()
    if len(key) != 43:
        raise WeComCallbackError("EncodingAESKey 长度应为 43 字符")
    try:
        return base64.b64decode(key + "=")
    except Exception as exc:
        raise WeComCallbackError("EncodingAESKey 无效") from exc


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise WeComCallbackError("解密结果为空")
    pad = data[-1]
    if pad < 1 or pad > 32:
        raise WeComCallbackError("解密 padding 无效")
    return data[:-pad]


def decrypt_echostr(encoding_aes_key: str, echostr: str, corp_id: str) -> str:
    aes_key = _decode_aes_key(encoding_aes_key)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_key[:16]))
    decryptor = cipher.decryptor()
    try:
        plain = decryptor.update(base64.b64decode(echostr)) + decryptor.finalize()
    except Exception as exc:
        raise WeComCallbackError("echostr 解密失败") from exc
    plain = _pkcs7_unpad(plain)
    msg_len = struct.unpack("!I", plain[16:20])[0]
    msg = plain[20 : 20 + msg_len].decode("utf-8")
    receive_id = plain[20 + msg_len :].decode("utf-8")
    if receive_id and corp_id and receive_id != corp_id:
        raise WeComCallbackError("CorpID 与解密结果不一致")
    return msg


def verify_url(
    *,
    token: str,
    encoding_aes_key: str,
    corp_id: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
) -> str:
    sign = _sha1_signature(token, timestamp, nonce, echostr)
    if sign != msg_signature:
        raise WeComCallbackError("msg_signature 校验失败")
    return decrypt_echostr(encoding_aes_key, echostr, corp_id)


def decrypt_message(
    *,
    token: str,
    encoding_aes_key: str,
    corp_id: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    encrypt: str,
) -> str:
    sign = _sha1_signature(token, timestamp, nonce, encrypt)
    if sign != msg_signature:
        raise WeComCallbackError("msg_signature 校验失败")
    return decrypt_echostr(encoding_aes_key, encrypt, corp_id)
