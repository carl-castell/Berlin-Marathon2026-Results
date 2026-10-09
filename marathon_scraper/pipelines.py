"""Item pipeline: writes all items into a SQLite database.

Why SQLite instead of CSV?
- Several tables (runners, details, splits) that can be joined with SQL.
- UPSERT ("insert or update"): running a spider twice creates no duplicates,
  existing rows are simply updated.
- The detail spider can query what is still missing -> resumable.
- Polars reads SQLite directly (pl.read_database).

Lifecycle of a pipeline in Scrapy:
  open_spider()   -> once at the start   (open DB, create tables)
  process_item()  -> for every item      (write a row)
  close_spider()  -> once at the end     (commit, close DB)
"""

import logging
import sqlite3
from collections import Counter
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .countries import create_view, ensure_relation, load_countries
from .items import DetailItem, FailureItem, RunnerItem, SplitItem

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runners (
    idp           TEXT PRIMARY KEY,
    sex           TEXT,
    place_overall INTEGER,
    place_ak      INTEGER,
    last_name     TEXT,
    first_name    TEXT,
    nation        TEXT REFERENCES countries(code),
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

-- Requests that failed for good in the LAST run of the respective spider.
CREATE TABLE IF NOT EXISTS failures (
    url        TEXT PRIMARY KEY,
    spider     TEXT,
    error      TEXT,
    scraped_at TEXT
);
"""

# Which item class goes into which table, and what its primary key is.
TABLES = {
    RunnerItem: ("runners", ["idp"]),
    DetailItem: ("details", ["idp"]),
    SplitItem: ("splits", ["idp", "split_key"]),
    FailureItem: ("failures", ["url"]),
}


def upsert_sql(table: str, columns: list[str], key: list[str]) -> str:
    """Build an 'INSERT ... ON CONFLICT DO UPDATE' statement for the table.

    Example result:
      INSERT INTO runners (idp, last_name, ...) VALUES (:idp, :last_name, ...)
      ON CONFLICT (idp) DO UPDATE SET last_name = excluded.last_name, ...
    """
    cols = ", ".join(columns)
    params = ", ".join(f":{c}" for c in columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in key)
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({params}) "
        f"ON CONFLICT ({', '.join(key)}) DO UPDATE SET {updates}"
    )


class SQLitePipeline:
    # Commit every N items. One commit per item would be very slow; no commit
    # until the end would risk losing data in a crash.
    COMMIT_EVERY = 500

    def __init__(self, db_path: str, crawler=None):
        self.db_path = db_path
        self.crawler = crawler
        self.conn: sqlite3.Connection | None = None
        self.pending = 0
        self.known_countries: set[str] = set()
        self.unknown_countries: Counter[str] = Counter()
        # Prepare the SQL statements once instead of rebuilding them per item.
        self.statements = {
            cls: upsert_sql(table, [f.name for f in fields(cls)] + ["scraped_at"], key)
            for cls, (table, key) in TABLES.items()
        }

    @classmethod
    def from_crawler(cls, crawler):
        # This is how a pipeline gets the settings: Scrapy calls from_crawler
        # and passes the crawler, which knows all settings.
        return cls(db_path=crawler.settings.get("SQLITE_PATH"), crawler=crawler)

    def open_spider(self, spider=None):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        # WAL lets you read the DB (e.g. in the notebook) while scraping.
        self.conn.execute("PRAGMA journal_mode=WAL")
        # countries first: runners.nation references countries.code
        load_countries(self.conn)
        self.conn.executescript(SCHEMA)
        ensure_relation(self.conn)  # older DBs: add the foreign key
        create_view(self.conn)
        self.known_countries = {row[0] for row in self.conn.execute("SELECT code FROM countries")}
        # Forget this spider's old failures: whatever fails again this time
        # is added anew. (The detail spider retries missing runners anyway.)
        if self.crawler and self.crawler.spider:
            self.conn.execute("DELETE FROM failures WHERE spider = ?", (self.crawler.spider.name,))
            self.conn.commit()

    def close_spider(self, spider=None):
        if self.unknown_countries:
            codes = ", ".join(f"{c} ({n}x)" for c, n in self.unknown_countries.most_common())
            logger.warning(
                "Country codes not in countries.csv: %s. The runners are saved, but have no "
                "country name. Fix: add the codes to EXTRA in scripts/build_countries.py "
                "(or directly to marathon_scraper/countries.csv), regenerate, then run "
                "`uv run python -m marathon_scraper.countries`.",
                codes,
            )
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def process_item(self, item, spider=None):
        sql = self.statements.get(type(item))
        if sql is None:
            return item  # unknown type -> pass through unchanged
        if isinstance(item, RunnerItem):
            self.check_country(item)
        row = asdict(item) | {"scraped_at": datetime.now(timezone.utc).isoformat()}
        self.conn.execute(sql, row)
        self.pending += 1
        if self.pending >= self.COMMIT_EVERY:
            self.conn.commit()
            self.pending = 0
        # Always return the item so further pipelines (if any) receive it too.
        return item

    def check_country(self, item: RunnerItem) -> None:
        """Warn about country codes missing from the `countries` table.

        SQLite doesn't enforce foreign keys by default, so the runner is still
        saved (no data loss); only the country name in runners_with_country
        stays empty until the code is added to countries.csv.
        """
        code = item.nation
        if code is None or code in self.known_countries:
            return
        if code not in self.unknown_countries:
            logger.warning(
                "Unknown country code %r (e.g. bib %s) – not in countries.csv. "
                "Runner is saved without a country name.",
                code,
                item.bib,
            )
        self.unknown_countries[code] += 1
        if self.crawler:
            stats = self.crawler.stats
            stats.inc_value("countries/unknown_runners")
            stats.set_value(
                "countries/unknown_codes",
                ", ".join(f"{c} ({n}x)" for c, n in self.unknown_countries.most_common()),
            )
