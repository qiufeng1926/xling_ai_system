"""读写项目根目录 .env 文件中的配置项。"""
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = _PROJECT_ROOT / ".env"


def update_env_value(key: str, value: str) -> None:
    """更新或追加 .env 中的 KEY=VALUE，保留其余行不变。"""
    key = key.strip()
    if not key:
        raise ValueError("环境变量名不能为空")

    lines: list[str] = []
    if ENV_FILE_PATH.exists():
        lines = ENV_FILE_PATH.read_text(encoding="utf-8").splitlines()

    prefix = f"{key}="
    found = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or (
            stripped
            and not stripped.startswith("#")
            and stripped.split("=", 1)[0].strip() == key
        ):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")

    ENV_FILE_PATH.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
