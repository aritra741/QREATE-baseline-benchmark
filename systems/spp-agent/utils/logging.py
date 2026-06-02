from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Iterator

from utils.config import load_config


def setup_logger(name: str, level: str | None = None) -> logging.Logger:
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    log_level = (level or os.environ.get("SPP_LOG_LEVEL") or log_cfg.get("level", "INFO")).upper()
    fmt = log_cfg.get(
        "format",
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    datefmt = log_cfg.get("datefmt", "%H:%M:%S")

    logger = logging.getLogger(name)
    if logger.handlers:
        logger.setLevel(log_level)
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(handler)
    logger.setLevel(log_level)
    logger.propagate = False
    return logger


@contextmanager
def log_step(logger: logging.Logger, label: str, **fields) -> Iterator[None]:
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    suffix = f" ({detail})" if detail else ""
    logger.info("START %s%s", label, suffix)
    started = time.perf_counter()
    try:
        yield
    except Exception:
        elapsed = time.perf_counter() - started
        logger.exception("FAIL  %s after %.2fs", label, elapsed)
        raise
    else:
        elapsed = time.perf_counter() - started
        logger.info("DONE  %s in %.2fs", label, elapsed)


def log_dict(logger: logging.Logger, prefix: str, data: dict, keys: list[str] | None = None) -> None:
    items = keys or list(data.keys())
    for key in items:
        if key in data:
            logger.info("%s %s=%s", prefix, key, data[key])
