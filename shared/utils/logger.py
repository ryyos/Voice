from __future__ import annotations

import logging
import threading
from pathlib import Path

from loguru import logger as _logger
from rich.console import Console


# ── shared Rich console ───────────────────────────────────────────────────
shared_console = Console(stderr=True)


# ── stdlib → loguru bridge ────────────────────────────────────────────────
# Routes ALL stdlib logging (httpx, httpcore, kafka-python, etc.) through
# loguru, so a single suppress call silences every log source at once.
class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        _logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)


# ── file sink ─────────────────────────────────────────────────────────────
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

_logger.remove()


def _console_sink(message: str) -> None:
    shared_console.print(message, end="", markup=False, highlight=False)


_console_sink_id: int = _logger.add(
    _console_sink,
    format=LOG_FORMAT,
    level="DEBUG",
    colorize=True,
)

_logger.add(
    _LineRotatingSink(LOG_PATH, max_lines=1000, check_every=10),
    format=FILE_FORMAT,
    level="DEBUG",
)


# ── console level control (used by ProcessMonitor) ────────────────────────

def suppress_console() -> None:
    """Raise console threshold to WARNING while Live is active.
    INFO/DEBUG still go to file. WARNING+ still visible on terminal."""
    global _console_sink_id
    _logger.remove(_console_sink_id)
    _console_sink_id = _logger.add(
        _console_sink,
        format=LOG_FORMAT,
        level="WARNING",
        colorize=True,
    )


def restore_console() -> None:
    """Restore full DEBUG logging after Live stops."""
    global _console_sink_id
    _logger.remove(_console_sink_id)
    _console_sink_id = _logger.add(
        _console_sink,
        format=LOG_FORMAT,
        level="DEBUG",
        colorize=True,
    )


# ── public instance ───────────────────────────────────────────────────────

log = _logger
