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
    return clean, load_runners_raw, show_table


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
def _(runners, show_table):
    show_table(runners)
    return


if __name__ == "__main__":
    app.run()
