"""Extension: progress display in the console (using `rich`).

Extensions are Scrapy components that react to signals (spider_opened,
spider_closed, item_scraped, ...). This one
  - shows a live progress bar with percentage, elapsed time, estimated time
    remaining, pages/second, failures and backoff pauses,
  - routes warnings and errors to the console (above the bar); everything
    else goes to the log file (LOG_FILE in settings.py),
  - prints a summary at the end.

The numbers come from the stats (progress/total, progress/done, ...), which
the spiders increment themselves, see spiders/base.py.

Disable with:  -s PROGRESS_ENABLED=False
"""

import asyncio
import logging
import time
from datetime import timedelta

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Table
from scrapy import signals
from scrapy.exceptions import NotConfigured

# These loggers may also write INFO messages to the console
# (e.g. "Received SIGINT, shutting down gracefully" from scrapy.crawler).
CONSOLE_INFO_LOGGERS = ("scrapy.crawler", "results_list", "results_detail", "marathon_scraper")


class ConsoleFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING or record.name.startswith(CONSOLE_INFO_LOGGERS)


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "–:––:––"
    return str(timedelta(seconds=int(seconds)))


class ProgressExtension:
    REFRESH_SECONDS = 0.5
    RATE_WINDOW_SECONDS = 60  # rate over the last minute -> stable time estimate

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.console = Console(stderr=True)
        self.progress: Progress | None = None
        self.task_id = None
        self.handler: RichHandler | None = None
        self.started = 0.0
        self.samples: list[tuple[float, int]] = []  # (time, finished) for the rate
        self.loop_task: asyncio.Task | None = None

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("PROGRESS_ENABLED", True):
            raise NotConfigured
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    # --- Signals ---------------------------------------------------------------

    def spider_opened(self, spider):
        self.started = time.time()
        self.progress = Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(),
            TextColumn("{task.fields[counts]}"),
            TextColumn("[cyan]⏱ {task.fields[elapsed]}"),
            TextColumn("[magenta]⏳ {task.fields[eta]}"),
            TextColumn("{task.fields[rate]}"),
            TextColumn("{task.fields[status]}"),
            console=self.console,
            refresh_per_second=4,
            expand=True,
        )
        label = getattr(spider, "progress_label", spider.name)
        self.task_id = self.progress.add_task(
            label, total=None, counts="", elapsed="", eta="", rate="", status=""
        )
        self.progress.start()

        # Print warnings/errors through rich so they appear above the bar
        # instead of breaking it.
        self.handler = RichHandler(console=self.console, show_path=False, markup=False)
        self.handler.setLevel(logging.INFO)
        self.handler.addFilter(ConsoleFilter())
        logging.getLogger().addHandler(self.handler)

        log_file = self.crawler.settings.get("LOG_FILE")
        if log_file:
            self.console.print(f"[dim]Detailed log: {log_file}  ·  Stop: Ctrl-C (once = clean shutdown)[/dim]")

        self.loop_task = asyncio.ensure_future(self.refresh_loop())

    def spider_closed(self, spider, reason):
        if self.loop_task:
            self.loop_task.cancel()
        self.refresh()
        if self.progress:
            self.progress.stop()
        if self.handler:
            logging.getLogger().removeHandler(self.handler)
        self.print_summary(reason)

    # --- Display -----------------------------------------------------------------

    async def refresh_loop(self):
        while True:
            self.refresh()
            await asyncio.sleep(self.REFRESH_SECONDS)

    def refresh(self):
        if not self.progress:
            return
        now = time.time()
        total = self.stats.get_value("progress/total", 0)
        done = self.stats.get_value("progress/done", 0)
        failed = self.stats.get_value("progress/failed", 0)
        finished = done + failed

        # Compute the rate over a sliding time window
        self.samples.append((now, finished))
        while len(self.samples) > 2 and now - self.samples[0][0] > self.RATE_WINDOW_SECONDS:
            self.samples.pop(0)
        t0, n0 = self.samples[0]
        rate = (finished - n0) / (now - t0) if now - t0 >= 2 else None

        eta = (total - finished) / rate if rate and total else None

        resume_at = self.stats.get_value("backoff/resume_at", 0)
        backoffs = self.stats.get_value("backoff/count", 0)
        if resume_at and resume_at > now:
            status = f"[yellow]⏸ paused (rate limit), {int(resume_at - now)} s left"
        else:
            parts = []
            if failed:
                parts.append(f"[red]✗ {failed} failed")
            if backoffs:
                parts.append(f"[yellow]throttled {backoffs}×")
            status = "  ".join(parts) or "[green]✓"

        self.progress.update(
            self.task_id,
            total=total or None,
            completed=finished,
            counts=f"{finished:,}/{total:,}",
            elapsed=fmt_duration(now - self.started),
            eta=fmt_duration(eta),
            rate=f"{rate:.1f}/s" if rate is not None else "…/s",
            status=status,
        )

    def print_summary(self, reason: str):
        s = self.stats
        total = s.get_value("progress/total", 0)
        done = s.get_value("progress/done", 0)
        failed = s.get_value("progress/failed", 0)
        elapsed = time.time() - self.started

        reasons = {
            "finished": "[green]finished",
            "shutdown": "[yellow]stopped (Ctrl-C) – restarting continues where it left off",
            "blocked": "[red]blocked by the server – restart later",
        }
        t = Table(title="Summary", show_header=False, title_justify="left")
        t.add_row("End", reasons.get(reason, reason))
        t.add_row("Duration", fmt_duration(elapsed))
        t.add_row("Pages done", f"{done:,} of {total:,}")
        t.add_row("Failed", f"[red]{failed}" if failed else "0")
        t.add_row("Items saved", str(s.get_value("item_scraped_count", 0)))
        t.add_row("From cache", str(s.get_value("httpcache/hit", 0)))
        t.add_row("Retries", str(s.get_value("retry/count", 0)))
        t.add_row("Rate-limit pauses", str(s.get_value("backoff/count", 0)))
        unknown = s.get_value("countries/unknown_codes")
        if unknown:
            t.add_row("Unknown countries", f"[yellow]{unknown}")
        self.console.print(t)
        if failed:
            self.console.print(
                "[dim]Failed URLs: sqlite3 data/marathon.db 'select * from failures'[/dim]"
            )
