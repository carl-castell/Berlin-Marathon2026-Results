import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import sqlite3
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import polars as pl

    DB = Path(__file__).resolve().parent.parent / "data" / "marathon.db"
    return DB, alt, mo, pl, sqlite3


@app.cell
def _(mo):
    mo.md("""
    # BMW Berlin Marathon 2026 – Ergebnisse

    Daten aus `data/marathon.db` (erzeugt von den Scrapy-Spidern).
    Zeiten liegen in der DB als Text (`"02:02:50"`) und werden hier in Sekunden bzw. `Duration` umgewandelt.
    """)
    return


@app.cell
def _(pl):
    def hms_to_seconds(col: str) -> pl.Expr:
        """'HH:MM:SS' (oder 'MM:SS') -> Sekunden als Int."""
        parts = pl.col(col).str.split(":").list.eval(pl.element().cast(pl.Int64))
        return (
            parts.list.eval(
                # von hinten: Sekunden * 1, Minuten * 60, Stunden * 3600
                pl.element() * pl.lit(60).pow(pl.int_range(pl.len()).reverse())
            )
            .list.sum()
            .alias(col)
        )

    return (hms_to_seconds,)


@app.cell
def _(DB, hms_to_seconds, pl, sqlite3):
    with sqlite3.connect(DB) as _conn:
        runners_raw = pl.read_database("SELECT * FROM runners", _conn)
        details_raw = pl.read_database("SELECT * FROM details", _conn)
        splits_raw = pl.read_database("SELECT * FROM splits", _conn)

    runners = runners_raw.with_columns(
        hms_to_seconds("time_netto").alias("netto_s"),
        hms_to_seconds("time_brutto").alias("brutto_s"),
    ).with_columns(
        pl.duration(seconds="netto_s").alias("netto"),
        (pl.col("netto_s") / 60).alias("netto_min"),
    )

    details = details_raw.with_columns(
        hms_to_seconds("hm1_time").alias("hm1_s"),
        hms_to_seconds("hm2_time").alias("hm2_s"),
    )

    splits = splits_raw.with_columns(
        hms_to_seconds("time").alias("time_s"),
        hms_to_seconds("diff").alias("diff_s"),
    )
    return details, runners, splits


@app.cell
def _(details, mo, runners, splits):
    mo.md(f"""
    | Tabelle | Zeilen |
    |---|---|
    | runners | {runners.height:,} |
    | details | {details.height:,} |
    | splits  | {splits.height:,} |
    """)
    return


@app.cell
def _(runners):
    runners.head(20)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Verteilung der Zielzeiten nach Geschlecht
    """)
    return


@app.cell
def _(alt, mo, runners):
    _chart = (
        alt.Chart(runners.drop_nulls("netto_min").select("sex", "netto_min"))
        .mark_bar(opacity=0.7)
        .encode(
            x=alt.X("netto_min:Q", bin=alt.Bin(step=5), title="Nettozeit (Minuten)"),
            y=alt.Y("count():Q", stack=None, title="Läufer"),
            color=alt.Color("sex:N", title="Geschlecht"),
        )
        .properties(height=300)
    )
    mo.ui.altair_chart(_chart)
    return


@app.cell
def _(pl, runners):
    # Median-Zeit je Altersklasse und Geschlecht
    (
        runners.group_by("sex", "age_class")
        .agg(
            pl.len().alias("n"),
            pl.col("netto_s").median().alias("median_s"),
        )
        .with_columns(pl.duration(seconds="median_s").alias("median"))
        .sort("sex", "age_class")
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Pacing: zweite Hälfte vs. erste Hälfte

    `split_ratio = HM2 / HM1`. Unter 1 = *negative split* (zweite Hälfte schneller).
    """)
    return


@app.cell
def _(details, pl, runners):
    pacing = (
        details.join(runners.select("idp", "sex", "age_class", "netto_min"), on="idp")
        .drop_nulls(["hm1_s", "hm2_s"])
        .with_columns((pl.col("hm2_s") / pl.col("hm1_s")).alias("split_ratio"))
    )
    pacing.select(
        pl.len().alias("n"),
        (pl.col("split_ratio") < 1).mean().alias("anteil_negative_split"),
        pl.col("split_ratio").median().alias("median_ratio"),
    )
    return (pacing,)


@app.cell
def _(alt, mo, pacing):
    _chart = (
        alt.Chart(pacing.select("netto_min", "split_ratio", "sex"))
        .mark_circle(size=8, opacity=0.4)
        .encode(
            x=alt.X("netto_min:Q", title="Nettozeit (Minuten)"),
            y=alt.Y("split_ratio:Q", scale=alt.Scale(domain=[0.85, 1.5]), title="HM2 / HM1"),
            color=alt.Color("sex:N", title="Geschlecht"),
        )
        .properties(height=350)
    )
    mo.ui.altair_chart(_chart)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Durchschnittliche Pace je Abschnitt
    """)
    return


@app.cell
def _(pl, splits):
    # diff_s = Zeit für den Abschnitt seit dem letzten Split
    (
        splits.group_by("seq", "split_name")
        .agg(pl.col("diff_s").median().alias("median_abschnitt_s"), pl.len().alias("n"))
        .sort("seq")
        .with_columns(pl.duration(seconds="median_abschnitt_s").alias("median_abschnitt"))
    )
    return


if __name__ == "__main__":
    app.run()
