"""Schritt 1: die Ergebnislisten (100 Läufer pro Seite, getrennt nach Geschlecht).

Geschlechter-Filter der Seite: M = Männer, W = Frauen, X = Divers.

Aufruf:
    uv run scrapy crawl results_list
    uv run scrapy crawl results_list -a sex=W -a max_pages=2   # zum Testen

Ablauf:
    start()  -> Seite 1 je Geschlecht anfragen
    parse()  -> Läufer der Seite als RunnerItem ausgeben
                (nur auf Seite 1) letzte Seitenzahl finden und alle weiteren
                Seiten auf einmal anfragen -> Scrapy lädt sie parallel.
"""

import re
from urllib.parse import parse_qs, urlparse

import scrapy
from scrapy.exceptions import CloseSpider

from ..items import RunnerItem
from ..site import clean, decode_silver, detail_url, list_url, to_int
from .base import ProgressSpider

# Jedes Feld enthält ein Label-<div class="list-label"> für die Handyansicht,
# z.B. <div>  <div class="list-label">Startnr.</div>6  </div>.
# Dieser XPath nimmt allen Text im Feld, AUSSER dem innerhalb des Labels.
VALUE_XPATH = ".//text()[not(ancestor::div[contains(@class, 'list-label')])]"


def field_value(el) -> str | None:
    return clean("".join(el.xpath(VALUE_XPATH).getall()))


# "Nachname, Vorname (NAT)": Nation = drei Großbuchstaben in Klammern am Ende.
NATION_RE = re.compile(r"\s*\(([A-Z]{3})\)$")


def split_name(full_name: str) -> tuple[str, str | None, str | None]:
    """'Adola, Guye (ETH)' -> ('Adola', 'Guye', 'ETH').

    Die Seite schreibt immer "Nachname, Vorname". Getrennt wird am ersten
    Komma, ohne Komma gilt alles als Nachname.
    """
    nation = None
    m = NATION_RE.search(full_name)
    if m:
        nation = m.group(1)
        full_name = full_name[: m.start()]
    last, sep, first = full_name.partition(",")
    return last.strip(), (first.strip() or None) if sep else None, nation


class ResultsListSpider(ProgressSpider):
    name = "results_list"
    progress_label = "Listen"
    allowed_domains = ["berlin.r.mikatiming.com"]

    def __init__(self, sex: str = "M,W,X", max_pages: str | None = None, **kwargs):
        # Argumente mit -a kommen immer als String an.
        super().__init__(**kwargs)
        self.sexes = [s.strip() for s in sex.split(",")]
        self.max_pages = int(max_pages) if max_pages else None

    async def start(self):
        # Seit Scrapy 2.13 ist `async def start()` der Einstieg (früher start_requests()).
        # Gesamtzahl der Seiten kennen wir erst nach Seite 1 -> erstmal nur diese zählen.
        self.add_total(len(self.sexes))
        for sex in self.sexes:
            # cb_kwargs: zusätzliche Argumente, die an den Callback übergeben werden.
            # So weiß parse(), zu welchem Geschlecht/welcher Seite die Antwort gehört.
            yield scrapy.Request(
                list_url(sex, 1),
                callback=self.parse,
                errback=self.on_error,
                cb_kwargs={"sex": sex, "page": 1},
            )

    def parse(self, response, sex: str, page: int):
        # Sicherheitscheck: Unbekannte Filterwerte ignoriert die Seite stillschweigend
        # und zeigt dann die Männer (getestet mit "D"). Die Seite schreibt den
        # tatsächlich aktiven Filter in <div data-sex="...">.
        active = response.css("[data-sex]::attr(data-sex)").get()
        if active != sex:
            raise CloseSpider(f"Filter sex={sex} wirkt nicht (Seite zeigt data-sex={active!r})")

        rows = response.css("li.list-group-item.row:not(.list-group-header)")
        self.logger.debug("%s Seite %d: %d Läufer", sex, page, len(rows))

        for row in rows:
            yield self.parse_row(row, response, sex, page)

        if page == 1:
            last = self.last_page(response)
            if self.max_pages:
                last = min(last, self.max_pages)
            self.logger.info("%s: %d Seiten insgesamt", sex, last)
            self.add_total(last - 1)
            for p in range(2, last + 1):
                yield scrapy.Request(
                    list_url(sex, p),
                    callback=self.parse,
                    errback=self.on_error,
                    cb_kwargs={"sex": sex, "page": p},
                )

        self.mark_done()

    def parse_row(self, row, response, sex: str, page: int) -> RunnerItem:
        # Name-Link: "Adola, Guye (ETH)" mit href="?content=detail&...&idp=..."
        link = row.css("h4.type-fullname a")
        full_name = clean(link.css("::text").get())
        href = link.attrib["href"]
        idp = parse_qs(urlparse(href).query)["idp"][0]

        last_name, first_name, nation = split_name(full_name or "")

        # Rechte Spalten, in fester Reihenfolge:
        #   .pull-left:  Startnr. | AK | Verein
        #   .pull-right: Brutto | Netto | (Favoriten-Icon)
        left = [field_value(el) for el in row.css(".pull-left .list-field")]
        times = [field_value(el) for el in row.css(".pull-right .type-time")]
        bib, age_class, club = (left + [None] * 3)[:3]

        return RunnerItem(
            idp=idp,
            sex=sex,
            place_overall=to_int(row.css(".place-primary::text").get()),
            place_ak=to_int(row.css(".place-secondary::text").get()),
            last_name=last_name,
            first_name=first_name,
            nation=nation,
            bib=bib,
            age_class=age_class,
            club=club,
            time_brutto=times[0] if len(times) > 0 else None,
            time_netto=times[1] if len(times) > 1 else None,
            detail_url=detail_url(idp),
            list_page=page,
        )

    def last_page(self, response) -> int:
        """Höchste Seitenzahl aus den (kodierten) Pagination-Links lesen."""
        pages = [1]
        for code in response.css("ul.pagination a::attr(data-silver)").getall():
            m = re.search(r"[?&]page=(\d+)", decode_silver(code))
            if m:
                pages.append(int(m.group(1)))
        return max(pages)
