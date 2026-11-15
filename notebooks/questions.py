import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl
    import seaborn as sns

    from marathon_data import (
        AGE_CLASS_ORDER,
        FINISH_TIME_GROUP_ORDER,
        MARATHON_KM,
        PACE_COLUMNS,
        SEGMENT_END_KM,
        add_analysis_columns,
        clean,
        format_time,
        load_runners_raw,
        save_figure,
        to_minutes,
    )

    sns.set_theme()
    return (
        AGE_CLASS_ORDER,
        FINISH_TIME_GROUP_ORDER,
        MARATHON_KM,
        PACE_COLUMNS,
        SEGMENT_END_KM,
        add_analysis_columns,
        clean,
        format_time,
        load_runners_raw,
        mo,
        pl,
        plt,
        save_figure,
        sns,
        to_minutes,
    )


@app.cell
def _(mo):
    mo.md("""
    # Berlin Marathon 2026: research questions (working notebook)

    All 9 candidate questions. The 5 with the clearest outcome go into `SE_42.py`.
    Times are minutes (float); `format_time()` displays them as H:MM:SS.
    """)
    return


@app.cell
def _(load_runners_raw):
    runners_raw = load_runners_raw()
    return (runners_raw,)


@app.cell
def _(add_analysis_columns, clean, runners_raw):
    runners, cleaning_report = clean(runners_raw)
    runners = add_analysis_columns(runners)
    cleaning_report
    return (runners,)


@app.cell
def _(PACE_COLUMNS, pl, runners):
    # finishers with sex M/W (the diverse category X is too small for comparisons)
    finishers = runners.filter(pl.col("result") == "finished", pl.col("sex").is_in(["M", "W"]))

    # finishers whose segment paces are all present and plausible (2.5-20 min/km);
    # a few runners have missing or impossible splits (timing glitches)
    finishers_clean_splits = finishers.filter(
        pl.all_horizontal(pl.col(pace).is_between(2.5, 20) for pace in PACE_COLUMNS)
    )

    # everyone who started and was not disqualified; is_dropout = did not finish
    starters = runners.filter(pl.col("result").is_in(["finished", "dnf"])).with_columns(
        (pl.col("result") == "dnf").alias("is_dropout")
    )
    {
        "finishers": finishers.height,
        "finishers_clean_splits": finishers_clean_splits.height,
        "starters": starters.height,
    }
    return finishers, finishers_clean_splits, starters


@app.cell
def _(mo):
    mo.md("""
    ## Q1 · Negative split: who runs the second half faster?

    Share of runners with a negative split (second half faster than the first) per finish-time group,
    and first vs second half time.
    """)
    return


@app.cell
def _(FINISH_TIME_GROUP_ORDER, finishers, pl, plt, save_figure, sns):
    _with_halves = finishers.drop_nulls("split_ratio")
    negative_split_by_group = (
        _with_halves.group_by("finish_time_group", "sex")
        .agg(
            pl.len().alias("runners"),
            ((pl.col("split_ratio") < 1).mean() * 100).alias("negative_split_%"),
            pl.col("split_ratio").median().alias("median_split_ratio"),
        )
        .sort("finish_time_group", "sex")
    )

    _figure, (_halves_ax, _share_ax) = plt.subplots(1, 2, figsize=(13, 5))
    _halves_ax.hexbin(_with_halves["first_half_time"], _with_halves["second_half_time"],
                      gridsize=60, bins="log", cmap="viridis", extent=(80, 220, 80, 260))
    _halves_ax.plot([80, 220], [80, 220], color="white", lw=1.5, ls="--", label="even split")
    _halves_ax.set(xlabel="first half (min)", ylabel="second half (min)", title="First vs second half")
    _halves_ax.legend(loc="upper left")
    sns.barplot(negative_split_by_group.to_pandas(), x="finish_time_group", y="negative_split_%",
                hue="sex", order=FINISH_TIME_GROUP_ORDER, ax=_share_ax)
    _share_ax.set(xlabel="finish time", ylabel="negative split (%)", title="Share of negative splitters")
    save_figure(_figure, "negative_split")
    return (negative_split_by_group,)


@app.cell
def _(finishers, negative_split_by_group, pl):
    {
        "overall_negative_split_%": round(
            finishers.drop_nulls("split_ratio").select((pl.col("split_ratio") < 1).mean() * 100).item(), 1
        ),
        "by_group": negative_split_by_group,
    }
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q2 · Hitting the wall: where does pace drop most?

    Pace per 5 km segment relative to the runner's own 5–10 km pace (1.0 = same pace),
    by finish-time group and sex. The first 5 km are not used as reference because of the crowded start.
    """)
    return


@app.cell
def _(
    FINISH_TIME_GROUP_ORDER,
    PACE_COLUMNS,
    SEGMENT_END_KM,
    finishers_clean_splits,
    pl,
    save_figure,
    sns,
):
    relative_pace_by_km = (
        finishers_clean_splits.select("runner_id", "sex", "finish_time_group", *PACE_COLUMNS)
        .with_columns(pl.col(pace) / pl.col("pace_km_5_10") for pace in PACE_COLUMNS)
        .unpivot(index=["runner_id", "sex", "finish_time_group"],
                 variable_name="segment", value_name="relative_pace")
        .with_columns(pl.col("segment").replace_strict(SEGMENT_END_KM).alias("segment_end_km"))
        .group_by("sex", "finish_time_group", "segment_end_km")
        .agg(pl.col("relative_pace").mean())
        .sort("sex", "finish_time_group", "segment_end_km")
    )
    _grid = sns.relplot(relative_pace_by_km.to_pandas(), x="segment_end_km", y="relative_pace",
                        hue="finish_time_group", col="sex", kind="line", marker="o",
                        hue_order=FINISH_TIME_GROUP_ORDER, height=4.5, aspect=1.2)
    _grid.set_axis_labels("segment end (km)", "pace relative to 5-10 km")
    _grid.figure.suptitle("Pace over the course", y=1.03)
    save_figure(_grid.figure, "wall")
    return (relative_pace_by_km,)


@app.cell
def _(pl, relative_pace_by_km):
    # biggest slowdown from one segment to the next, per group
    (
        relative_pace_by_km
        .with_columns(pl.col("relative_pace").diff().over("sex", "finish_time_group").alias("slowdown"))
        .sort("slowdown", descending=True, nulls_last=True)
        .group_by("sex", "finish_time_group", maintain_order=True)
        .first()
        .sort("sex", "finish_time_group")
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q3 · Age curve: how do finish times change with age, and does the sex gap change?
    """)
    return


@app.cell
def _(AGE_CLASS_ORDER, finishers, plt, save_figure, sns):
    _figure, _axes = plt.subplots(figsize=(13, 5))
    sns.boxplot(finishers.to_pandas(), x="age_class", y="net_time", hue="sex",
                order=AGE_CLASS_ORDER, showfliers=False, ax=_axes)
    _axes.set(xlabel="age class (H = 20-29)", ylabel="net time (min)", title="Finish time by age class and sex")
    save_figure(_figure, "age_curve")
    return


@app.cell
def _(AGE_CLASS_ORDER, finishers, format_time, pl):
    _age_class_position = {age_class: i for i, age_class in enumerate(AGE_CLASS_ORDER)}
    (
        finishers.filter(pl.col("age_class").is_in(AGE_CLASS_ORDER))
        .group_by("age_class", "sex")
        .agg(pl.col("net_time").median().alias("median"), pl.len().alias("runners"))
        .pivot(on="sex", index="age_class", values=["median", "runners"])
        .with_columns(
            ((pl.col("median_W") / pl.col("median_M") - 1) * 100).round(1).alias("women_slower_%"),
            pl.col("median_M", "median_W").map_elements(format_time, return_dtype=pl.String),
        )
        .sort(pl.col("age_class").replace_strict(_age_class_position))
        .select("age_class", "runners_M", "runners_W", "median_M", "median_W", "women_slower_%")
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q4 · Start time: do later starters run slower?

    Time of day the runner crossed the start line, in 10-minute groups (groups with ≥ 200 finishers).
    """)
    return


@app.cell
def _(finishers, pl, plt, save_figure, sns, to_minutes):
    finishers_by_start = (
        finishers.with_columns(
            (to_minutes("start_line_time") // 10 * 10).cast(pl.Int64).alias("start_minute_of_day")
        )
        .drop_nulls("start_minute_of_day")
        .with_columns(
            pl.format("{}:{}",
                      (pl.col("start_minute_of_day") // 60).cast(pl.String).str.zfill(2),
                      (pl.col("start_minute_of_day") % 60).cast(pl.String).str.zfill(2))
            .alias("start_group")
        )
        .filter(pl.len().over("start_group") >= 200)
        .sort("start_minute_of_day")
    )
    _figure, _axes = plt.subplots(figsize=(13, 5))
    sns.boxplot(finishers_by_start.to_pandas(), x="start_group", y="net_time",
                showfliers=False, color="C0", ax=_axes)
    _axes.set(xlabel="start time (10-min group)", ylabel="net time (min)", title="Finish time by start time")
    save_figure(_figure, "start_time")
    return (finishers_by_start,)


@app.cell
def _(finishers_by_start, format_time, pl):
    (
        finishers_by_start.group_by("start_group", "start_minute_of_day")
        .agg(
            pl.len().alias("runners"),
            pl.col("net_time").median().alias("median_net_time"),
            (pl.col("gun_time") - pl.col("net_time")).median().alias("wait_at_start"),
        )
        .sort("start_minute_of_day")
        .with_columns(pl.col("median_net_time", "wait_at_start").map_elements(format_time, return_dtype=pl.String))
        .drop("start_minute_of_day")
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q5 · Dropout anatomy: who quits, where, and did they start too fast?
    """)
    return


@app.cell
def _(AGE_CLASS_ORDER, pl, plt, save_figure, sns, starters):
    _timing_points = ["before 5 km", "5 km", "10 km", "15 km", "20 km", "Halb", "25 km", "30 km", "35 km", "40 km"]
    _after_halfway = ["Halb", "25 km", "30 km", "35 km", "40 km"]  # "Halb" = half-marathon point
    _dropouts = starters.filter(pl.col("is_dropout")).with_columns(
        pl.col("last_split").fill_null("before 5 km")
    )
    _dropout_rate = (
        starters.filter(pl.col("sex").is_in(["M", "W"]))
        .group_by("age_class", "sex")
        .agg((pl.col("is_dropout").mean() * 100).alias("dropout_rate_%"))
    )
    # first-half time: finishers vs runners who quit after halfway
    _finished_or_late_dropout = starters.filter(
        ~pl.col("is_dropout") | pl.col("last_split").is_in(_after_halfway)
    ).with_columns(
        pl.when(pl.col("is_dropout")).then(pl.lit("quit after halfway")).otherwise(pl.lit("finished"))
        .alias("group")
    )

    _figure, (_where_ax, _rate_ax, _first_half_ax) = plt.subplots(1, 3, figsize=(18, 5))
    sns.countplot(_dropouts.to_pandas(), x="last_split", order=_timing_points, color="C3", ax=_where_ax)
    _where_ax.set(xlabel="last timing point reached", ylabel="dropouts", title="Where runners quit")
    _where_ax.tick_params(axis="x", rotation=45)
    sns.barplot(_dropout_rate.to_pandas(), x="age_class", y="dropout_rate_%", hue="sex",
                hue_order=["M", "W"], order=AGE_CLASS_ORDER, ax=_rate_ax)
    _rate_ax.set(xlabel="age class", ylabel="dropout rate (%)", title="Dropout rate by age and sex")
    sns.histplot(_finished_or_late_dropout.to_pandas(), x="first_half_time", hue="group", bins=40,
                 stat="density", common_norm=False, element="step", ax=_first_half_ax)
    _first_half_ax.set(xlabel="first-half time (min)", title="First half: finishers vs late quitters")
    save_figure(_figure, "dropouts")
    return


@app.cell
def _(pl, starters):
    {
        "dropout_rate_%": round(starters["is_dropout"].mean() * 100, 2),
        "by_sex": starters.group_by("sex").agg(
            pl.len().alias("starters"), (pl.col("is_dropout").mean() * 100).round(2).alias("dropout_%")
        ),
        "median_first_half_finished_vs_late_dropout": starters.filter(
            ~pl.col("is_dropout") | pl.col("last_split").is_in(["Halb", "25 km", "30 km", "35 km", "40 km"])
        ).group_by("is_dropout").agg(pl.col("first_half_time").median(), pl.len().alias("runners")),
    }
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q6 · Country effects: are foreign runners faster than Germans of the same sex and age?

    Each runner's net time is divided by the median time of **German** runners of the same sex and age class.
    Per country: median of that ratio − 1 (in %). Negative = faster than comparable Germans.
    15 countries with the most finishers.
    """)
    return


@app.cell
def _(finishers, pl, plt, save_figure, sns):
    _german_median = (
        finishers.filter(pl.col("nation_code") == "GER")
        .group_by("sex", "age_class")
        .agg(pl.col("net_time").median().alias("german_median_time"))
    )
    country_vs_germany = (
        finishers.join(_german_median, on=["sex", "age_class"])
        .with_columns((pl.col("net_time") / pl.col("german_median_time")).alias("time_vs_germans"))
        .group_by("country")
        .agg(pl.len().alias("runners"), ((pl.col("time_vs_germans").median() - 1) * 100).alias("difference_%"))
        .sort("runners", descending=True)
        .head(15)
        .sort("difference_%")
    )
    _figure, _axes = plt.subplots(figsize=(9, 6))
    sns.barplot(country_vs_germany.to_pandas(), x="difference_%", y="country", color="C0", ax=_axes)
    _axes.axvline(0, color="black", lw=1)
    _axes.set(xlabel="median time vs Germans of same sex & age (%)", ylabel="",
              title="Country effect (top 15 by finishers)")
    save_figure(_figure, "countries_vs_germany")
    return (country_vs_germany,)


@app.cell
def _(country_vs_germany):
    country_vs_germany
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q8 · Pacing consistency: does even pacing go with faster times?

    Pace variation = coefficient of variation (std / mean) of the 9 segment paces; 0 = perfectly even.
    """)
    return


@app.cell
def _(finishers_clean_splits, pl, plt, save_figure):
    _without_outliers = finishers_clean_splits.filter(pl.col("pace_variation") < 0.4)
    median_time_by_variation_decile = (
        _without_outliers.with_columns(
            (pl.col("pace_variation").rank() / pl.len() * 10).ceil().cast(pl.Int64).alias("decile")
        )
        .group_by("decile")
        .agg(pl.col("pace_variation").median(), pl.col("net_time").median(), pl.len().alias("runners"))
        .sort("pace_variation")
    )
    _figure, _axes = plt.subplots(figsize=(10, 6))
    _density = _axes.hexbin(_without_outliers["pace_variation"] * 100, _without_outliers["net_time"],
                            gridsize=60, bins="log", cmap="viridis")
    _axes.plot(median_time_by_variation_decile["pace_variation"] * 100,
               median_time_by_variation_decile["net_time"],
               color="orange", marker="o", lw=2, label="median per decile")
    _axes.set(xlabel="pace variation (%)", ylabel="net time (min)", title="Even pacing vs finish time")
    _axes.legend()
    _figure.colorbar(_density, ax=_axes, label="runners (log)")
    save_figure(_figure, "pacing_consistency")
    return (median_time_by_variation_decile,)


@app.cell
def _(finishers_clean_splits, median_time_by_variation_decile, pl):
    {
        "spearman_variation_vs_time": round(
            finishers_clean_splits.select(pl.corr("pace_variation", "net_time", method="spearman")).item(), 3
        ),
        "deciles": median_time_by_variation_decile,
    }
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q9 · Overtaking: who gains places between halfway and the finish?

    Places gained = place at halfway − final place (both within sex). Positive = moved up.
    """)
    return


@app.cell
def _(FINISH_TIME_GROUP_ORDER, finishers, pl, plt, save_figure, sns):
    _quartile_labels = {1: "1 most even", 2: "2", 3: "3", 4: "4 biggest slowdown"}
    places_gained = finishers.drop_nulls(["first_half_place", "place_in_sex", "split_ratio"]).with_columns(
        (pl.col("first_half_place") - pl.col("place_in_sex")).alias("places_gained"),
        (pl.col("split_ratio").rank() / pl.len() * 4).ceil().cast(pl.Int64)
        .replace_strict(_quartile_labels).alias("split_ratio_quartile"),
    )
    _figure, (_histogram_ax, _by_group_ax) = plt.subplots(1, 2, figsize=(14, 5))
    sns.histplot(places_gained.to_pandas(), x="places_gained", binrange=(-4000, 4000), bins=80,
                 color="C2", ax=_histogram_ax)
    _histogram_ax.axvline(0, color="black", lw=1)
    _histogram_ax.set(xlabel="places gained after halfway", title="Places gained / lost in the second half")
    sns.barplot(places_gained.to_pandas(), x="finish_time_group", y="places_gained", hue="split_ratio_quartile",
                order=FINISH_TIME_GROUP_ORDER, estimator="median", errorbar=None, ax=_by_group_ax)
    _by_group_ax.axhline(0, color="black", lw=1)
    _by_group_ax.set(xlabel="finish time", ylabel="median places gained", title="By finish time and pacing")
    _by_group_ax.legend(title="2nd half / 1st half")
    save_figure(_figure, "overtaking")
    return (places_gained,)


@app.cell
def _(pl, places_gained):
    {
        "gained_places_%": round((places_gained["places_gained"] > 0).mean() * 100, 1),
        "spearman_split_ratio_vs_places_gained": round(
            places_gained.select(pl.corr("split_ratio", "places_gained", method="spearman")).item(), 3
        ),
        "by_quartile": places_gained.group_by("split_ratio_quartile")
        .agg(pl.col("places_gained").median(), pl.len().alias("runners"))
        .sort("split_ratio_quartile"),
    }
    return


@app.cell
def _(mo):
    mo.md("""
    ## Q10 · Round targets: do finish times bunch just under 3:00, 3:30, 4:00 …?

    1-minute histogram of net times; and the last 12.2 km (30 km → finish) pace relative to the
    runner's average pace for those just under vs just over a target (± 3 min).
    """)
    return


@app.cell
def _(MARATHON_KM, finishers, pl, plt, save_figure, sns):
    _target_minutes = [180, 210, 240, 270, 300]
    _last_section_km = MARATHON_KM - 30
    _finishers_2_30_to_5_30 = finishers.filter(pl.col("net_time").is_between(150, 330)).with_columns(
        ((pl.col("split_finish") - pl.col("split_30km")) / _last_section_km
         / (pl.col("net_time") / MARATHON_KM)).alias("last_section_relative_pace")
    )
    _near_targets = pl.concat(
        _finishers_2_30_to_5_30.filter(pl.col("net_time").is_between(target - 3, target + 3)).with_columns(
            pl.lit(f"{target // 60}:{target % 60:02d}").alias("target"),
            pl.when(pl.col("net_time") < target).then(pl.lit("just under")).otherwise(pl.lit("just over"))
            .alias("side"),
        )
        for target in _target_minutes
    )
    finishers_near_targets = (
        _near_targets.group_by("target", "side")
        .agg(pl.len().alias("runners"), pl.col("last_section_relative_pace").median())
        .sort("target", "side", descending=[False, True])
    )

    _figure, (_histogram_ax, _comparison_ax) = plt.subplots(
        1, 2, figsize=(15, 5), gridspec_kw={"width_ratios": [2, 1]}
    )
    sns.histplot(_finishers_2_30_to_5_30.to_pandas(), x="net_time", binwidth=1, color="C0", ax=_histogram_ax)
    for _target in _target_minutes:
        _histogram_ax.axvline(_target, color="C3", lw=1, ls="--")
    _histogram_ax.set(xlabel="net time (min, 1-min bins)", title="Finish times bunch below round targets")
    sns.barplot(finishers_near_targets.to_pandas(), x="target", y="runners", hue="side",
                hue_order=["just under", "just over"], ax=_comparison_ax)
    _comparison_ax.set(xlabel="target", ylabel="finishers within 3 min", title="Just under vs just over")
    save_figure(_figure, "round_targets")
    return (finishers_near_targets,)


@app.cell
def _(finishers_near_targets, pl):
    finishers_near_targets.pivot(
        on="side", index="target", values=["runners", "last_section_relative_pace"]
    ).with_columns(
        (pl.col("runners_just under") / pl.col("runners_just over")).round(2).alias("ratio_under_to_over")
    )
    return


if __name__ == "__main__":
    app.run()
