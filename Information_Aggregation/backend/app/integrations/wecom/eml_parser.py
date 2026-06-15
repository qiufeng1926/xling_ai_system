"""解析企业微信 read_mail 返回的 EML 内容"""

from __future__ import annotations

import base64
import binascii
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser


def _decode_mail_data(raw: str) -> bytes:
    text = (raw or "").strip()
    if not text:
        return b""
    if text.startswith("Received:") or text.startswith("From:") or text.startswith("Return-Path:"):
        return text.encode("utf-8", errors="replace")
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return text.encode("utf-8", errors="replace")


def _extract_body(msg: EmailMessage) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            ctype = part.get_content_type()
            try:
                payload = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload.decode(charset, errors="replace")
            if not isinstance(payload, str):
                continue
            if ctype == "text/html":
                html_parts.append(payload)
            elif ctype == "text/plain":
                plain_parts.append(payload)
    else:
        try:
            payload = msg.get_content()
        except Exception:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                payload = payload.decode(charset, errors="replace")
        if isinstance(payload, str):
            if msg.get_content_type() == "text/html":
                html_parts.append(payload)
            else:
                plain_parts.append(payload)
    return "\n".join(plain_parts).strip(), "\n".join(html_parts).strip()


def parse_mail_data(mail_data: str) -> dict:
    raw_bytes = _decode_mail_data(mail_data)
    if not raw_bytes:
        return {
            "subject": "",
            "from": "",
            "to": "",
            "date": "",
            "body_text": "",
            "body_html": "",
        }
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    body_text, body_html = _extract_body(msg)
    return {
        "subject": str(msg.get("Subject", "") or ""),
        "from": str(msg.get("From", "") or ""),
        "to": str(msg.get("To", "") or ""),
        "date": str(msg.get("Date", "") or ""),
        "body_text": body_text,
        "body_html": body_html,
    }
