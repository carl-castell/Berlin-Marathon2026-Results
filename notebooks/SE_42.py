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
        AGE_CLASS_LABELS,
        AGE_CLASS_ORDER,
        FINISH_TIME_GROUP_ORDER,
        MARATHON_KM,
        PACE_COLUMNS,
        SEGMENT_END_KM,
        add_analysis_columns,
        clean,
        format_time,
        load_runners_raw,
        run_sql,
        save_figure,
    )
    from maps import color_legend, country_map, save_map, show_map
    from branca.colormap import LinearColormap, StepColormap

    sns.set_theme()
    return (
        AGE_CLASS_LABELS,
        AGE_CLASS_ORDER,
        FINISH_TIME_GROUP_ORDER,
        LinearColormap,
        MARATHON_KM,
        PACE_COLUMNS,
        SEGMENT_END_KM,
        StepColormap,
        add_analysis_columns,
        clean,
        color_legend,
        country_map,
        format_time,
        load_runners_raw,
        mo,
        pl,
        plt,
        run_sql,
        save_figure,
        save_map,
        show_map,
        sns,
    )


@app.cell
def _(add_analysis_columns, clean, load_runners_raw):
    runners, cleaning_report = clean(load_runners_raw())
    runners = add_analysis_columns(runners)
    return cleaning_report, runners


@app.cell
def _(PACE_COLUMNS, pl, runners):
    finishers = runners.filter(pl.col("result") == "finished")

    # for comparisons by sex: M/W only (the diverse category X is too small)
    finishers_men_women = finishers.filter(pl.col("sex").is_in(["M", "W"]))

    # finishers whose segment paces are all present and plausible (2.5-20 min/km);
    # a few runners have missing or impossible splits (timing glitches)
    finishers_clean_splits = finishers_men_women.filter(
        pl.all_horizontal(pl.col(pace).is_between(2.5, 20) for pace in PACE_COLUMNS)
    )

    # everyone who started and was not disqualified; is_dropout = did not finish
    starters = runners.filter(pl.col("result").is_in(["finished", "dnf"])).with_columns(
        (pl.col("result") == "dnf").alias("is_dropout")
    )
    return finishers, finishers_clean_splits, finishers_men_women, starters


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Berlin Marathon 2026
    ## What 50,000 finishers tell us about pacing, age and the wall

    Data Science Marathon · final project · Carl Castell
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## How I got the data

    - **Source:** official results of the BMW Berlin Marathon 2026, timing by mika:timing,
      <https://berlin.r.mikatiming.com/2026/> (results © SCC EVENTS GmbH)
    - **Scraper:** my own [Scrapy](https://scrapy.org) project in this repo
        1. *results list*: all runners from the ranking + the search view (DNF, DNS …), ~1,000 pages, ~10 min
        2. *detail pages*: status, start time, halves and all splits, ~51,000 pages, ~4.5 h
    - polite crawling: max. 4 parallel requests, delay + auto-throttle, HTML cache, restartable
    - stored in **SQLite**, analysed with **Polars**, plotted with **seaborn/matplotlib**, presented in **marimo**
    - country codes → names via `pycountry` / `country_converter`

    *Data is for personal / educational use only and is not published in the repo.*
    """)
    return


@app.cell(hide_code=True)
def _(mo, run_sql, runners):
    _table_sizes = run_sql("""
        SELECT 'runners' AS "table", count(*) AS rows, 'one row per runner: name, nation, age class, club, times, place' AS content FROM runners
        UNION ALL SELECT 'details', count(*), 'status, start time, half-marathon times and places' FROM details
        UNION ALL SELECT 'splits', count(*), '10 timing points per runner: 5 km … 40 km, half, finish' FROM splits
        UNION ALL SELECT 'countries', count(*), 'country code → English/German name, ISO codes' FROM countries
    """)
    _split_rows = _table_sizes.filter(_table_sizes["table"] == "splits")["rows"].item()
    mo.vstack([
        mo.md("## The dataset"),
        mo.hstack([
            mo.stat(f"{runners.height:,}", label="runners", bordered=True),
            mo.stat(f"{_split_rows:,}", label="split times", bordered=True),
            mo.stat(f"{runners.width}", label="columns after joining", bordered=True),
        ], justify="start"),
        _table_sizes,
    ])
    return


@app.cell(hide_code=True)
def _(mo, pl, runners):
    _result_labels = {
        "finished": "finished",
        "dnf": "did not finish",
        "dsq": "disqualified",
        "dns": "listed as not started",
    }
    runners_by_result = (
        runners.filter(pl.col("result").is_in(list(_result_labels)))
        .group_by("result")
        .agg(
            pl.len().alias("total"),
            (pl.col("sex") == "M").sum().alias("men"),
            (pl.col("sex") == "W").sum().alias("women"),
            (pl.col("sex") == "X").sum().alias("diverse"),
        )
        .with_columns(pl.col("result").replace_strict(_result_labels))
        .sort("total", descending=True)
    )
    _starters = runners.filter(pl.col("result").is_in(["finished", "dnf", "dsq"])).height
    _finished_row = runners_by_result.filter(pl.col("result") == "finished")
    _finisher_count = _finished_row["total"].item()
    _women_finishers = _finished_row["women"].item()
    mo.vstack([
        mo.md("## Quick facts"),
        mo.hstack([
            mo.stat(f"{_starters:,}", label="starters", bordered=True),
            mo.stat(f"{_finisher_count:,}", label="finishers",
                    caption=f"{_finisher_count / _starters:.1%} of starters", bordered=True),
            mo.stat(f"{_women_finishers / _finisher_count:.0%}", label="women among finishers", bordered=True),
            mo.stat(f"{runners['nation_code'].n_unique()}", label="nationalities", bordered=True),
        ], justify="start"),
        runners_by_result,
    ])
    return


@app.cell
def _(finishers, format_time, pl):
    # elite-level times: men under 2:30, women under 2:50
    _is_elite_time = ((pl.col("sex") == "M") & (pl.col("net_time") < 150)) | (
        (pl.col("sex") == "W") & (pl.col("net_time") < 170)
    )
    finishers_per_country = (
        finishers.group_by("iso3", "country")
        .agg(
            pl.len().alias("finishers"),
            (pl.col("sex") == "M").sum().alias("men"),
            (pl.col("sex") == "W").sum().alias("women"),
            (pl.col("sex") == "X").sum().alias("diverse"),
            pl.col("net_time").median().alias("median_minutes"),
            # middle 50% of runners: from the 25% to the 75% quantile
            pl.col("net_time").quantile(0.25).alias("quantile_25_minutes"),
            pl.col("net_time").quantile(0.75).alias("quantile_75_minutes"),
            (_is_elite_time.mean() * 100).alias("elite_share_%"),
        )
        .with_columns(
            pl.col("median_minutes").map_elements(format_time, return_dtype=pl.String).alias("median_time"),
            pl.concat_str(
                pl.col("quantile_25_minutes").map_elements(format_time, return_dtype=pl.String),
                pl.col("quantile_75_minutes").map_elements(format_time, return_dtype=pl.String),
                separator=" – ",
            ).alias("middle_50_percent"),
        )
        .sort("finishers", descending=True)
    )
    return (finishers_per_country,)


@app.cell(hide_code=True)
def _(
    StepColormap,
    color_legend,
    country_map,
    finishers,
    finishers_per_country,
    mo,
    pl,
    plt,
    save_figure,
    save_map,
    show_map,
    sns,
):
    # log scale: Germany alone has more than 17,000 finishers
    _finishers_colormap = StepColormap(
        colors=["#deebf7", "#9ecae1", "#4292c6", "#2171b5", "#08306b"],
        index=[1, 10, 100, 1_000, 10_000, 20_000], vmin=1, vmax=20_000,
        caption="finishers per country (1 · 10 · 100 · 1,000 · 10,000)",
    )
    _runners_map = country_map(finishers_per_country, color_column="finishers", colormap=_finishers_colormap,
                               tooltip_columns={"finishers": "finishers", "men": "men", "women": "women",
                                                "diverse": "diverse"})
    _runners_map_view = show_map(_runners_map)
    _runners_legend = color_legend(_finishers_colormap, "finishers per country",
                                   {1: "1", 10: "10", 100: "100", 1_000: "1,000", 10_000: "10,000", 20_000: ""})
    save_map(_runners_map, "runners_per_country", legend=_finishers_colormap)

    _top_countries = finishers_per_country.head(10)
    _figure, _axes = plt.subplots(figsize=(6, 4.5))
    sns.barplot(_top_countries.to_pandas(), x="finishers", y="country", color="C0", ax=_axes)
    _axes.bar_label(_axes.containers[0], fmt="{:,.0f}", padding=3)
    _axes.set(xlabel="finishers", ylabel="", title="Top 10 countries by finishers")
    _axes.set_xlim(0, _top_countries["finishers"].max() * 1.2)
    save_figure(_figure, "se42_countries")

    _german_share = finishers.filter(pl.col("nation_code") == "GER").height / finishers.height
    mo.vstack([
        mo.md(f"""
        ## Where do the runners come from?

        {finishers_per_country.height} nations · only **{_german_share:.0%}** of finishers are German
        """),
        mo.hstack([mo.vstack([_runners_map_view, _runners_legend]), _figure], widths=[3, 2], align="center"),
    ])
    return


@app.cell(hide_code=True)
def _(
    LinearColormap,
    color_legend,
    country_map,
    finishers_per_country,
    mo,
    pl,
    plt,
    save_figure,
    save_map,
    show_map,
    sns,
):
    _minimum_finishers = 10
    _countries_with_enough_runners = finishers_per_country.filter(pl.col("finishers") >= _minimum_finishers)

    # smooth gradient purple (fastest) -> red -> orange -> yellow (slowest);
    # values outside 3:20-5:00 get the end colours
    _median_colormap = LinearColormap(
        colors=["#5B1A8C", "#E31A1C", "#FD8D3C", "#FFE135"],
        vmin=200, vmax=300,
        caption=f"median finish time in minutes (countries with ≥ {_minimum_finishers} finishers)",
    )
    _median_map = country_map(_countries_with_enough_runners, color_column="median_minutes",
                              colormap=_median_colormap,
                              tooltip_columns={"median_time": "median time",
                                               "middle_50_percent": "middle 50% of runners",
                                               "finishers": "finishers"})
    _median_map_view = show_map(_median_map)
    _median_legend = color_legend(
        _median_colormap, f"median finish time (countries with ≥ {_minimum_finishers} finishers; grey = fewer)",
        {200: "≤ 3:20", 225: "3:45", 250: "4:10", 275: "4:35", 300: "≥ 5:00"},
    )
    save_map(_median_map, "median_time_per_country", legend=_median_colormap)

    _fastest_countries = _countries_with_enough_runners.sort("median_minutes").head(10)
    _figure, _axes = plt.subplots(figsize=(6, 4.5))
    sns.barplot(_fastest_countries.to_pandas(), x="median_minutes", y="country", color="#E31A1C", ax=_axes)
    _bar_labels = [
        f"{row['median_time']} · {row['finishers']} runners · {row['elite_share_%']:.0f}% elite"
        for row in _fastest_countries.iter_rows(named=True)
    ]
    _axes.bar_label(_axes.containers[0], labels=_bar_labels, padding=3, fontsize=8)
    _axes.set(xlabel="median finish time (min)", ylabel="", xlim=(0, 420),
              title=f"10 fastest countries (≥ {_minimum_finishers} finishers)")
    save_figure(_figure, "se42_fastest_countries")

    _fastest = _fastest_countries.row(0, named=True)
    _fastest_large = (
        finishers_per_country.filter(pl.col("finishers") >= 100).sort("median_minutes").head(2).rows(named=True)
    )
    _overall_elite_share = (
        (finishers_per_country["elite_share_%"] * finishers_per_country["finishers"]).sum()
        / finishers_per_country["finishers"].sum()
    )
    fastest_countries_finding = mo.md(f"""
    ## Fastest countries: findings

    - **{_fastest['country']}** is fastest (median {_fastest['median_time']}), but only {_fastest['finishers']} of its
      runners finished, and **{_fastest['elite_share_%']:.0f}%** of them ran elite times (overall: {_overall_elite_share:.1f}%).
    - Small delegations are often selected athletes, big ones are mostly amateurs:
      the fewer runners a country sends, the higher the share of professionals can be.
    - Among countries with ≥ 100 finishers, **{_fastest_large[0]['country']}** ({_fastest_large[0]['median_time']})
      and **{_fastest_large[1]['country']}** ({_fastest_large[1]['median_time']}) are fastest.

    *Elite = men under 2:30, women under 2:50.*
    """)
    mo.vstack([
        mo.md("## Where are runners fastest on average?"),
        mo.hstack([mo.vstack([_median_map_view, _median_legend]), _figure], widths=[3, 2], align="center"),
    ])
    return (fastest_countries_finding,)


@app.cell(hide_code=True)
def _(fastest_countries_finding):
    fastest_countries_finding
    return


@app.cell(hide_code=True)
def _(finishers, format_time, mo, pl):
    def _top_five(sex):
        return (
            finishers.filter(pl.col("sex") == sex)
            .sort("place_in_sex")
            .head(5)
            .select(
                pl.col("place_in_sex").alias("place"),
                pl.concat_str("first_name", "last_name", separator=" ").alias("name"),
                "country",
                pl.col("net_time").map_elements(format_time, return_dtype=pl.String).alias("time"),
            )
        )

    mo.vstack([
        mo.md("## The fastest: top 5"),
        mo.hstack([
            mo.vstack([mo.md("### Men"), _top_five("M")]),
            mo.vstack([mo.md("### Women"), _top_five("W")]),
        ], widths="equal"),
    ])
    return


@app.cell(hide_code=True)
def _(AGE_CLASS_ORDER, finishers, format_time, mo, pl, plt, save_figure, sns):
    _men_and_women = finishers.filter(pl.col("sex").is_in(["M", "W"]))
    _figure, _axes = plt.subplots(figsize=(11, 4.5))
    sns.countplot(_men_and_women.filter(pl.col("age_class").is_in(AGE_CLASS_ORDER)).to_pandas(),
                  x="age_class", hue="sex", hue_order=["M", "W"], order=AGE_CLASS_ORDER, ax=_axes)
    _axes.set(xlabel="age class (H = 20-29, 30 = 30-34, …)", ylabel="finishers", title="Finishers by age class")
    save_figure(_figure, "se42_age_distribution")

    _finish_times_by_sex = (
        _men_and_women.group_by("sex")
        .agg(
            pl.col("net_time").min().alias("fastest"),
            pl.col("net_time").median().alias("median"),
            pl.col("net_time").max().alias("slowest"),
            pl.col("net_time").filter(pl.col("age_class") == "80").min().alias("fastest 80+"),
            (pl.col("age_class") == "80").sum().alias("finishers 80+"),
        )
        .sort("sex")
        .with_columns(
            pl.col("fastest", "median", "slowest", "fastest 80+").map_elements(format_time, return_dtype=pl.String)
        )
    )
    mo.vstack([
        mo.md("## Who runs? Age and finish times"),
        _figure,
        _finish_times_by_sex,
        mo.md("*The site only gives age classes, so the oldest finishers are the 80+ class.*"),
    ])
    return


@app.cell(hide_code=True)
def _(cleaning_report, finishers, mo, pl, runners):
    _club_share = runners.filter(pl.col("club").is_not_null() & (pl.col("club") != "")).height / runners.height
    _start_times = finishers.filter(pl.col("start_line_time").str.contains(r"^\d"))["start_line_time"]
    mo.vstack([
        mo.md(f"""
        ## More facts & data quality

        - **{_club_share:.0%}** of runners list a running club
        - start window: **{_start_times.min()[:5]} – {_start_times.max()[:5]}**, runners start in waves
        - the site marks disqualified runners as *Finished*: recognised by the time "DSQ"
        - **{runners['age_class'].is_null().sum()}** runners without an age class
        - a few runners have missing or impossible splits (e.g. negative pace): excluded from pacing analyses

        Cleaning rules applied:
        """),
        cleaning_report,
    ])
    return


@app.cell(hide_code=True)
def _(
    AGE_CLASS_LABELS,
    AGE_CLASS_ORDER,
    finishers_men_women,
    format_time,
    mo,
    pl,
    plt,
    save_figure,
    sns,
):
    _with_age_class = finishers_men_women.filter(pl.col("age_class").is_in(AGE_CLASS_ORDER))
    _figure, _axes = plt.subplots(figsize=(13, 5))
    sns.boxplot(_with_age_class.to_pandas(), x="age_class", y="net_time", hue="sex", hue_order=["M", "W"],
                order=AGE_CLASS_ORDER, showfliers=False, ax=_axes)
    _axes.set(xlabel="age class (H = 20-29, 30 = 30-34, …)", ylabel="net time (min)",
              title="Finish time by age class and sex")
    save_figure(_figure, "se42_age_curve")

    # median finish time per age class and sex, and how much slower women are
    _median_by_age = (
        _with_age_class.group_by("age_class", "sex")
        .agg(pl.col("net_time").median().alias("median_time"))
        .pivot(on="sex", index="age_class", values="median_time")
        .with_columns(((pl.col("W") / pl.col("M") - 1) * 100).alias("women_slower_%"))
    )
    _fastest_men = _median_by_age.sort("M").row(0, named=True)
    _fastest_women = _median_by_age.sort("W").row(0, named=True)
    _gap_up_to_55 = _median_by_age.filter(pl.col("age_class").is_in(["H", "30", "35", "40", "45", "50", "55"]))["women_slower_%"]
    _gap_60_to_79 = _median_by_age.filter(pl.col("age_class").is_in(["60", "65", "70", "75"]))["women_slower_%"]

    age_curve_finding = mo.md(f"""
    ## 1 · Age curve: findings

    - Men are fastest at **{AGE_CLASS_LABELS[_fastest_men['age_class']]}** (median {format_time(_fastest_men['M'])}),
      women at **{AGE_CLASS_LABELS[_fastest_women['age_class']]}** (median {format_time(_fastest_women['W'])}).
      Under 30 is not the fastest age.
    - After that, finish times rise with age, but the spread within each class is large:
      age explains only part of the time.
    - Up to 55, women's median time is **{_gap_up_to_55.min():.0f}–{_gap_up_to_55.max():.0f}% slower** than men's;
      from 60 to 79 the gap shrinks to **{_gap_60_to_79.min():.0f}–{_gap_60_to_79.max():.0f}%**.
      Possibly the few older women who run a marathon are an especially fit group (few runners per class).
    """)
    age_curve_summary = (
        f"Fastest at {AGE_CLASS_LABELS[_fastest_men['age_class']]}; the gap between women and men shrinks "
        f"from {_gap_up_to_55.min():.0f}–{_gap_up_to_55.max():.0f}% to {_gap_60_to_79.min():.0f}–{_gap_60_to_79.max():.0f}% after 60."
    )
    mo.vstack([
        mo.md("## 1 · How do finish times change with age, and does the gap between women and men change?"),
        _figure,
    ])
    return age_curve_finding, age_curve_summary


@app.cell(hide_code=True)
def _(age_curve_finding):
    age_curve_finding
    return


@app.cell(hide_code=True)
def _(
    FINISH_TIME_GROUP_ORDER,
    finishers_men_women,
    mo,
    pl,
    plt,
    save_figure,
    sns,
):
    _with_halves = finishers_men_women.drop_nulls("split_ratio")
    _negative_split_by_group = (
        _with_halves.group_by("finish_time_group", "sex")
        .agg(((pl.col("split_ratio") < 1).mean() * 100).alias("negative_split_%"))
    )

    _figure, (_halves_ax, _share_ax) = plt.subplots(1, 2, figsize=(13, 5))
    _halves_ax.hexbin(_with_halves["first_half_time"], _with_halves["second_half_time"],
                      gridsize=60, bins="log", cmap="viridis", extent=(80, 220, 80, 260))
    _halves_ax.plot([80, 220], [80, 220], color="white", lw=1.5, ls="--", label="even split")
    _halves_ax.set(xlabel="first half (min)", ylabel="second half (min)", title="First vs second half (each hexagon = runners)")
    _halves_ax.legend(loc="upper left")
    sns.barplot(_negative_split_by_group.to_pandas(), x="finish_time_group", y="negative_split_%",
                hue="sex", hue_order=["M", "W"], order=FINISH_TIME_GROUP_ORDER, ax=_share_ax)
    _share_ax.set(xlabel="finish time", ylabel="negative split (%)", title="Share running the second half faster")
    save_figure(_figure, "se42_negative_split")

    def _share(sex, group):
        return _negative_split_by_group.filter(
            pl.col("sex") == sex, pl.col("finish_time_group") == group
        )["negative_split_%"].item()

    _overall_share = (_with_halves["split_ratio"] < 1).mean() * 100
    _women_ahead_in_every_group = all(_share("W", group) > _share("M", group) for group in FINISH_TIME_GROUP_ORDER)

    negative_split_finding = mo.md(f"""
    ## 2 · Negative split: findings

    - Only **{_overall_share:.0f}%** of finishers run the second half faster than the first;
      most points in the left plot lie above the "even split" line.
    - The faster the runner, the more likely a negative split:
      **{_share('W', '<3:00'):.0f}%** of women under 3:00, but only **{_share('M', '>5:00'):.1f}%** of men over 5:00.
    - Women run a negative split more often than men {"in every finish-time group" if _women_ahead_in_every_group else "in most finish-time groups"}:
      they seem to pace more evenly.
    """)
    negative_split_summary = (
        f"Only {_overall_share:.0f}% run the second half faster: {_share('W', '<3:00'):.0f}% of women under 3:00, "
        f"{_share('M', '>5:00'):.1f}% of men over 5:00."
    )
    mo.vstack([mo.md("## 2 · Negative split: who runs the second half faster?"), _figure])
    return negative_split_finding, negative_split_summary


@app.cell(hide_code=True)
def _(negative_split_finding):
    negative_split_finding
    return


@app.cell(hide_code=True)
def _(
    FINISH_TIME_GROUP_ORDER,
    PACE_COLUMNS,
    SEGMENT_END_KM,
    finishers_clean_splits,
    mo,
    pl,
    save_figure,
    sns,
):
    # pace per segment divided by the runner's own 5-10 km pace (the first 5 km are crowded)
    _relative_pace_by_km = (
        finishers_clean_splits.select("runner_id", "sex", "finish_time_group", *PACE_COLUMNS)
        .with_columns(pl.col(pace) / pl.col("pace_km_5_10") for pace in PACE_COLUMNS)
        .unpivot(index=["runner_id", "sex", "finish_time_group"],
                 variable_name="segment", value_name="relative_pace")
        .with_columns(pl.col("segment").replace_strict(SEGMENT_END_KM).alias("segment_end_km"))
        .group_by("sex", "finish_time_group", "segment_end_km")
        .agg(pl.col("relative_pace").mean())
    )
    _grid = sns.relplot(_relative_pace_by_km.to_pandas(), x="segment_end_km", y="relative_pace",
                        hue="finish_time_group", col="sex", kind="line", marker="o",
                        hue_order=FINISH_TIME_GROUP_ORDER, height=4.5, aspect=1.2)
    _grid.set_axis_labels("segment end (km)", "pace relative to 5-10 km (1.0 = same)")
    _grid.figure.suptitle("Pace over the course", y=1.03)
    save_figure(_grid.figure, "se42_wall")

    def _slowdown_percent(sex, group, segment_end_km):
        return (_relative_pace_by_km.filter(
            pl.col("sex") == sex, pl.col("finish_time_group") == group, pl.col("segment_end_km") == segment_end_km
        )["relative_pace"].item() - 1) * 100

    _women_fade_less = all(
        _slowdown_percent("W", group, 40) < _slowdown_percent("M", group, 40) for group in FINISH_TIME_GROUP_ORDER
    )
    _largest_change_at_15_km = (_relative_pace_by_km.filter(pl.col("segment_end_km") == 15)["relative_pace"] - 1).abs().max() * 100

    wall_finding = mo.md(f"""
    ## 3 · The wall: findings

    - Up to 15 km all groups hold their pace (within {_largest_change_at_15_km:.0f}%). After that, everyone slows down.
    - The slower the group, the earlier and harder the slowdown. At 35–40 km, men over 5:00 run
      **{_slowdown_percent('M', '>5:00', 40):.0f}% slower** than at 5–10 km, men under 3:00 only **{_slowdown_percent('M', '<3:00', 40):.0f}%**.
    - Women slow down {"less than men in every group" if _women_fade_less else "less than men in most groups"}
      (women over 5:00: {_slowdown_percent('W', '>5:00', 40):.0f}%).
    - The worst segment is 35–40 km; on the last 2 km everyone speeds up again: the finish line pulls.
    """)
    wall_summary = (
        f"Pace holds to 15 km, then drops; at 35–40 km men over 5:00 are {_slowdown_percent('M', '>5:00', 40):.0f}% slower, "
        f"men under 3:00 {_slowdown_percent('M', '<3:00', 40):.0f}%; women slow down less."
    )
    mo.vstack([mo.md("## 3 · Hitting the wall: where does the pace drop?"), _grid.figure])
    return wall_finding, wall_summary


@app.cell(hide_code=True)
def _(wall_finding):
    wall_finding
    return


@app.cell(hide_code=True)
def _(MARATHON_KM, finishers_men_women, mo, pl, plt, save_figure, sns):
    _target_minutes = [180, 210, 240, 270, 300]
    _last_section_km = MARATHON_KM - 30
    _finishers_2_30_to_5_30 = finishers_men_women.filter(pl.col("net_time").is_between(150, 330)).with_columns(
        # pace from 30 km to the finish relative to the runner's average pace (1.0 = same)
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
    _runners_near_targets = (
        _near_targets.group_by("target", "side")
        .agg(pl.len().alias("runners"), pl.col("last_section_relative_pace").median())
        .sort("target")
    )

    _figure, (_histogram_ax, _comparison_ax) = plt.subplots(
        1, 2, figsize=(15, 5), gridspec_kw={"width_ratios": [2, 1]}
    )
    sns.histplot(_finishers_2_30_to_5_30.to_pandas(), x="net_time", binwidth=1, color="C0", ax=_histogram_ax)
    for _target in _target_minutes:
        _histogram_ax.axvline(_target, color="C3", lw=1, ls="--")
    _histogram_ax.set(xlabel="net time (min, 1-min bins); dashed = 3:00, 3:30, 4:00, 4:30, 5:00",
                      ylabel="finishers", title="Finish times")
    sns.barplot(_runners_near_targets.to_pandas(), x="target", y="runners", hue="side",
                hue_order=["just under", "just over"], ax=_comparison_ax)
    _comparison_ax.set(xlabel="target", ylabel="finishers within 3 min", title="Just under vs just over")
    save_figure(_figure, "se42_round_targets")

    def _value(target, side, column):
        return _runners_near_targets.filter(pl.col("target") == target, pl.col("side") == side)[column].item()

    def _under_to_over(target):
        return _value(target, "just under", "runners") / _value(target, "just over", "runners")

    _targets_with_more_under = sum(_under_to_over(target) > 1 for target in _runners_near_targets["target"].unique())

    round_targets_finding = mo.md(f"""
    ## 4 · Round targets: findings

    - The histogram has clear spikes **just before** 3:00, 3:30 and 4:00, and drops right after them.
    - Within 3 minutes of a target, more runners finish just under than just over at
      **{_targets_with_more_under} of 5** targets: **{_under_to_over('3:00'):.1f}×** at 3:00 and **{_under_to_over('4:00'):.1f}×** at 4:00.
    - Runners just under 3:00 slowed down less in the last 12 km
      ({(_value('3:00', 'just under', 'last_section_relative_pace') - 1) * 100:.1f}% vs
      {(_value('3:00', 'just over', 'last_section_relative_pace') - 1) * 100:.1f}% slower than their average pace):
      consistent with a final push for the goal.
    """)
    round_targets_summary = (
        f"Finish times bunch just under round targets: {_under_to_over('3:00'):.1f}× more runners just under 3:00 "
        f"than just over, {_under_to_over('4:00'):.1f}× at 4:00."
    )
    mo.vstack([mo.md("## 4 · Round targets: do finish times bunch just under 3:00, 3:30, 4:00 …?"), _figure])
    return round_targets_finding, round_targets_summary


@app.cell(hide_code=True)
def _(round_targets_finding):
    round_targets_finding
    return


@app.cell(hide_code=True)
def _(AGE_CLASS_ORDER, mo, pl, plt, save_figure, sns, starters):
    _timing_points = ["before 5 km", "5 km", "10 km", "15 km", "20 km", "Halb", "25 km", "30 km", "35 km", "40 km"]
    _after_halfway = ["Halb", "25 km", "30 km", "35 km", "40 km"]  # "Halb" = half-marathon point
    _dropouts = starters.filter(pl.col("is_dropout")).with_columns(
        pl.col("last_split").fill_null("before 5 km")
    )
    _dropout_rate_by_age = (
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
    _where_ax.set(xlabel="last timing point reached (Halb = half marathon)", ylabel="dropouts", title="Where runners quit")
    _where_ax.tick_params(axis="x", rotation=45)
    sns.barplot(_dropout_rate_by_age.to_pandas(), x="age_class", y="dropout_rate_%", hue="sex",
                hue_order=["M", "W"], order=AGE_CLASS_ORDER, ax=_rate_ax)
    _rate_ax.set(xlabel="age class", ylabel="dropout rate (%)", title="Dropout rate by age and sex")
    sns.histplot(_finished_or_late_dropout.to_pandas(), x="first_half_time", hue="group", bins=40,
                 stat="density", common_norm=False, element="step", ax=_first_half_ax)
    _first_half_ax.set(xlabel="first-half time (min)", title="First half: finishers vs late quitters")
    save_figure(_figure, "se42_dropouts")

    _dropout_rate = starters["is_dropout"].mean() * 100
    _quit_at_halfway = _dropouts.filter(pl.col("last_split") == "Halb").height
    _is_65_or_older = pl.col("age_class").is_in(["65", "70", "75", "80"])
    _rate_65_plus = starters.filter(_is_65_or_older)["is_dropout"].mean() * 100
    _rate_under_65 = starters.filter(~_is_65_or_older)["is_dropout"].mean() * 100
    _median_first_half = _finished_or_late_dropout.group_by("group").agg(pl.col("first_half_time").median())

    def _first_half(group):
        return _median_first_half.filter(pl.col("group") == group)["first_half_time"].item()

    dropouts_finding = mo.md(f"""
    ## 5 · Dropouts: findings

    - Only **{_dropout_rate:.1f}%** of starters do not finish ({_dropouts.height} runners).
    - The most common place to quit is **halfway** ({_quit_at_halfway} runners, {_quit_at_halfway / _dropouts.height:.0%} of all dropouts):
      possibly a natural point to decide "that's enough".
    - The dropout rate is about the same up to 64 ({_rate_under_65:.1f}%), but **{_rate_65_plus:.1f}%** from 65 on.
    - "They started too fast" is **not confirmed**: runners who quit after halfway were *slower* in the first half
      (median {_first_half('quit after halfway'):.0f} min) than finishers ({_first_half('finished'):.0f} min).
      Their times are spread widely, so other reasons (injury, illness, the cut-off time) are more likely; the data cannot tell.
    """)
    dropouts_summary = (
        f"{_dropout_rate:.1f}% quit, most at halfway; {_rate_65_plus:.1f}% from 65 on; "
        f"starting too fast is not confirmed."
    )
    mo.vstack([mo.md("## 5 · Dropouts: who quits, where, and did they start too fast?"), _figure])
    return dropouts_finding, dropouts_summary


@app.cell(hide_code=True)
def _(dropouts_finding):
    dropouts_finding
    return


@app.cell(hide_code=True)
def _(
    age_curve_summary,
    dropouts_summary,
    mo,
    negative_split_summary,
    round_targets_summary,
    wall_summary,
):
    mo.md(f"""
    ## Summary

    1. **Age:** {age_curve_summary}
    2. **Negative split:** {negative_split_summary}
    3. **The wall:** {wall_summary}
    4. **Round targets:** {round_targets_summary}
    5. **Dropouts:** {dropouts_summary}

    *Also explored in `questions.py`: overtaking after halfway, start time, country effects, pacing consistency.*

    **Thank you!** Code: scraper + notebooks in this repo · data: berlin.r.mikatiming.com/2026
    """)
    return


if __name__ == "__main__":
    app.run()
