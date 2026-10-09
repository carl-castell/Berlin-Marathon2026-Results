"""Gemeinsame Basisklasse für unsere Spider: Fortschritt zählen + Fehler behandeln.

Fortschritt wird über die Scrapy-Stats gezählt (ein Dictionary mit Zählern,
das jede Komponente lesen und schreiben kann):
    progress/total   wie viele Seiten insgesamt zu laden sind
    progress/done    erfolgreich verarbeitet
    progress/failed  endgültig fehlgeschlagen (nach allen Retries)
Die ProgressExtension (extensions.py) liest diese Werte und zeichnet daraus
den Fortschrittsbalken. Die Stats stehen am Ende auch im Log.
"""

import scrapy

from ..items import FailureItem


class ProgressSpider(scrapy.Spider):
    # Text vor dem Fortschrittsbalken
    progress_label = "Scraping"

    def add_total(self, n: int) -> None:
        self.crawler.stats.inc_value("progress/total", n)

    def mark_done(self) -> None:
        self.crawler.stats.inc_value("progress/done")

    def on_error(self, failure):
        """errback: wird aufgerufen, wenn ein Request endgültig scheitert.

        Das passiert z.B., wenn alle Retries aufgebraucht sind (Timeout,
        Verbindungsfehler) oder die Antwort einen Fehlerstatus (404, 500, ...)
        hat. Ohne errback würde Scrapy den Fehler nur loggen. Wir zählen ihn
        und speichern ihn in der Tabelle `failures`.
        """
        request = failure.request
        self.crawler.stats.inc_value("progress/failed")
        self.logger.warning(
            "Fehlgeschlagen: %s – %s", request.url, failure.getErrorMessage()[:200]
        )
        # Auch ein errback darf Items liefern. Dieses landet in der DB.
        yield FailureItem(
            url=request.url,
            spider=self.name,
            error=f"{failure.type.__name__}: {failure.getErrorMessage()}"[:500],
        )
