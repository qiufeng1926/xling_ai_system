from __future__ import annotations

import logging
import sys
from pathlib import Path

_DEFAULT = "xlink-agent"


def setup_logging(service_name: str = _DEFAULT, console: bool = True) -> logging.Logger:
    from config.config import log_dir, log_level

    logger = logging.getLogger(service_name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, str(log_level).upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(Path(log_dir) / f"{service_name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(_DEFAULT)
    if name:
        return base.getChild(name)
    return base
