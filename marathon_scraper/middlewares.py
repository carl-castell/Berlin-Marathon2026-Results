"""Downloader middleware: reacting to rate limiting / blocking.

What happens without this middleware?
Scrapy's RetryMiddleware retries a request on 429/503 up to RETRY_TIMES times,
and does so immediately. When the server says "too many requests", that tends
to make things worse. After that the request is dropped.

What does this middleware do?
When the server answers with a "slow down!" status (429 Too Many Requests,
503 Service Unavailable, 403 Forbidden), it
  1. pauses the WHOLE crawl (no new requests),
  2. waits, longer each time (exponential backoff: 30 s, 60 s, 120 s, ... up
     to 10 min). If the server sends a "Retry-After" header, it waits at least
     that long,
  3. reschedules the request afterwards, so nothing is lost,
  4. gives up after BACKOFF_MAX_STRIKES pauses in a row and closes the spider
     cleanly (reason "blocked"). Everything up to that point is saved in the
     DB; a later restart continues from there.
As soon as a normal response (200) arrives again, the counter is reset.

Where does it sit? Downloader middlewares form a chain between the engine and
the downloader. process_response runs from the highest number to the lowest.
With 560 we see the response BEFORE the RetryMiddleware (550), see settings.py.
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
        self.strikes = 0  # pauses in a row without a successful response in between
        self.resume_at = 0.0  # time.time() until which we pause
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
            raise IgnoreRequest(f"Spider is shutting down (HTTP {response.status})")

        stats = self.crawler.stats
        now = time.time()
        # Several parallel requests get a 429 at the same time. Only the FIRST
        # response of a wave counts as a new "strike"; the others wait along.
        if now >= self.resume_at:
            self.strikes += 1
            if self.strikes > self.max_strikes:
                self.gave_up = True
                logger.error(
                    "Server keeps blocking (HTTP %s) after %d pauses – closing the spider. "
                    "Just restart later; data saved so far is kept.",
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
                "HTTP %s – server is throttling us. Pausing %d s (pause %d of max. %d), then continuing.",
                response.status,
                wait,
                self.strikes,
                self.max_strikes,
            )

        # Pause the engine: no new requests are sent.
        self.crawler.engine.pause()
        await asyncio.sleep(max(0.0, self.resume_at - time.time()))
        self.crawler.engine.unpause()
        stats.set_value("backoff/resume_at", 0)

        # When a middleware returns a Request instead of a Response, Scrapy
        # schedules it again. dont_filter=True, otherwise the duplicate filter
        # considers it already done.
        stats.inc_value("backoff/requeued")
        return request.replace(dont_filter=True)

    @staticmethod
    def retry_after(response) -> float:
        """Header 'Retry-After: 120' -> 120.0 (we ignore the date format)."""
        value = response.headers.get(b"Retry-After")
        try:
            return float(value.decode()) if value else 0.0
        except ValueError:
            return 0.0
