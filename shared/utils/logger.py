from __future__ import annotations

import sys
import threading
from pathlib import Path

from loguru import logger as _logger

class _LineRotatingSink:

    def __init__(
        self,
        path: str | Path,
        max_lines: int = 1000,
        check_every: int = 10,
    ) -> None:
        self.path = Path(path)
        self.max_lines = max_lines
        self.check_every = check_every
        self._write_count = 0
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def write(self, message: str) -> None:
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(message)

            self._write_count += 1
            if self._write_count >= self.check_every:
                self._write_count = 0
                self._trim()

    def _trim(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) > self.max_lines:
                excess = len(lines) - self.max_lines
                lines = lines[excess:]
                with open(self.path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
        except Exception:
            pass


# ── setup logger ─────────────────────────────────────────────────────────

LOG_PATH = Path("logs/app.log")
LOG_FORMAT = (
    "<green>{time:DD/MM/YYYY HH:mm:ss}</green> | "
    "<level>{level:<8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
    "<level>{message}</level>"
)
FILE_FORMAT = (
    "{time:DD/MM/YYYY HH:mm:ss} | "
    "{level:<8} | "
    "{name}:{line} — "
    "{message}"
)

# Hapus handler default loguru supaya tidak dobel dengan stdlib logging
_logger.remove()

# Console — colorized
_logger.add(
    sys.stderr,
    format=LOG_FORMAT,
    level="DEBUG",
    colorize=True,
)

# File — line-rotating, max 1000 baris
_logger.add(
    _LineRotatingSink(LOG_PATH, max_lines=1000, check_every=10),
    format=FILE_FORMAT,
    level="DEBUG",
)

# ── public instance ───────────────────────────────────────────────────────

log = _logger
