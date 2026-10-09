"""`countries` lookup table: country code -> English + German name.

`runners.nation` references `countries.code` (foreign key). The codes are the
ones the results site uses: IOC codes (GER, SUI, RSA, ...), or ISO alpha-3 for
territories without an IOC code. Data source: countries.csv (regenerate with
scripts/build_countries.py).

The pipeline loads the table automatically. For an existing database:
    uv run python -m marathon_scraper.countries
"""

import csv
import sqlite3
import sys
from pathlib import Path

CSV_PATH = Path(__file__).with_name("countries.csv")

COUNTRIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS countries (
    code    TEXT PRIMARY KEY,
    iso3    TEXT,
    iso2    TEXT,
    name_en TEXT NOT NULL,
    name_de TEXT NOT NULL
);
"""

VIEW_SQL = """
DROP VIEW IF EXISTS runners_with_country;
CREATE VIEW runners_with_country AS
SELECT r.*, c.name_en AS country_en, c.name_de AS country_de, c.iso2, c.iso3
FROM runners r
LEFT JOIN countries c ON c.code = r.nation;
"""


def load_countries(conn: sqlite3.Connection) -> int:
    """Create the `countries` table and insert/update all rows from the CSV."""
    conn.executescript(COUNTRIES_SCHEMA)
    with CSV_PATH.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    conn.executemany(
        """
        INSERT INTO countries (code, iso3, iso2, name_en, name_de)
        VALUES (:code, :iso3, :iso2, :name_en, :name_de)
        ON CONFLICT (code) DO UPDATE SET
            iso3 = excluded.iso3, iso2 = excluded.iso2,
            name_en = excluded.name_en, name_de = excluded.name_de
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def create_view(conn: sqlite3.Connection) -> None:
    conn.executescript(VIEW_SQL)


def has_nation_fk(conn: sqlite3.Connection) -> bool:
    fks = conn.execute("PRAGMA foreign_key_list(runners)").fetchall()
    # columns: id, seq, table, from, to, ...
    return any(fk[2] == "countries" and fk[3] == "nation" for fk in fks)


def ensure_relation(conn: sqlite3.Connection) -> bool:
    """Add the foreign key runners.nation -> countries.code to an existing table.

    SQLite cannot add a foreign key with ALTER TABLE, so the table is rebuilt
    with the new definition and the rows are copied over. Returns True if the
    table was rebuilt.

    Codes missing from `countries` don't stop the rebuild (SQLite doesn't
    enforce foreign keys by default); they are reported by the callers.
    """
    exists = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runners'"
    ).fetchone()
    if not exists or has_nation_fk(conn):
        return False

    old_sql = exists[0]
    new_sql = old_sql.replace("nation        TEXT,", "nation        TEXT REFERENCES countries(code),", 1)
    if new_sql == old_sql:
        raise RuntimeError("Unexpected runners schema, cannot add the foreign key automatically.")
    new_sql = new_sql.replace("CREATE TABLE runners", "CREATE TABLE runners_new", 1)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(new_sql)
        conn.execute("INSERT INTO runners_new SELECT * FROM runners")
        conn.execute("DROP VIEW IF EXISTS runners_with_country")
        conn.execute("DROP TABLE runners")
        conn.execute("ALTER TABLE runners_new RENAME TO runners")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


def main() -> None:
    from scrapy.utils.project import get_project_settings

    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_project_settings()["SQLITE_PATH"])
    if not db_path.exists():
        sys.exit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    n = load_countries(conn)
    print(f"countries: {n} rows loaded")
    if ensure_relation(conn):
        print("runners: rebuilt with foreign key nation -> countries.code")
    else:
        print("runners: foreign key already present")
    create_view(conn)

    unmapped = conn.execute(
        "SELECT nation, count(*) FROM runners_with_country WHERE country_en IS NULL GROUP BY nation"
    ).fetchall()
    total = conn.execute("SELECT count(*) FROM runners").fetchone()[0]
    print("view runners_with_country created")
    conn.close()

    if unmapped:
        codes = ", ".join(f"{code} ({n}x)" for code, n in unmapped)
        sys.exit(
            f"runners: {total} rows, but these country codes are not in countries.csv: {codes}\n"
            "Add them to EXTRA in scripts/build_countries.py (or directly to the CSV), "
            "regenerate, and run this command again."
        )
    print(f"runners: {total} rows, all with a country")


if __name__ == "__main__":
    main()
