"""Shared data setup for all notebooks in this folder.

marimo puts the notebook's folder on the Python path, so every notebook here can
use:  from marathon_data import load_runners_raw, clean, show_table, ...

Steps (same in every notebook):
    runners_raw = load_runners_raw()               # joined + converted, values as on the site
    runners, cleaning_report = clean(runners_raw)  # known data quirks fixed
    runners = add_analysis_columns(runners)        # paces, split ratio, finish-time group
    show_table(runners)                            # table with times as H:MM:SS

All times are minutes (float), e.g. 122.83 = 2:02:50.

Column names are translated from the site's (partly German) names to English in
load_runners_raw(), see COLUMN_NAMES. The database itself keeps the original names.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import marimo as mo
import polars as pl

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "marathon.db"
FIGURES_DIR = Path(__file__).resolve().parent.parent / "figures"

TIME_PATTERN = r"^-?\d+(:\d{2}){1,2}$"  # "HH:MM:SS" or "MM:SS", optionally negative

MARATHON_KM = 42.195
HALF_MARATHON_KM = 21.0975

# split key in the database -> column name (cumulative time from the start line, in minutes)
SPLIT_COLUMNS = {
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

# database / site column name -> name used in the notebooks
COLUMN_NAMES = {
    "idp": "runner_id",
    "country_en": "country",
    "nation": "nation_code",  # code used by the site (mostly IOC, e.g. GER)
    "place_overall": "place_in_sex",  # the site's "overall" place is counted per sex
    "place_ak": "place_in_age_class",
    "place_total": "place_overall",  # place among all runners
    "time_netto": "net_time",  # start line -> finish (the official time)
    "time_brutto": "gun_time",  # start signal of the runner's wave -> finish
    "start_time_netto": "start_line_time",  # time of day the runner crossed the start line
    "start_time_brutto": "wave_start_time",  # time of day of the wave's start signal
    "hm1_time": "first_half_time",
    "hm1_place": "first_half_place",  # place (per sex) by first-half time = place at halfway
    "hm2_time": "second_half_time",
    "hm2_place": "second_half_place",  # place (per sex) by second-half time
}

# Columns holding minutes; show_table() displays them as H:MM:SS
TIME_COLUMNS = ["net_time", "gun_time", "first_half_time", "second_half_time", *SPLIT_COLUMNS.values()]


def run_sql(query: str) -> pl.DataFrame:
    """Run a SQL query against marathon.db (read-only) and return a Polars DataFrame."""
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"{DATABASE_PATH} not found. The data is not part of the repo: create it with the "
            "scraper (see README), or view the exported HTML instead."
        )
    with closing(sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)) as connection:
        return pl.read_database(query, connection)


def to_minutes(column: str) -> pl.Expr:
    """Text time ("02:02:50", "14:30", "-00:52") -> minutes as float; "DSQ", "–", null -> null."""
    text = pl.col(column)
    parts = text.str.strip_prefix("-").str.split(":").list.eval(pl.element().cast(pl.Int64))
    seconds = parts.list.eval(
        pl.element() * pl.lit(60).pow(pl.int_range(pl.len()).reverse())
    ).list.sum()
    sign = pl.when(text.str.starts_with("-")).then(-1).otherwise(1)
    return pl.when(text.str.contains(TIME_PATTERN)).then(seconds * sign / 60).alias(column)


def format_time(minutes: float | None) -> str:
    """Minutes -> "H:MM:SS" for display (122.83 -> "2:02:50"); null -> ""."""
    if minutes is None:
        return ""
    total_seconds = round(minutes * 60)
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, rest = divmod(total_seconds, 3600)
    mins, secs = divmod(rest, 60)
    return f"{sign}{hours}:{mins:02d}:{secs:02d}"


def load_runners_raw() -> pl.DataFrame:
    """One row per runner: runners + details + country + splits (wide).

    Values as delivered by the site, only joined, converted (text -> minutes) and renamed.
    """
    details = run_sql("""
        SELECT idp, status, last_split, place_total,
               start_time_netto, start_time_brutto,
               hm1_time, hm1_place, hm2_time, hm2_place
        FROM details
    """)

    # one row per runner, one column per split (cumulative time in minutes)
    splits_wide = (
        run_sql("SELECT idp, split_key, time FROM splits")
        .with_columns(to_minutes("time"))
        .pivot(on="split_key", index="idp", values="time", on_columns=list(SPLIT_COLUMNS))
        .rename(SPLIT_COLUMNS)
    )

    return (
        run_sql("SELECT * FROM runners_with_country")
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
            to_minutes("time_netto"),
            to_minutes("time_brutto"),
            to_minutes("hm1_time"),
            to_minutes("hm2_time"),
        )
        .rename(COLUMN_NAMES)
        .select(
            # who
            "runner_id", "sex", "last_name", "first_name", "nation_code", "country", "iso3",
            "bib", "age_class", "club",
            # result: finished / dnf (did not finish) / dns (did not start) / dsq (disqualified)
            "result", "status", "last_split", "place_in_sex", "place_in_age_class", "place_overall",
            # times (minutes; start times as "HH:MM:SS" time of day)
            "net_time", "gun_time", "start_line_time", "wave_start_time",
            "first_half_time", "first_half_place", "second_half_time", "second_half_place",
            # cumulative split times (minutes)
            *SPLIT_COLUMNS.values(),
        )
    )


# Cleaning: every rule fixes a known data quirk. One entry per rule:
# (column, why, expression that produces the cleaned column)
CLEANING_RULES = [
    (
        "first_half_place",
        "site shows a first-half place without a first-half time (e.g. non-starters)",
        pl.when(pl.col("first_half_time").is_not_null()).then(pl.col("first_half_place")),
    ),
    (
        "second_half_place",
        "second-half place without a second-half time",
        pl.when(pl.col("second_half_time").is_not_null()).then(pl.col("second_half_place")),
    ),
]


def clean(runners_raw: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Apply CLEANING_RULES. Returns (runners, report: how many values each rule changed)."""
    runners = runners_raw.with_columns(rule.alias(column) for column, _, rule in CLEANING_RULES)
    report = pl.DataFrame(
        {
            "column": [column for column, _, _ in CLEANING_RULES],
            "rule": [reason for _, reason, _ in CLEANING_RULES],
            "values_changed": [
                int(runners_raw[column].ne_missing(runners[column]).sum())
                for column, _, _ in CLEANING_RULES
            ],
        }
    )
    return runners, report


def show_table(df: pl.DataFrame, **kwargs):
    """Interactive table; minute columns are displayed as H:MM:SS (data stays minutes)."""
    time_formats = {column: format_time for column in TIME_COLUMNS if column in df.columns}
    return mo.ui.table(df, format_mapping=time_formats, **kwargs)


# --- analysis helpers -------------------------------------------------------

# age classes in order: JU20 = under 20, H = 20-29 ("Hauptklasse"), 30 = 30-34, ...
AGE_CLASS_ORDER = ["JU20", "H", "30", "35", "40", "45", "50", "55", "60", "65", "70", "75", "80"]
AGE_CLASS_LABELS = {"JU20": "under 20", "H": "20-29", "80": "80+"} | {
    age_class: f"{age_class}-{int(age_class) + 4}" for age_class in AGE_CLASS_ORDER[2:-1]
}

# split column -> km; segments are 0-5, 5-10, ..., 35-40, 40-42.2 (half split skipped)
SPLIT_KM = {
    "split_5km": 5.0, "split_10km": 10.0, "split_15km": 15.0, "split_20km": 20.0,
    "split_25km": 25.0, "split_30km": 30.0, "split_35km": 35.0, "split_40km": 40.0,
    "split_finish": MARATHON_KM,
}
# one pace column per segment: pace_km_0_5, pace_km_5_10, ..., pace_km_40_42
_segment_starts = [0, *list(SPLIT_KM.values())[:-1]]
PACE_COLUMNS = [f"pace_km_{int(start)}_{int(end)}" for start, end in zip(_segment_starts, SPLIT_KM.values())]
SEGMENT_END_KM = dict(zip(PACE_COLUMNS, SPLIT_KM.values()))  # pace column -> km at segment end

# finish-time groups: (upper limit in minutes, label)
FINISH_TIME_GROUPS = [(180, "<3:00"), (210, "3:00-3:30"), (240, "3:30-4:00"),
                      (270, "4:00-4:30"), (300, "4:30-5:00"), (None, ">5:00")]
FINISH_TIME_GROUP_ORDER = [label for _, label in FINISH_TIME_GROUPS]


def add_analysis_columns(runners: pl.DataFrame) -> pl.DataFrame:
    """Add analysis columns.

    - pace_km_0_5 ... pace_km_40_42: pace per segment (min/km)
    - split_ratio: second half / first half time (< 1 = negative split, faster second half)
    - pace_variation: coefficient of variation of the segment paces (std / mean; 0 = perfectly even)
    - finish_time_group: "<3:00", "3:00-3:30", ..., ">5:00"
    """
    split_columns = list(SPLIT_KM)
    split_km = list(SPLIT_KM.values())
    segment_paces = []
    for i, pace_column in enumerate(PACE_COLUMNS):
        previous_time = pl.col(split_columns[i - 1]) if i > 0 else 0
        previous_km = split_km[i - 1] if i > 0 else 0
        segment_minutes = pl.col(split_columns[i]) - previous_time
        segment_paces.append((segment_minutes / (split_km[i] - previous_km)).alias(pace_column))

    finish_time_group = pl.when(pl.col("net_time").is_null()).then(None)
    for upper_limit, label in FINISH_TIME_GROUPS:
        is_in_group = pl.col("net_time") < upper_limit if upper_limit else pl.lit(True)
        finish_time_group = finish_time_group.when(is_in_group).then(pl.lit(label))

    all_paces = pl.concat_list(PACE_COLUMNS)
    return runners.with_columns(segment_paces).with_columns(
        (pl.col("second_half_time") / pl.col("first_half_time")).alias("split_ratio"),
        (all_paces.list.std() / all_paces.list.mean()).alias("pace_variation"),
        finish_time_group.alias("finish_time_group"),
    )


def save_figure(figure, name: str):
    """Save a matplotlib figure as figures/<name>.png and return it (so marimo still shows it)."""
    FIGURES_DIR.mkdir(exist_ok=True)
    figure.savefig(FIGURES_DIR / f"{name}.png", dpi=150, bbox_inches="tight")
    return figure
