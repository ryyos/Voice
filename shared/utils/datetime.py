"""
Date utility — date range parsing dengan berbagai format.

Mendukung:
  - Interval shorthand : "30d", "7d", "1m", "3m", "1y", "2w"
  - Explicit range     : "23/06/2026 - 23/07/2026"
  - Custom format      : Date.interval("30d", fmt="%Y-%m-%d")
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Tuple

from loguru import logger


class Time:
    """
    Time range parser.

    Usage
    -----
    >>> Time.interval("30d")
    ("24/05/2026", "23/06/2026")

    >>> Time.interval("1m")
    ("23/05/2026", "23/06/2026")

    >>> Time.interval("2y")
    ("23/06/2024", "23/06/2026")

    >>> Time.interval("23/06/2026 - 23/07/2026")
    ("23/06/2026", "23/07/2026")
    """

    DEFAULT_FMT: str = "%d/%m/%Y"

    # ── main API ──────────────────────────────────────────────────

    @staticmethod
    def interval(
        value: str,
        *,
        fmt: str = DEFAULT_FMT,
        today: datetime | None = None,
    ) -> Tuple[str, str]:
        """
        Parse interval string → (start_date, end_date) strings.

        Supported shorthands
        --------------------
        d — days   : "30d"  → 30 hari ke belakang
        w — weeks  : "2w"   → 2 minggu ke belakang
        m — months : "1m"   → 1 bulan ke belakang
        y — years  : "1y"   → 1 tahun ke belakang
        h — hours  : "24h"  → 24 jam ke belakang

        Explicit range
        --------------
        "01/06/2026 - 30/06/2026"  → date range eksplisit

        Parameters
        ----------
        value : str   — "30d", "1m", "2y", atau "dd/mm/yyyy - dd/mm/yyyy"
        fmt   : str   — output format (default dd/mm/yyyy)
        today : datetime | None — titik referensi (default sekarang)

        Returns
        -------
        (start, end) — tuple of formatted date strings
        """
        now = today or datetime.now()

        # Explicit range: "23/06/2026 - 23/07/2026"
        if " - " in value or " to " in value:
            return Time._parse_explicit(value, fmt)

        # Shorthand: "30d", "1m", "2y", "24h", "3w"
        match = re.match(r"^(\d+)\s*(d|w|m|y|h)$", value.strip().lower())
        if not match:
            logger.warning(
                f"[ DATE ] unknown interval format: '{value}'. "
                f"Falling back to 30d."
            )
            return Time.interval("30d", fmt=fmt, today=now)

        amount = int(match.group(1))
        unit = match.group(2)

        start = Time._subtract(now, amount, unit)
        return start.strftime(fmt), now.strftime(fmt)

    # ── raw datetime (kalau butuh object, bukan string) ────────────

    @staticmethod
    def interval_dt(
        value: str,
        *,
        today: datetime | None = None,
    ) -> Tuple[datetime, datetime]:
        """Same as .interval() but returns datetime objects."""
        now = today or datetime.now()

        if " - " in value or " to " in value:
            s, e = Time._parse_explicit(value, "%d/%m/%Y")
            return (
                datetime.strptime(s, "%d/%m/%Y"),
                datetime.strptime(e, "%d/%m/%Y"),
            )

        match = re.match(r"^(\d+)\s*(d|w|m|y|h)$", value.strip().lower())
        if not match:
            return Time.interval_dt("30d", today=now)

        amount = int(match.group(1))
        unit = match.group(2)
        start = Time._subtract(now, amount, unit)
        return start, now

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _subtract(dt: datetime, amount: int, unit: str) -> datetime:
        """Subtract amount * unit from dt."""
        if unit == "h":
            return dt - timedelta(hours=amount)
        elif unit == "d":
            return dt - timedelta(days=amount)
        elif unit == "w":
            return dt - timedelta(weeks=amount)
        elif unit == "m":
            return dt - relativedelta(months=amount)
        elif unit == "y":
            return dt - relativedelta(years=amount)
        return dt

    @staticmethod
    def _parse_explicit(value: str, fmt: str) -> Tuple[str, str]:
        """Parse "23/06/2026 - 23/07/2026" style date range."""
        sep = " - " if " - " in value else " to "
        parts = value.split(sep)
        if len(parts) != 2:
            logger.warning(f"[ DATE ] invalid explicit range: '{value}'")
            now = datetime.now()
            return now.strftime(fmt), now.strftime(fmt)

        start_str, end_str = parts[0].strip(), parts[1].strip()
        # Coba beberapa format umum
        for f in (fmt, "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                start_dt = datetime.strptime(start_str, f)
                end_dt = datetime.strptime(end_str, f)
                return start_dt.strftime(fmt), end_dt.strftime(fmt)
            except ValueError:
                continue

        logger.warning(f"[ DATE ] cannot parse explicit dates: '{value}'")
        now = datetime.now()
        return now.strftime(fmt), now.strftime(fmt)

    # ── convenience ────────────────────────────────────────────────

    @staticmethod
    def today(fmt: str = DEFAULT_FMT) -> str:
        """Return today's date string."""
        return datetime.now().strftime(fmt)

    @staticmethod
    def now_iso() -> str:
        """Return ISO 8601 timestamp (cocok untuk RawDocument.fetched_at dsb)."""
        return datetime.now().isoformat()

    @staticmethod
    def parse(date_str: str, fmt: str = DEFAULT_FMT) -> datetime:
        """Parse a date string → datetime object."""
        return datetime.strptime(date_str, fmt)

    @staticmethod
    def format(dt: datetime, fmt: str = DEFAULT_FMT) -> str:
        """Format a datetime → string."""
        return dt.strftime(fmt)
