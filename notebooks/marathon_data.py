"""Shared data setup for all notebooks in this folder.

marimo puts the notebook's folder on the Python path, so every notebook here can
use:  from marathon_data import load_runners_raw, clean, show, ...

Steps (same in every notebook):
    runners_raw = load_runners_raw()               # joined + converted, values as on the site
    runners, cleaning_report = clean(runners_raw)  # known data quirks fixed
    show(runners)                                  # table with times as H:MM:SS

All times are minutes (float), e.g. 122.83 = 2:02:50.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import marimo as mo
import polars as pl

DB = Path(__file__).resolve().parent.parent / "data" / "marathon.db"

TIME_RE = r"^-?\d+(:\d{2}){1,2}$"  # "HH:MM:SS" or "MM:SS", optionally negative

SPLITS = {
    "time_05": "split_5km",
    "time_10": "split_10km",
    "time_15": "split_15km",
    "time_20": "split_20km",
    "time_21": "split_half",
    "time_25": "split_25km",
    "time_30": "split_30km",
    "time_35": "split_35km",
    "time_40": "split_40km",
    "time_finish_netto": "split_finish",
}

# Columns holding minutes; show() displays them as H:MM:SS
TIME_COLUMNS = ["time_netto", "time_brutto", "hm1_time", "hm2_time", *SPLITS.values()]


def sql(query: str) -> pl.DataFrame:
    """Run a SQL query against marathon.db and return a Polars DataFrame."""
    with closing(sqlite3.connect(DB)) as conn:
        return pl.read_database(query, conn)


def minutes(col: str) -> pl.Expr:
    """Text time ("02:02:50", "14:30", "-00:52") -> minutes as float; "DSQ", "–", null -> null."""
    text = pl.col(col)
    parts = text.str.strip_prefix("-").str.split(":").list.eval(pl.element().cast(pl.Int64))
    seconds = parts.list.eval(
        pl.element() * pl.lit(60).pow(pl.int_range(pl.len()).reverse())
    ).list.sum()
    sign = pl.when(text.str.starts_with("-")).then(-1).otherwise(1)
    return pl.when(text.str.contains(TIME_RE)).then(seconds * sign / 60).alias(col)


def hms(value: float | None) -> str:
    """Minutes -> "H:MM:SS" for display (122.83 -> "2:02:50"); null -> ""."""
    if value is None:
        return ""
    total = round(value * 60)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def load_runners_raw() -> pl.DataFrame:
    """One row per runner: runners + details + country + splits (wide).

    Values as delivered by the site, only joined and converted (text -> minutes).
    """
    details = sql("""
        SELECT idp, status, last_split, place_total,
               start_time_netto, start_time_brutto,
               hm1_time, hm1_place, hm2_time, hm2_place
        FROM details
    """)

    # one row per runner, one column per split (cumulative time in minutes)
    splits_wide = (
        sql("SELECT idp, split_key, time FROM splits")
        .with_columns(minutes("time"))
        .pivot(on="split_key", index="idp", values="time", on_columns=list(SPLITS))
        .rename(SPLITS)
    )

    return (
        sql("SELECT * FROM runners_with_country")
        .join(details, on="idp", how="left")
        .join(splits_wide, on="idp", how="left")
        .with_columns(
            # DSQ first: the site marks disqualified runners as "Finished"
            pl.when(pl.col("time_netto") == "DSQ").then(pl.lit("dsq"))
            .when(pl.col("status") == "Finished").then(pl.lit("finished"))
            .when(pl.col("status") == "Did Not Finish").then(pl.lit("dnf"))
            .when(pl.col("status") == "Not Started").then(pl.lit("dns"))
            .otherwise(pl.lit("unknown"))
            .alias("result"),
            minutes("time_netto"),
            minutes("time_brutto"),
            minutes("hm1_time"),
            minutes("hm2_time"),
        )
        .select(
            # who
            "idp", "sex", "last_name", "first_name", "nation", "country_en",
            "bib", "age_class", "club",
            # result
            "result", "status", "last_split", "place_overall", "place_ak", "place_total",
            # times (minutes; start times as "HH:MM:SS")
            "time_netto", "time_brutto", "start_time_netto", "start_time_brutto",
            "hm1_time", "hm1_place", "hm2_time", "hm2_place",
            # cumulative split times (minutes)
            *SPLITS.values(),
        )
    )


# Cleaning: every rule fixes a known data quirk. One entry per rule:
# (column, why, expression that produces the cleaned column)
CLEANING_RULES = [
    (
        "hm1_place",
        "site shows an HM 1 place without an HM 1 time (e.g. non-starters)",
        pl.when(pl.col("hm1_time").is_not_null()).then(pl.col("hm1_place")),
    ),
    (
        "hm2_place",
        "HM 2 place without an HM 2 time",
        pl.when(pl.col("hm2_time").is_not_null()).then(pl.col("hm2_place")),
    ),
]


def clean(runners_raw: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply CLEANING_RULES. Returns (runners, report: how many values each rule changed)."""
    runners = runners_raw.with_columns(expr.alias(col) for col, _, expr in CLEANING_RULES)
    report = pl.DataFrame(
        {
            "column": [col for col, _, _ in CLEANING_RULES],
            "rule": [why for _, why, _ in CLEANING_RULES],
            "values_changed": [
                int(runners_raw[col].ne_missing(runners[col]).sum()) for col, _, _ in CLEANING_RULES
            ],
        }
    )
    return runners, report


def show(df: pl.DataFrame, **kwargs):
    """Interactive table; minute columns are displayed as H:MM:SS (data stays minutes)."""
    fmt = {c: hms for c in TIME_COLUMNS if c in df.columns}
    return mo.ui.table(df, format_mapping=fmt, **kwargs)
