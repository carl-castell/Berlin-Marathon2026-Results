"""Wissen über die Webseite (URLs, Parameter, kleine Parse-Helfer).

An einem Ort gesammelt, damit beide Spider dasselbe verwenden. Für ein anderes
Jahr müssen meist nur YEAR und EVENT angepasst werden (EVENT findet man in den
Links der Ergebnisliste: "...&event=BML_...").
"""

from urllib.parse import urlencode

YEAR = 2026
EVENT = "BML_HCH3C0OH37C"  # "Läufer" (andere Events: Skater, Handbiker, ...)
BASE_URL = f"https://berlin.r.mikatiming.com/{YEAR}/"
PAGE_SIZE = 100  # mehr als 100 Ergebnisse pro Seite erlaubt die Seite nicht
LANG = "EN_CAP"  # feste Sprache, damit Texte wie "Finished" immer gleich sind


def list_url(sex: str, page: int) -> str:
    """URL einer Ergebnisseite, gefiltert nach Geschlecht."""
    params = {
        "pid": "list",
        "event": EVENT,
        "lang": LANG,
        "num_results": PAGE_SIZE,
        "search[sex]": sex,
        "page": page,
    }
    return BASE_URL + "?" + urlencode(params)


def detail_url(idp: str) -> str:
    """URL der Detailseite. Nur idp + event sind wirklich nötig."""
    return BASE_URL + "?" + urlencode(
        {"content": "detail", "idp": idp, "event": EVENT, "lang": LANG}
    )


def decode_silver(data_silver: str) -> str:
    """Dekodiert die 'versteckten' Links der Seite.

    Statt <a href="?page=2"> steht dort <a data-silver="63,112,97,...">.
    Das sind einfach ASCII-Codes: 63='?', 112='p', 97='a' ... -> "?page=2&amp;...".
    Ein Stück JavaScript baut daraus beim Klick den echten Link. Das soll
    simple Bots abhalten - für uns ist es eine Zeile Python.
    """
    return "".join(chr(int(c)) for c in data_silver.split(","))


def clean(text: str | None) -> str | None:
    """Whitespace entfernen; leere Werte und Platzhalter ('–', '-') -> None."""
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
