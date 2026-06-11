"""生成本地开发用自签名 HTTPS 证书（解决局域网 IP 无法使用麦克风的问题）。"""
from __future__ import annotations

import datetime
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    cert_dir = root / "certs"
    cert_dir.mkdir(exist_ok=True)
    key_path = cert_dir / "dev-key.pem"
    cert_path = cert_dir / "dev-cert.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Meeting AI Dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[OK] 证书已生成: {cert_path}")
    print(f"[OK] 私钥已生成: {key_path}")
    print()
    print("启动 HTTPS 开发服务:")
    print(
        "  uvicorn api.main:app --host 0.0.0.0 --port 8000 "
        f"--ssl-keyfile={key_path} --ssl-certfile={cert_path}"
    )
    print()
    print("浏览器首次访问需信任自签名证书，之后即可使用麦克风。")


if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("请先安装: pip install cryptography", file=sys.stderr)
        sys.exit(1)
