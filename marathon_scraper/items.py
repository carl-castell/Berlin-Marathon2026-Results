"""Items = the data structures our spiders produce.

Scrapy accepts dicts, scrapy.Item or (as here) dataclasses. Dataclasses are the
most pleasant: fixed fields, autocompletion in the IDE, and typos in field
names show up immediately.

All times are deliberately stored as text ("02:02:50"), exactly as they appear
on the site. Converting them (to seconds/durations) happens later in Polars.
That way nothing is lost while scraping, and parsing mistakes can be fixed
later without scraping again.
"""

from dataclasses import dataclass


@dataclass
class RunnerItem:
    """One row of the results list (step 1)."""

    idp: str  # mikatiming's internal runner ID, unique -> primary key
    sex: str  # "M", "W" or "X" (= diverse), from the list filter
    place_overall: int | None  # place within the runner's sex
    place_ak: int | None  # place within the age group
    last_name: str
    first_name: str | None  # missing for some entries
    nation: str | None  # "GER", "ETH", ...
    bib: str  # bib number (text, because values like "F2" exist)
    age_class: str  # age group, e.g. "35", "H" (main class)
    club: str | None
    time_brutto: str | None  # gun time (from the starting gun)
    time_netto: str | None  # net time (from crossing the start line)
    detail_url: str
    list_page: int  # list page the runner was on (for debugging)


@dataclass
class DetailItem:
    """Additional info from a runner's detail page (step 2)."""

    idp: str
    status: str | None  # e.g. "Finished"
    last_split: str | None
    place_sex: int | None
    place_ak: int | None
    place_total: int | None  # place across all sexes
    time_netto: str | None
    time_brutto: str | None
    start_time_netto: str | None  # time of day the runner crossed the start line
    start_time_brutto: str | None
    hm1_time: str | None  # first half
    hm1_place: int | None
    hm2_time: str | None  # second half
    hm2_place: int | None


@dataclass
class SplitItem:
    """One split time. Each runner has several -> separate table (long format)."""

    idp: str
    split_key: str  # stable key from the CSS class, e.g. "time_05", "time_finish_netto"
    split_name: str  # display text, e.g. "5 km", "Halb", "Finish"
    seq: int  # order on the page
    time_of_day: str | None
    time: str | None  # cumulative time since the start
    diff: str | None  # time since the previous split
    pace_min_km: str | None
    kmh: float | None


@dataclass
class FailureItem:
    """A request that failed for good (created in the errback)."""

    url: str
    spider: str
    error: str
