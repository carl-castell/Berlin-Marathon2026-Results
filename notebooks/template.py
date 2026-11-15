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
        add_analysis_columns,
        clean,
        format_time,
        load_runners_raw,
        save_figure,
        show_table,
    )

    sns.set_theme()
    return (
        AGE_CLASS_ORDER,
        FINISH_TIME_GROUP_ORDER,
        add_analysis_columns,
        clean,
        format_time,
        load_runners_raw,
        mo,
        pl,
        plt,
        save_figure,
        show_table,
        sns,
    )


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
def _(pl, runners):
    finishers = runners.filter(pl.col("result") == "finished")
    return (finishers,)


if __name__ == "__main__":
    app.run()
