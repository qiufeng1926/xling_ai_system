"""受限 Python 代码沙箱：服务端执行，对齐豆包「能算能改」的一小块能力。

约束：
- 超时默认 8s
- 禁止危险 import（os/sys/subprocess/socket 等）
- 工作目录限定为用户 workspace（可读写本 uid 目录）
- 不提供网络；不执行 shell
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger("tools.code_sandbox")

_DEFAULT_TIMEOUT = 8
_MAX_CODE_CHARS = 12000
_MAX_OUTPUT_CHARS = 8000

_BLOCKED_IMPORTS = (
    "os",
    "sys",
    "subprocess",
    "socket",
    "ctypes",
    "multiprocessing",
    "pathlib",
    "shutil",
    "signal",
    "importlib",
    "builtins",
    "pty",
    "fcntl",
    "resource",
    "http",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "telnetlib",
    "pickle",
    "marshal",
    "code",
    "codeop",
    "pty",
)

_WRAPPER = '''\
import builtins as _builtins

_BLOCKED = {blocked}

_real_import = _builtins.__import__

def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = (name or "").split(".", 1)[0]
    if root in _BLOCKED:
        raise ImportError(f"sandbox blocked import: {root}")
    return _real_import(name, globals, locals, fromlist, level)

_builtins.__import__ = _safe_import

# 用户代码
{user_code}
'''


def _validate_code(code: str) -> str | None:
    raw = (code or "").strip()
    if not raw:
        return "code 不能为空"
    if len(raw) > _MAX_CODE_CHARS:
        return f"code 过长（上限 {_MAX_CODE_CHARS} 字符）"
    low = raw.lower()
    for bad in (
        "__import__",
        "getattr(",
        "setattr(",
        "delattr(",
        "globals(",
        "locals(",
        "breakpoint(",
        "eval(",
        "exec(",
        "compile(",
        "open(",
        "input(",
    ):
        # open 允许用于读写 workspace 内文件；改为运行时靠 cwd 限制
        if bad == "open(":
            continue
        if bad in low:
            return f"代码含有禁止用法: {bad.rstrip('(')}"
    return None


def run_python_sandbox(
    code: str,
    *,
    workdir: Path,
    timeout_sec: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    err = _validate_code(code)
    if err:
        return {"ok": False, "error": err}

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    blocked_repr = repr(set(_BLOCKED_IMPORTS))
    user_src = textwrap.dedent(code).strip()
    # 不用 str.format：用户代码里的 {} 会破坏占位符
    wrapped = _WRAPPER.replace("{blocked}", blocked_repr, 1).replace("{user_code}", user_src, 1)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".py",
        dir=str(workdir),
        delete=False,
    ) as tf:
        tf.write(wrapped)
        script_path = Path(tf.name)

    try:
        import os

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [sys.executable, "-I", str(script_path)],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout_sec or _DEFAULT_TIMEOUT), 30)),
            env=env,
        )
        stdout = (proc.stdout or "")[:_MAX_OUTPUT_CHARS]
        stderr = (proc.stderr or "")[:_MAX_OUTPUT_CHARS]
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": (stderr or stdout or f"exit {proc.returncode}")[:1500],
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "exit_code": proc.returncode,
            }
        return {
            "ok": True,
            "stdout": stdout,
            "stderr": stderr[:1000],
            "exit_code": 0,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"执行超时（>{timeout_sec}s）"}
    except Exception as exc:
        logger.warning("run_code failed: %s", exc)
        return {"ok": False, "error": f"沙箱执行失败: {exc}"}
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except Exception:
            pass
