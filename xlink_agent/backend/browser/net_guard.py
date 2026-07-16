"""禁内网 URL 校验"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_blocked_host(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return True
    if h in {"localhost", "metadata.google.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(h)
        return any(ip in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(h, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
            if any(ip in net for net in _BLOCKED_NETWORKS):
                return True
        except ValueError:
            continue
    return False


def assert_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅允许 http/https")
    host = parsed.hostname or ""
    if is_blocked_host(host):
        raise ValueError(f"禁止访问内网或本机地址: {host}")
    return url
