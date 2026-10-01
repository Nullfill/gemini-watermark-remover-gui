"""
Application Logging Facility.
Logs simultaneously to rotating log file and console.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from core.config import LOGS_DIR

_logger: logging.Logger = None


def setup_logger(name: str = "WatermarkRemover") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(module)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Reconfigure sys.stdout encoding for Windows if possible
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler
    try:
        log_file = LOGS_DIR / "app.log"
        fh = RotatingFileHandler(str(log_file), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: could not initialize file logger: {e}", file=sys.stderr)

    _logger = logger
    return _logger


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        return setup_logger()
    return _logger
