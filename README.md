# Berlin Marathon 2026 – Results Scraper

Scrapes the runner results of the BMW Berlin Marathon 2026 from
<https://berlin.r.mikatiming.com/2026/> into a SQLite database and provides a
marimo notebook for analysis with Polars and seaborn.

The repository contains only code, no data.

> [!WARNING]
> **Disclaimer – personal use only.**
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

## Usage

```bash
# Step 1: all runners – finishers from the ranking, plus runners without a place
# (did not finish, did not start, ...) from the search view; ~1,000 pages, ~10 min
uv run scrapy crawl results_list

# Step 2: detail pages + splits, ~50,000 pages, ~4–4.5 h (only missing ones)
caffeinate -i uv run scrapy crawl results_detail

# Analysis
uv run marimo edit notebooks/analyse.py
```

Step 2 can be stopped with Ctrl-C and restarted at any time; it only fetches
runners without details.

Notebooks share their setup via `notebooks/marathon_data.py` (load, cleaning rules,
table display). New notebook: `cp notebooks/template.py notebooks/<name>.py`.

Options:

| Command | Effect |
|---|---|
| `-a sex=W` | only one category (`M`, `W`, `X`; default `M,W,X`) |
| `-a max_pages=2` | limit list pages per category and view (testing) |
| `-a unranked=false` | step 1: finishers only (skip the search view) |
| `-a ranked=false` | step 1: only runners without a place (skip the ranking) |
| `-a limit=20` | limit number of detail pages (testing) |
| `-s HTTPCACHE_ENABLED=False` | don't cache raw HTML in `.scrapy/` (~1.5 GB for a full run) |
| `-s PROGRESS_ENABLED=False -s LOG_FILE=` | plain Scrapy log output instead of the progress bar |

Full log: `logs/scrapy.log`. Failed requests: table `failures`.

## Output

`data/marathon.db`:

| Table | Content | Key |
|---|---|---|
| `runners` | finishers and runners without a place (place and times empty); place, place in age group, last/first name, nation, bib, age group, club, gun + net time, sex (`M`/`W`/`X` = diverse) | `idp`; `nation` → `countries.code` |
| `details` | status (`Finished`, `Did Not Finish`, `Not Started`, …), last split reached, place by sex/age group/overall, start times, half-marathon times + places | `idp` |
| `splits` | 5 km … 40 km, half, finish: time of day, time, diff, min/km, km/h (long format) | `idp`, `split_key` |
| `failures` | requests that failed in the last run | `url` |
| `countries` | country code as used by the site (IOC, else ISO alpha-3), ISO alpha-3/alpha-2, English + German name (250 rows, from `marathon_scraper/countries.csv`) | `code` |
| `runners_with_country` (view) | `runners` + `country_en`, `country_de`, `iso2`, `iso3` | |

All times are stored as text (`HH:MM:SS`).

```sql
SELECT country_de, count(*) FROM runners_with_country GROUP BY 1 ORDER BY 2 DESC;

-- status of all runners
SELECT status, count(*) FROM details GROUP BY 1;

-- where runners quit
SELECT last_split, count(*) FROM details WHERE status = 'Did Not Finish' GROUP BY 1;
```

Finishers only: `details.status = 'Finished'` (or `runners.place_overall IS NOT NULL`).

Add the `countries` table to a database created before it existed (backup first):

```bash
uv run python -m marathon_scraper.countries
```

Country codes that are not in `countries.csv` don't stop a scrape: the runner is
saved without a country name, a warning is shown per new code, and the summary
lists them ("Unknown countries"). The command above then exits with an error
listing the codes. Fix: add them to `EXTRA` in `scripts/build_countries.py` (or
directly to the CSV), regenerate, and run the command again.

Regenerate `countries.csv` (dev dependencies `pycountry`, `country_converter`):

```bash
uv run python scripts/build_countries.py
```

Check completeness (`missing_details` and `failures` must be 0):

```bash
sqlite3 -header -column data/marathon.db "
select (select count(*) from runners) runners,
       (select count(*) from details) details,
       (select count(*) from runners r where not exists
          (select 1 from details d where d.idp = r.idp)) missing_details,
       (select count(*) from splits) splits,
       (select count(*) from failures) failures;"
```

Backup:

```bash
sqlite3 data/marathon.db ".backup data/marathon_backup_$(date +%F).db"
```

## Findings (scraped 2026-10-09, unofficial results)

| | Men | Women | Diverse | Total |
|---|---|---|---|---|
| Finishers | 32,090 | 17,941 | 53 | **50,084** |
| Fastest | 2:02:50 | 2:11:04 | 2:54:26 | |
| Median | 3:58:48 | 4:30:57 | 4:21:45 | 4:11:20 |
| Slowest | 8:39:13 | 7:59:21 | 6:28:10 | |

- 167 nations; most runners from GER (17,108), USA (7,041), GBR (2,885), BRA (1,820), FRA (1,425).
- Under 3 h: 7.5 % · under 4 h: 43.2 % · under 5 h: 78.2 %.
- Negative split (second half faster): 10.3 % of runners; median second half is 8.9 % slower than the first.
- Start line crossings (net start) from 08:45:01 to 11:00:23.
- 1,122 runners have missing split / half-marathon times (finish time is always present).
- Tied times share a place and the next place is skipped; 13 further place numbers are missing from the site's list.
- The site's sex filter only accepts `M`, `W`, `X`; other values silently return the men's list.
