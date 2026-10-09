import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import sqlite3
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl
    import seaborn as sns

    # seaborn needs pandas: sns.histplot(df.to_pandas(), x="...")
    sns.set_theme()
    return Path, mo, pl, plt, sns, sqlite3


@app.cell
def _(Path, pl, sqlite3):
    DB = Path(__file__).resolve().parent.parent / "data" / "marathon.db"
    conn = sqlite3.connect(DB)


    def sql(query: str) -> pl.DataFrame:
        """Run a SQL query against marathon.db and return a Polars DataFrame."""
        return pl.read_database(query, conn)


    runners = sql("SELECT * FROM runners")
    details = sql("SELECT * FROM details")
    splits = sql("SELECT * FROM splits")
    countries = sql("SELECT * FROM countries")
    return conn, countries, details, runners, splits, sql


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
