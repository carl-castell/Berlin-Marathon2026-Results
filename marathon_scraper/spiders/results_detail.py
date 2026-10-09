"""Schritt 2: Detailseite für jeden Läufer aus Schritt 1.

Aufruf:
    uv run scrapy crawl results_detail                 # alle, die noch fehlen
    uv run scrapy crawl results_detail -a limit=20     # zum Testen

Der Spider liest die Läufer aus der Tabelle `runners` und fragt nur die an,
für die es noch keine Zeile in `details` gibt. Bricht man ab (Ctrl-C) und
startet neu, macht er also einfach dort weiter, wo er aufgehört hat.

Die Detailseite hat für jede Tabellenzeile eine CSS-Klasse mit dem internen
Feldnamen, z.B. <td class="f-place_all">. Diese Klassen sind unabhängig von
der Sprache -> sehr robuste Selektoren.
"""

import sqlite3

import scrapy

from ..items import DetailItem, SplitItem
from ..site import clean, detail_url, to_float, to_int
from .base import ProgressSpider


class ResultsDetailSpider(ProgressSpider):
    name = "results_detail"
    progress_label = "Details"
    allowed_domains = ["berlin.r.mikatiming.com"]

    def __init__(self, limit: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.limit = int(limit) if limit else None

    async def start(self):
        db_path = self.settings.get("SQLITE_PATH")
        sql = """
            SELECT r.idp FROM runners r
            LEFT JOIN details d USING (idp)
            WHERE d.idp IS NULL
            ORDER BY r.sex, r.place_overall
        """
        if self.limit:
            sql += f" LIMIT {self.limit}"
        try:
            with sqlite3.connect(db_path) as conn:
                idps = [row[0] for row in conn.execute(sql)]
        except sqlite3.OperationalError:
            self.logger.error("Keine Tabelle 'runners' - zuerst `scrapy crawl results_list` ausführen.")
            return

        self.logger.info("%d Detailseiten zu laden", len(idps))
        self.add_total(len(idps))
        for idp in idps:
            yield scrapy.Request(
                detail_url(idp),
                callback=self.parse,
                errback=self.on_error,
                cb_kwargs={"idp": idp},
            )

    def parse(self, response, idp: str):
        def f(field: str) -> str | None:
            """Wert aus <td class="f-<field>"> in den Info-Tabellen."""
            return clean(" ".join(response.css(f"td.f-{field} ::text").getall()))

        # Halbmarathon-Zeilen in "Race Info": <tr class="f-time_21"> (HM 1) und
        # <tr class="f-time_59"> (HM 2), jeweils mit Zeit und Platz.
        def hm(field: str) -> tuple[str | None, int | None]:
            tr = response.css(f"#detail-box-other tr.f-{field}")
            tds = tr.css("td")
            if len(tds) < 2:
                return None, None
            return clean(tds[0].css("::text").get()), to_int(tds[1].css("::text").get())

        hm1_time, hm1_place = hm("time_21")
        hm2_time, hm2_place = hm("time_59")

        yield DetailItem(
            idp=idp,
            status=f("race_status_string"),
            last_split=f("__last_split_name"),
            place_sex=to_int(f("place_all")),
            place_ak=to_int(f("place_age")),
            place_total=to_int(f("place_nosex")),
            time_netto=f("time_finish_netto"),
            time_brutto=f("time_finish_brutto"),
            start_time_netto=f("starttime_net"),
            start_time_brutto=f("starttime"),
            hm1_time=hm1_time,
            hm1_place=hm1_place,
            hm2_time=hm2_time,
            hm2_place=hm2_place,
        )

        # Splits-Tabelle: eine Zeile pro Messpunkt (5 km, 10 km, ..., Finish).
        for seq, tr in enumerate(response.css("#detail-box-splits tbody tr")):
            # Klasse z.B. "list-highlight f-time_10" -> Schlüssel "time_10"
            classes = (tr.attrib.get("class") or "").split()
            key = next((c[2:] for c in classes if c.startswith("f-")), f"row_{seq}")

            def cell(cls: str) -> str | None:
                return clean(tr.css(f"td.{cls}::text").get())

            yield SplitItem(
                idp=idp,
                split_key=key,
                split_name=clean(tr.css("th::text").get()),
                seq=seq,
                time_of_day=cell("time_day"),
                time=cell("time"),
                diff=cell("diff"),
                pace_min_km=cell("min_km"),
                kmh=to_float(cell("kmh")),
            )

        self.mark_done()
