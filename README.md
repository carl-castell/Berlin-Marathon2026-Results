# Berlin Marathon 2026 Results

Scraping and analysing the runner results of the BMW Berlin Marathon 2026:
51,347 runners and 509,480 split times from <https://berlin.r.mikatiming.com/2026/>,
stored in SQLite and analysed with Polars, seaborn and marimo.

| Part | What | Read |
|---|---|---|
| **Results** | research questions, plots, presentation (Data Science Marathon hand-in) | [notebooks/README.md](notebooks/README.md) |
| **Scraper** | how the data is collected: usage, options, database tables | [marathon_scraper/README.md](marathon_scraper/README.md) |

**Quick look without setup:** download [docs/SE_42.html](docs/SE_42.html) and open it in a browser.

The repository contains no scraped data, only code and aggregated results
(plots and summary tables in the exported notebook).

## Disclaimer

> [!WARNING]
> **Personal use only.**
> The results list is protected by copyright. According to the website, it may
> only be retrieved and viewed for private information purposes (see the notice
> on the results page and the terms and conditions of SCC EVENTS GmbH).
> Use this code only to scrape data for your own personal use. Do not publish,
> share or sell the scraped data, and do not use it commercially. Keep the
> request rate low (the default settings do) so the website isn't burdened.
> This project is not affiliated with SCC EVENTS GmbH or mika:timing GmbH.
> You are responsible for making sure your use complies with the website's terms.

## Setup

```bash
uv sync
```

Then: collect the data with the [scraper](marathon_scraper/README.md), and open the
notebooks as described in the [results README](notebooks/README.md).

## Repository layout

```text
marathon_scraper/   Scrapy project (spiders, pipelines, countries.csv)
scripts/            helper scripts (regenerate countries.csv and the world map shapes)
notebooks/          marimo notebooks + shared code (marathon_data.py, maps.py)
notebooks/geo/      world country shapes (GeoJSON, Natural Earth)
figures/            exported plots (PNG)
docs/               static HTML export of the presentation notebook + interactive maps
data/               SQLite database (not in the repo)
```

## Built with

| Tool | Purpose | License |
|---|---|---|
| [Scrapy](https://scrapy.org) | scraping | BSD-3-Clause |
| [Polars](https://pola.rs) | DataFrames | MIT |
| [marimo](https://marimo.io) | notebooks | Apache-2.0 |
| [seaborn](https://seaborn.pydata.org) / [matplotlib](https://matplotlib.org) | plots | BSD-3-Clause / PSF-based |
| [folium](https://python-visualization.github.io/folium/) | interactive world maps | MIT |
| [Natural Earth](https://www.naturalearthdata.com) | country shapes for the maps | public domain |
| [Rich](https://github.com/Textualize/rich) | console progress bar | MIT |
| [pycountry](https://github.com/pycountry/pycountry), [country_converter](https://github.com/IndEcol/country_converter) | generating `marathon_scraper/countries.csv` (dev only) | LGPL-2.1, GPL-3.0 |

## License

The code is licensed under the [MIT License](LICENSE) – © 2026 Carl Castell.
This does not cover the scraped results data (see the disclaimer above).
