# -*- coding: utf-8 -*-
"""Local MySQL setup script. Usage: python scripts/setup_db.py"""

import getpass
import os
import re
import secrets
import sys

try:
    import pymysql
except ImportError:
    print("请先安装 pymysql: pip install pymysql")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SQL_FILE = os.path.join(SCRIPT_DIR, "setup_local.sql")
ENV_FILE = os.path.join(PROJECT_DIR, "backend", ".env")

APP_USER = "app_user"
APP_PASSWORD = "app123"
DB_NAME = "influencer_db"


def read_sql(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_env(root_password: str) -> None:
    admin_password = secrets.token_urlsafe(12)
    secret_key = secrets.token_urlsafe(32)
    content = f"""DB_HOST=localhost
DB_PORT=3306
DB_USER={APP_USER}
DB_PASSWORD={APP_PASSWORD}
DB_NAME={DB_NAME}

MYSQL_ROOT_PASSWORD={root_password}

REDIS_URL=redis://localhost:6379/0
SECRET_KEY={secret_key}
DEBUG=true

ADMIN_USERNAME=admin
ADMIN_PASSWORD={admin_password}

LOGIN_RATE_LIMIT_MAX_ATTEMPTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Config written: {ENV_FILE}")
    print(f"  Admin login : admin / {admin_password}")
    print("  (请妥善保存上述密码，首次登录后建议修改)")


def load_root_password() -> str:
    env_password = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    if env_password:
        return env_password

    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                match = re.match(r"^MYSQL_ROOT_PASSWORD=(.*)$", line.strip())
                if match and match.group(1):
                    return match.group(1)

    return getpass.getpass("MySQL root password: ")


def main():
    print("=" * 50)
    print("  Influencer DB - Local MySQL Setup")
    print("=" * 50)

    password = load_root_password()

    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password=password,
            charset="utf8mb4",
            autocommit=True,
        )
    except pymysql.err.OperationalError as exc:
        print(f"\n[ERROR] Cannot connect to MySQL: {exc}")
        print("\nTip: set MYSQL_ROOT_PASSWORD in backend/.env then re-run")
        sys.exit(1)

    print("\nConnected. Initializing database influencer_db ...")

    sql = read_sql(SQL_FILE)
    with conn.cursor() as cursor:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            lines = [
                ln for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")
            ]
            if not lines:
                continue
            cursor.execute(stmt)

    conn.close()

    write_env(password)

    print("\n[SUCCESS] Database initialized!")
    print(f"  Database : {DB_NAME}")
    print(f"  App user : {APP_USER} / {APP_PASSWORD}")
    print(f"  Root pwd : saved to backend/.env (MYSQL_ROOT_PASSWORD)")
    print("\nNext step - start backend:")
    print("  cd backend")
    print("  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    main()
