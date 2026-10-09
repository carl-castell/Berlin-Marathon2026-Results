"""Items = die Datenstrukturen, die unsere Spider erzeugen.

Scrapy akzeptiert dicts, scrapy.Item oder (wie hier) dataclasses. Dataclasses
sind am angenehmsten: feste Felder, Autovervollständigung in der IDE, und
Tippfehler bei Feldnamen fallen sofort auf.

Alle Zeiten speichern wir bewusst als Text ("02:02:50"), also genau so wie sie
auf der Seite stehen. Umwandeln (in Sekunden/Duration) machen wir später in
Polars. So geht beim Scrapen nichts verloren und Parsing-Fehler lassen sich
später korrigieren, ohne neu zu scrapen.
"""

from dataclasses import dataclass


@dataclass
class RunnerItem:
    """Eine Zeile aus der Ergebnisliste (Schritt 1)."""

    idp: str  # interne ID des Läufers bei mikatiming, eindeutig -> Primärschlüssel
    sex: str  # "M", "W" oder "X" (= divers), aus dem Listenfilter
    place_overall: int | None  # Platz innerhalb des Geschlechts
    place_ak: int | None  # Platz in der Altersklasse
    last_name: str  # Nachname
    first_name: str | None  # Vorname(n); fehlt bei manchen Einträgen
    nation: str | None  # "GER", "ETH", ...
    bib: str  # Startnummer (Text, da z.B. "F2" vorkommt)
    age_class: str  # AK, z.B. "35", "H" (Hauptklasse)
    club: str | None
    time_brutto: str | None  # Zeit ab Startschuss
    time_netto: str | None  # Zeit ab Überqueren der Startlinie
    detail_url: str
    list_page: int  # Seite der Liste, auf der der Läufer stand (zum Debuggen)


@dataclass
class DetailItem:
    """Zusätzliche Infos von der Detailseite eines Läufers (Schritt 2)."""

    idp: str
    status: str | None  # z.B. "Finished"
    last_split: str | None
    place_sex: int | None
    place_ak: int | None
    place_total: int | None  # Platz über alle Geschlechter
    time_netto: str | None
    time_brutto: str | None
    start_time_netto: str | None  # Tageszeit, zu der die Startlinie überquert wurde
    start_time_brutto: str | None
    hm1_time: str | None  # erste Hälfte
    hm1_place: int | None
    hm2_time: str | None  # zweite Hälfte
    hm2_place: int | None


@dataclass
class SplitItem:
    """Eine Zwischenzeit. Pro Läufer gibt es mehrere -> eigene Tabelle (long format)."""

    idp: str
    split_key: str  # stabiler Schlüssel aus der CSS-Klasse, z.B. "time_05", "time_finish_netto"
    split_name: str  # Anzeige-Text, z.B. "5 km", "Halb", "Finish"
    seq: int  # Reihenfolge auf der Seite
    time_of_day: str | None
    time: str | None  # kumulierte Zeit seit Start
    diff: str | None  # Zeit seit letztem Split
    pace_min_km: str | None
    kmh: float | None


@dataclass
class FailureItem:
    """Ein Request, der endgültig gescheitert ist (wird im errback erzeugt)."""

    url: str
    spider: str
    error: str
