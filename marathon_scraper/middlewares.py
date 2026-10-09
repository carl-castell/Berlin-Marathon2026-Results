"""Downloader-Middleware: Reaktion auf Rate-Limiting / Blockieren.

Was passiert ohne diese Middleware?
Scrapys RetryMiddleware versucht einen Request bei 429/503 bis zu RETRY_TIMES
mal erneut, und zwar sofort. Wenn der Server sagt „zu viele Anfragen“, wird es
dadurch eher schlimmer. Danach wird der Request verworfen.

Was macht diese Middleware?
Antwortet der Server mit einem „Bremse!“-Status (429 Too Many Requests,
503 Service Unavailable, 403 Forbidden), dann
  1. pausiert sie den GANZEN Crawl (keine neuen Requests),
  2. wartet, und zwar jedes Mal länger (exponential backoff: 30 s, 60 s,
     120 s, ... bis max. 10 min). Schickt der Server einen „Retry-After“-Header,
     wird mindestens so lange gewartet,
  3. plant den Request danach neu ein. Es geht also nichts verloren,
  4. gibt nach BACKOFF_MAX_STRIKES Pausen in Folge auf und beendet den Spider
     sauber (Grund „blocked“). Alles bis dahin ist in der DB gespeichert, ein
     Neustart später macht dort weiter.
Kommt wieder eine normale Antwort (200), wird der Zähler zurückgesetzt.

Wo sitzt sie? Downloader-Middlewares bilden eine Kette zwischen Engine und
Downloader. process_response läuft von der höchsten Zahl zur niedrigsten.
Mit 560 sehen wir die Antwort VOR der RetryMiddleware (550), siehe settings.py.
"""

import asyncio
import logging
import time

from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


class BackoffMiddleware:
    def __init__(self, crawler):
        self.crawler = crawler
        s = crawler.settings
        self.codes = {int(c) for c in s.getlist("BACKOFF_HTTP_CODES", [429, 503, 403])}
        self.base = s.getfloat("BACKOFF_BASE_SECONDS", 30)
        self.max_wait = s.getfloat("BACKOFF_MAX_SECONDS", 600)
        self.max_strikes = s.getint("BACKOFF_MAX_STRIKES", 6)
        self.strikes = 0  # Pausen in Folge ohne erfolgreiche Antwort dazwischen
        self.resume_at = 0.0  # time.time(), bis wann pausiert wird
        self.gave_up = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_response(self, request, response, spider=None):
        if response.status not in self.codes:
            if response.status == 200:
                self.strikes = 0
            return response

        if self.gave_up:
            raise IgnoreRequest(f"Spider wird beendet (HTTP {response.status})")

        stats = self.crawler.stats
        now = time.time()
        # Mehrere parallele Requests bekommen gleichzeitig 429. Nur die ERSTE
        # Antwort einer Welle zählt als neuer "Strike", die anderen warten mit.
        if now >= self.resume_at:
            self.strikes += 1
            if self.strikes > self.max_strikes:
                self.gave_up = True
                logger.error(
                    "Server blockiert weiterhin (HTTP %s) nach %d Pausen – Spider wird beendet. "
                    "Später einfach neu starten, bereits gespeicherte Daten bleiben erhalten.",
                    response.status,
                    self.max_strikes,
                )
                asyncio.ensure_future(self.crawler.engine.close_spider_async(reason="blocked"))
                raise IgnoreRequest(f"blocked (HTTP {response.status})")

            wait = min(self.base * 2 ** (self.strikes - 1), self.max_wait)
            wait = max(wait, self.retry_after(response))
            self.resume_at = now + wait
            stats.inc_value("backoff/count")
            stats.set_value("backoff/resume_at", self.resume_at)
            logger.warning(
                "HTTP %s – Server bremst. Pause %d s (Pause %d von max. %d), danach geht es weiter.",
                response.status,
                wait,
                self.strikes,
                self.max_strikes,
            )

        # Engine pausieren: es werden keine neuen Requests mehr losgeschickt.
        self.crawler.engine.pause()
        await asyncio.sleep(max(0.0, self.resume_at - time.time()))
        self.crawler.engine.unpause()
        stats.set_value("backoff/resume_at", 0)

        # Gibt eine Middleware einen Request statt einer Response zurück, plant
        # Scrapy ihn neu ein. dont_filter=True, sonst hält der Duplikatfilter
        # ihn für schon erledigt.
        stats.inc_value("backoff/requeued")
        return request.replace(dont_filter=True)

    @staticmethod
    def retry_after(response) -> float:
        """Header 'Retry-After: 120' -> 120.0 (Datumsformat ignorieren wir)."""
        value = response.headers.get(b"Retry-After")
        try:
            return float(value.decode()) if value else 0.0
        except ValueError:
            return 0.0
