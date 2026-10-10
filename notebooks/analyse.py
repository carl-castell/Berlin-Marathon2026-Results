import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import sqlite3
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl
    import seaborn as sns

    sns.set_theme()

    DB = Path(__file__).resolve().parent.parent / "data" / "marathon.db"
    conn = sqlite3.connect(DB)


    def sql(query: str) -> pl.DataFrame:
        """Run a SQL query against marathon.db and return a Polars DataFrame."""
        return pl.read_database(query, conn)


    TIME_RE = r"^-?\d+(:\d{2}){1,2}$"  # "HH:MM:SS" or "MM:SS", optionally negative


    def duration(col: str) -> pl.Expr:
        """Text time ("02:02:50", "14:30", "-00:52") -> pl.Duration; "DSQ", "–", null -> null."""
        text = pl.col(col)
        parts = text.str.strip_prefix("-").str.split(":").list.eval(pl.element().cast(pl.Int64))
        seconds = parts.list.eval(
            pl.element() * pl.lit(60).pow(pl.int_range(pl.len()).reverse())
        ).list.sum()
        sign = pl.when(text.str.starts_with("-")).then(-1).otherwise(1)
        return (
            pl.when(text.str.contains(TIME_RE))
            .then(pl.duration(seconds=seconds * sign))
            .alias(col)
        )


    def time_of_day(col: str) -> pl.Expr:
        """'08:45:01' -> pl.Time; anything else -> null."""
        return pl.col(col).str.to_time("%H:%M:%S", strict=False).alias(col)


    return duration, pl, plt, sql


@app.cell
def _(sql):
    runners = sql("SELECT * FROM runners")

    return (runners,)


@app.cell
def _(runners):
    runners
    return


@app.cell
def _(sql):
    details = sql("""
        SELECT r.first_name, r.last_name, d.*
        FROM details d
        JOIN runners r USING (idp)
    """)
    details

    return


@app.cell
def _(sql):
    disqualified = sql("""
        SELECT first_name, last_name, sex, nation, bib, age_class, club
        FROM runners
        WHERE time_netto = 'DSQ'
        ORDER BY last_name
    """)
    disqualified

    return


@app.cell
def _(sql):
    dsq_last_split = sql("""
        SELECT r.first_name, r.last_name, d.last_split
        FROM runners r
        JOIN details d USING (idp)
        WHERE r.time_netto = 'DSQ'
        ORDER BY r.last_name
    """)
    dsq_last_split

    return


@app.cell
def _(duration, pl, plt, sql):
    from matplotlib.lines import Line2D

    _SEX = {"M": "Men", "W": "Women", "X": "Diverse"}
    _COLORS = {"Men": "#2a78d6", "Women": "#eb6834", "Diverse": "#1baf7a"}
    _INK = "#52514e"
    _LO, _HI = 55, 280

    halves = (
        sql("""
            SELECT r.sex, d.hm1_time, d.hm2_time
            FROM runners r JOIN details d USING (idp)
            WHERE d.status = 'Finished' AND r.time_netto != 'DSQ'
        """)
        .with_columns(duration("hm1_time"), duration("hm2_time"))
        .drop_nulls()
        .with_columns(
            (pl.col("hm1_time").dt.total_seconds() / 60).alias("first_half_min"),
            (pl.col("hm2_time").dt.total_seconds() / 60).alias("second_half_min"),
            pl.col("sex").replace_strict(_SEX).alias("sex"),
        )
    )

    _neg_share = (halves["second_half_min"] < halves["first_half_min"]).mean()
    _counts = dict(halves.group_by("sex").len().iter_rows())
    _hidden = halves.filter((pl.col("first_half_min") > _HI) | (pl.col("second_half_min") > _HI)).height

    _fig, _ax = plt.subplots(figsize=(7, 7))

    # Men + women in random order, so neither group is painted over the other
    _mw = halves.filter(pl.col("sex") != "Diverse").sample(fraction=1.0, shuffle=True, seed=1)
    _ax.scatter(
        _mw["first_half_min"], _mw["second_half_min"],
        c=_mw["sex"].replace_strict(_COLORS).to_list(),
        s=4, alpha=0.2, linewidths=0, rasterized=True,
    )
    # Diverse: only 51 runners -> bigger markers, drawn on top
    _dv = halves.filter(pl.col("sex") == "Diverse")
    _ax.scatter(_dv["first_half_min"], _dv["second_half_min"], color=_COLORS["Diverse"], s=16, linewidths=0)

    _ax.plot([_LO, _HI], [_LO, _HI], color=_INK, linewidth=1.5, linestyle="--")
    _ax.text(_HI - 6, _HI - 14, "even pace", color=_INK, ha="right", va="top",
             rotation=45, rotation_mode="anchor", fontsize=10)
    _ax.text(_HI - 8, _LO + 8, "below the line = second half faster", color=_INK, ha="right", fontsize=10)

    _ax.set(xlim=(_LO, _HI), ylim=(_LO, _HI), aspect="equal",
            xlabel="First half (minutes)", ylabel="Second half (minutes)")
    _ax.set_title(f"Most runners slow down – only {_neg_share:.0%} ran the second half faster",
                  loc="left", fontsize=12)
    _ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", markersize=7, color=_COLORS[s], label=f"{s} (n={_counts[s]:,})")
            for s in ["Men", "Women", "Diverse"]
        ],
        loc="upper left", frameon=False,
    )
    _fig.text(0.01, 0.005, f"Finishers with both half-marathon times. {_hidden} runners above {_HI} min not shown.",
              color=_INK, fontsize=8)
    _fig.tight_layout(rect=(0, 0.02, 1, 1))
    _ax

    return


if __name__ == "__main__":
    app.run()
