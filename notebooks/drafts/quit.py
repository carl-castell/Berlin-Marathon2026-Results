import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl
    import seaborn as sns

    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # marathon_data.py lives one level up
    from marathon_data import clean, format_time, load_runners_raw, show_table, to_minutes

    sns.set_theme()
    return clean, load_runners_raw, pl, show_table, sns, to_minutes


@app.cell
def _(load_runners_raw):
    runners_raw = load_runners_raw()
    return (runners_raw,)


@app.cell
def _(clean, runners_raw):
    runners, cleaning_report = clean(runners_raw)
    cleaning_report
    return (runners,)


@app.cell
def _(pl, runners, show_table):
    dropouts = runners.filter(pl.col("result") == "dnf")
    show_table(dropouts)
    return (dropouts,)


@app.cell
def _(pl, runners):
    # everyone who started and was not disqualified; is_dropout = did not finish
    starters = runners.filter(pl.col("result").is_in(["finished", "dnf"])).with_columns(
        (pl.col("result") == "dnf").alias("is_dropout")
    )
    return (starters,)


@app.cell
def _(dropouts, pl, sns):
    # where they dropped out: last timing point reached
    _timing_points = ["before 5 km", "5 km", "10 km", "15 km", "20 km", "Halb", "25 km", "30 km", "35 km", "40 km"]
    sns.countplot(
        dropouts.with_columns(pl.col("last_split").fill_null("before 5 km")).to_dict(),
        x="last_split",
        order=_timing_points,
    )
    return


@app.cell
def _(pl, sns, starters):
    # 1. dropout rate by age group and sex
    _age_classes = ["JU20", "H", "30", "35", "40", "45", "50", "55", "60", "65", "70", "75", "80"]
    _dropout_rate = (
        starters.filter(pl.col("sex").is_in(["M", "W"]))
        .group_by("age_class", "sex")
        .agg((pl.col("is_dropout").mean() * 100).alias("dropout_rate_%"))
    )
    sns.barplot(_dropout_rate.to_dict(), x="age_class", y="dropout_rate_%", hue="sex", order=_age_classes)
    return


@app.cell
def _(pl, sns, starters):
    # 2. too fast at the start? first-half time: finishers vs. dropouts who quit after halfway
    _after_halfway = ["Halb", "25 km", "30 km", "35 km", "40 km"]
    _first_half = starters.filter(
        ~pl.col("is_dropout") | pl.col("last_split").is_in(_after_halfway)
    ).with_columns(
        pl.when(pl.col("is_dropout")).then(pl.lit("quit after halfway")).otherwise(pl.lit("finished")).alias("group")
    )
    sns.histplot(
        _first_half.to_dict(),
        x="first_half_time",
        hue="group",
        bins=30,
        stat="density",
        common_norm=False,
        element="step",
    )
    return


@app.cell
def _(pl, sns, starters):
    # 3. slowing down before quitting: pace per segment relative to the runner's first segment,
    #    aligned so that 0 = the last segment before they quit
    _SPLIT_KM = {
        "split_5km": 5.0, "split_10km": 10.0, "split_15km": 15.0, "split_20km": 20.0,
        "split_half": 21.0975, "split_25km": 25.0, "split_30km": 30.0, "split_35km": 35.0,
        "split_40km": 40.0,
    }
    _segments = (
        starters.filter(pl.col("is_dropout"))
        .select("runner_id", *_SPLIT_KM)
        .unpivot(index="runner_id", variable_name="split", value_name="time")
        .with_columns(pl.col("split").replace_strict(_SPLIT_KM).alias("km"))
        .drop_nulls("time")
        .sort("runner_id", "km")
        .with_columns(
            # time and distance since the previous recorded split (or since the start)
            (pl.col("time").diff().over("runner_id").fill_null(pl.col("time"))
             / pl.col("km").diff().over("runner_id").fill_null(pl.col("km"))).alias("pace"),
            (pl.int_range(pl.len()).over("runner_id") - pl.len().over("runner_id") + 1).alias("segments_before_quit"),
        )
        .with_columns((pl.col("pace") / pl.col("pace").first().over("runner_id")).alias("pace_vs_first_segment"))
        .filter(pl.col("segments_before_quit") >= -5)
    )
    sns.lineplot(_segments.to_dict(), x="segments_before_quit", y="pace_vs_first_segment", marker="o")
    return


@app.cell
def _(pl, sns, starters, to_minutes):
    # 4. dropout rate by start time (10-minute groups, only groups with >= 200 starters)
    _by_start = (
        starters.with_columns((to_minutes("start_line_time") // 10 * 10).cast(pl.Int64).alias("start_min"))
        .group_by("start_min")
        .agg(pl.len().alias("runners"), (pl.col("is_dropout").mean() * 100).alias("dropout_rate_%"))
        .filter(pl.col("runners") >= 200)
        .sort("start_min")
        .with_columns(
            pl.format(
                "{}:{}",
                (pl.col("start_min") // 60).cast(pl.String).str.zfill(2),
                (pl.col("start_min") % 60).cast(pl.String).str.zfill(2),
            ).alias("start_time")
        )
    )
    sns.barplot(_by_start.to_dict(), x="start_time", y="dropout_rate_%")
    return


@app.cell
def _(pl, sns, starters):
    # 5. dropout rate for the 15 countries with the most starters
    _by_country = (
        starters.group_by("country")
        .agg(pl.len().alias("runners"), (pl.col("is_dropout").mean() * 100).alias("dropout_rate_%"))
        .sort("runners", descending=True)
        .head(15)
        .sort("dropout_rate_%", descending=True)
    )
    _ax = sns.barplot(_by_country.to_dict(), x="dropout_rate_%", y="country")
    _ax.figure.tight_layout()  # room for long country names
    _ax
    return


if __name__ == "__main__":
    app.run()
