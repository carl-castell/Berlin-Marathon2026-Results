"""Shared base class for our spiders: count progress + handle errors.

Progress is counted via the Scrapy stats (a dictionary of counters that every
component can read and write):
    progress/total   how many pages there are to load in total
    progress/done    processed successfully
    progress/failed  failed for good (after all retries)
The ProgressExtension (extensions.py) reads these values and draws the
progress bar from them. The stats also appear in the log at the end.
"""

import scrapy

from ..items import FailureItem


class ProgressSpider(scrapy.Spider):
    # Text shown in front of the progress bar
    progress_label = "Scraping"

    def add_total(self, n: int) -> None:
        self.crawler.stats.inc_value("progress/total", n)

    def mark_done(self) -> None:
        self.crawler.stats.inc_value("progress/done")

    def on_error(self, failure):
        """errback: called when a request fails for good.

        That happens e.g. when all retries are used up (timeout, connection
        error) or the response has an error status (404, 500, ...). Without an
        errback Scrapy would only log the error. We count it and store it in
        the `failures` table.
        """
        request = failure.request
        self.crawler.stats.inc_value("progress/failed")
        self.logger.warning(
            "Failed: %s – %s", request.url, failure.getErrorMessage()[:200]
        )
        # An errback may yield items too. This one ends up in the DB.
        yield FailureItem(
            url=request.url,
            spider=self.name,
            error=f"{failure.type.__name__}: {failure.getErrorMessage()}"[:500],
        )
