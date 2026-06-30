from __future__ import annotations

from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.console import Group
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from shared.utils.logger import shared_console


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        transient=False,
    )


class ProcessMonitor:
    """
    Tracks and displays pipeline progress for two stages: detail crawling and comment fetching.

    During Live:
      - Console log threshold raised to WARNING (INFO/DEBUG go to file only).
      - This keeps the terminal clean — progress bars re-render only on rare WARNING events.

    split=True  → two Rich panels (Detail + Comment) stacked vertically.
    split=False → one unified panel (default, via LOG_SPLIT env var).

    Usage:
        with ProcessMonitor(split=settings.log_split) as monitor:
            task_id = monitor.add_detail_task("[detik] articles", total=15)
            monitor.advance_detail(task_id)
    """

    def __init__(self, split: bool = False) -> None:
        self._split = split
        self._detail = _make_progress()
        self._comment = _make_progress()
        self._unified = _make_progress() if not split else None
        self._live: Live | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "ProcessMonitor":
        if self._split:
            renderable = Group(
                Panel(
                    self._detail,
                    title="[bold blue]Detail Crawling",
                    border_style="blue",
                ),
                Panel(
                    self._comment,
                    title="[bold green]Comment Fetching",
                    border_style="green",
                ),
            )
        else:
            renderable = Panel(
                self._unified,
                title="[bold cyan]Voice Pipeline",
                border_style="cyan",
            )

        self._live = Live(renderable, console=shared_console, refresh_per_second=4)
        self._live.start()
        return self

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    def __enter__(self) -> "ProcessMonitor":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Detail stage
    # ------------------------------------------------------------------

    def add_detail_task(self, description: str, total: int = 0) -> int:
        p = self._detail if self._split else self._unified
        return p.add_task(f"[blue]{escape(description)}", total=total)

    def advance_detail(self, task_id: int, advance: int = 1) -> None:
        p = self._detail if self._split else self._unified
        p.advance(task_id, advance)

    def update_detail(self, task_id: int, **kwargs) -> None:
        p = self._detail if self._split else self._unified
        p.update(task_id, **kwargs)

    # ------------------------------------------------------------------
    # Comment stage
    # ------------------------------------------------------------------

    def add_comment_task(self, description: str, total: int = 0) -> int:
        p = self._comment if self._split else self._unified
        return p.add_task(f"[green]{escape(description)}", total=total)

    def advance_comment(self, task_id: int, advance: int = 1) -> None:
        p = self._comment if self._split else self._unified
        p.advance(task_id, advance)

    def update_comment(self, task_id: int, **kwargs) -> None:
        p = self._comment if self._split else self._unified
        p.update(task_id, **kwargs)
