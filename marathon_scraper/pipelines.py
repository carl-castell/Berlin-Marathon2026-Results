"""Item-Pipeline: schreibt alle Items in eine SQLite-Datenbank.

Warum SQLite statt CSV?
- Mehrere Tabellen (runners, details, splits), die man per SQL joinen kann.
- UPSERT ("insert or update"): Läuft ein Spider zweimal, entstehen keine
  Duplikate, vorhandene Zeilen werden einfach aktualisiert.
- Der Detail-Spider kann per SQL abfragen, was noch fehlt -> fortsetzbar.
- Polars liest SQLite direkt (pl.read_database).

Lebenszyklus einer Pipeline in Scrapy:
  open_spider()   -> einmal beim Start   (DB öffnen, Tabellen anlegen)
  process_item()  -> für jedes Item       (Zeile schreiben)
  close_spider()  -> einmal am Ende       (commit, DB schließen)
"""

import sqlite3
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .items import DetailItem, FailureItem, RunnerItem, SplitItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS runners (
    idp           TEXT PRIMARY KEY,
    sex           TEXT,
    place_overall INTEGER,
    place_ak      INTEGER,
    last_name     TEXT,
    first_name    TEXT,
    nation        TEXT,
    bib           TEXT,
    age_class     TEXT,
    club          TEXT,
    time_brutto   TEXT,
    time_netto    TEXT,
    detail_url    TEXT,
    list_page     INTEGER,
    scraped_at    TEXT
);

CREATE TABLE IF NOT EXISTS details (
    idp               TEXT PRIMARY KEY REFERENCES runners(idp),
    status            TEXT,
    last_split        TEXT,
    place_sex         INTEGER,
    place_ak          INTEGER,
    place_total       INTEGER,
    time_netto        TEXT,
    time_brutto       TEXT,
    start_time_netto  TEXT,
    start_time_brutto TEXT,
    hm1_time          TEXT,
    hm1_place         INTEGER,
    hm2_time          TEXT,
    hm2_place         INTEGER,
    scraped_at        TEXT
);

CREATE TABLE IF NOT EXISTS splits (
    idp         TEXT REFERENCES runners(idp),
    split_key   TEXT,
    split_name  TEXT,
    seq         INTEGER,
    time_of_day TEXT,
    time        TEXT,
    diff        TEXT,
    pace_min_km TEXT,
    kmh         REAL,
    scraped_at  TEXT,
    PRIMARY KEY (idp, split_key)
);

-- Requests, die im LETZTEN Lauf des jeweiligen Spiders endgültig gescheitert sind.
CREATE TABLE IF NOT EXISTS failures (
    url        TEXT PRIMARY KEY,
    spider     TEXT,
    error      TEXT,
    scraped_at TEXT
);
"""

# Welche Item-Klasse in welche Tabelle gehört und was der Primärschlüssel ist.
TABLES = {
    RunnerItem: ("runners", ["idp"]),
    DetailItem: ("details", ["idp"]),
    SplitItem: ("splits", ["idp", "split_key"]),
    FailureItem: ("failures", ["url"]),
}


def upsert_sql(table: str, columns: list[str], key: list[str]) -> str:
    """Baut ein 'INSERT ... ON CONFLICT DO UPDATE' für die Tabelle.

    Beispiel-Ergebnis:
      INSERT INTO runners (idp, name, ...) VALUES (:idp, :name, ...)
      ON CONFLICT (idp) DO UPDATE SET name = excluded.name, ...
    """
    cols = ", ".join(columns)
    params = ", ".join(f":{c}" for c in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in key)
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({params}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
    )


class SQLitePipeline:
    # Alle N Items committen. Ein Commit pro Item wäre sehr langsam,
    # gar kein Commit bis zum Ende riskiert Datenverlust bei einem Absturz.
    COMMIT_EVERY = 500

    def __init__(self, db_path: str, crawler=None):
        self.db_path = db_path
        self.crawler = crawler
        self.conn: sqlite3.Connection | None = None
        self.pending = 0
        # SQL-Statements einmal vorbereiten, statt für jedes Item neu zu bauen.
        self.statements = {
            cls: upsert_sql(table, [f.name for f in fields(cls)] + ["scraped_at"], key)
            for cls, (table, key) in TABLES.items()
        }

    @classmethod
    def from_crawler(cls, crawler):
        # So kommt eine Pipeline an die Settings: Scrapy ruft from_crawler auf
        # und übergibt den Crawler, der alle Einstellungen kennt.
        return cls(db_path=crawler.settings.get("SQLITE_PATH"), crawler=crawler)

    def open_spider(self, spider=None):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        # WAL erlaubt es, die DB (z.B. im Notebook) zu lesen, während gescrapt wird.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        # Alte Fehler dieses Spiders vergessen: Was diesmal wieder scheitert,
        # landet neu in der Tabelle. (Der Detail-Spider holt fehlende Läufer
        # sowieso automatisch nach.)
        if self.crawler and self.crawler.spider:
            self.conn.execute("DELETE FROM failures WHERE spider = ?", (self.crawler.spider.name,))
            self.conn.commit()

    def close_spider(self, spider=None):
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def process_item(self, item, spider=None):
        sql = self.statements.get(type(item))
        if sql is None:
            return item  # unbekannter Typ -> unverändert weiterreichen
        row = asdict(item) | {"scraped_at": datetime.now(timezone.utc).isoformat()}
        self.conn.execute(sql, row)
        self.pending += 1
        if self.pending >= self.COMMIT_EVERY:
            self.conn.commit()
            self.pending = 0
        # Items immer zurückgeben, damit evtl. weitere Pipelines sie auch bekommen.
        return item
