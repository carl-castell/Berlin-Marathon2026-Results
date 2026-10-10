"""Knowledge about the website (URLs, parameters, small parsing helpers).

Kept in one place so both spiders use the same values. For another year you
usually only need to change YEAR and EVENT (EVENT appears in the links of the
results list: "...&event=BML_...").
"""

from urllib.parse import urlencode

YEAR = 2026
EVENT = "BML_HCH3C0OH37C"  # "Runner" (other events: inline skaters, handbikers, ...)
BASE_URL = f"https://berlin.r.mikatiming.com/{YEAR}/"
PAGE_SIZE = 100  # the site does not allow more than 100 results per page
LANG = "EN_CAP"  # fixed language so texts like "Finished" are always the same


def list_url(sex: str, page: int) -> str:
    """URL of a results page, filtered by sex."""
    params = {
        "pid": "list",
        "event": EVENT,
        "lang": LANG,
        "num_results": PAGE_SIZE,
        "search[sex]": sex,
        "page": page,
    }
    return BASE_URL + "?" + urlencode(params)


def search_url(sex: str, page: int) -> str:
    """URL of a page of the search view: all entries, incl. runners without a place."""
    return list_url(sex, page).replace("pid=list", "pid=search", 1)


def detail_url(idp: str) -> str:
    """URL of the detail page. Only idp + event are actually required."""
    return BASE_URL + "?" + urlencode(
        {"content": "detail", "idp": idp, "event": EVENT, "lang": LANG}
    )


def decode_silver(data_silver: str) -> str:
    """Decode the site's "hidden" links.

    Instead of <a href="?page=2"> the site uses <a data-silver="63,112,97,...">.
    These are plain ASCII codes: 63='?', 112='p', 97='a' ... -> "?page=2&amp;...".
    A bit of JavaScript turns them into the real link on click. It is meant to
    stop simple bots - for us it is one line of Python.
    """
    return "".join(chr(int(c)) for c in data_silver.split(","))


def clean(text: str | None) -> str | None:
    """Normalize whitespace; empty values and placeholders ('–', '-') -> None."""
    if text is None:
        return None
    text = " ".join(text.split())
    return None if text in ("", "–", "-", "&ndash;") else text


def to_int(text: str | None) -> int | None:
    text = clean(text)
    try:
        return int(text.rstrip(".")) if text else None
    except ValueError:
        return None


def to_float(text: str | None) -> float | None:
    text = clean(text)
    try:
        return float(text) if text else None
    except ValueError:
        return None
