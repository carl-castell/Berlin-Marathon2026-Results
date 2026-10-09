"""Build marathon_scraper/countries.csv (country code -> English + German name).

Dev tool, only needed to (re)generate the CSV:
    uv run python scripts/build_countries.py

The results site uses IOC codes (GER, SUI, RSA, ...) and falls back to ISO
alpha-3 for territories without an IOC code (MTQ, VAT). So `code` is the IOC
code if one exists, otherwise the ISO alpha-3 code.

Sources: pycountry (ISO 3166 list + German translations) and
country_converter (ISO -> IOC mapping, short English names).
"""

import csv
import gettext
import sqlite3
import sys
from pathlib import Path

import country_converter as coco
import pycountry

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "marathon_scraper" / "countries.csv"
DB_PATH = ROOT / "data" / "marathon.db"

# Codes that are not ISO 3166 countries.
EXTRA = [
    {"code": "KOS", "iso3": "XKX", "iso2": "XK", "name_en": "Kosovo", "name_de": "Kosovo"},
]

# English names where country_converter abbreviates or uses an unusual form.
NAME_EN = {
    "FSM": "Micronesia",
    "SGS": "South Georgia and the South Sandwich Islands",
    "BLM": "Saint Barthélemy",
    "BRN": "Brunei",
    "COG": "Republic of the Congo",
}

# German names where the translated ISO name is awkward or official-sounding.
NAME_DE = {
    "KOR": "Südkorea",
    "PRK": "Nordkorea",
    "TWN": "Taiwan",
    "IRN": "Iran",
    "RUS": "Russland",
    "SYR": "Syrien",
    "VEN": "Venezuela",
    "BOL": "Bolivien",
    "TZA": "Tansania",
    "MDA": "Moldau",
    "LAO": "Laos",
    "VNM": "Vietnam",
    "FSM": "Mikronesien",
    "PSE": "Palästina",
    "VAT": "Vatikanstadt",
    "COD": "Demokratische Republik Kongo",
    "COG": "Republik Kongo",
    "BRN": "Brunei",
    "CPV": "Kap Verde",
    "CIV": "Elfenbeinküste",
    "MKD": "Nordmazedonien",
    "TUR": "Türkei",
    "CZE": "Tschechien",
    "VGB": "Britische Jungferninseln",
    "VIR": "Amerikanische Jungferninseln",
    "BES": "Bonaire, Sint Eustatius und Saba",
    "SHN": "St. Helena, Ascension und Tristan da Cunha",
}


def main() -> None:
    de = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["de"])
    cc = coco.CountryConverter()

    rows = []
    for c in pycountry.countries:
        ioc = cc.convert(c.alpha_3, src="ISO3", to="IOC", not_found=None)
        name_en = cc.convert(c.alpha_3, src="ISO3", to="name_short", not_found=None)
        if not isinstance(name_en, str):
            name_en = getattr(c, "common_name", c.name)
        rows.append(
            {
                "code": ioc if isinstance(ioc, str) else c.alpha_3,
                "iso3": c.alpha_3,
                "iso2": c.alpha_2,
                "name_en": NAME_EN.get(c.alpha_3, name_en),
                "name_de": NAME_DE.get(c.alpha_3) or de.gettext(c.name),
            }
        )
    rows += EXTRA
    rows.sort(key=lambda r: r["code"])

    codes = [r["code"] for r in rows]
    dupes = {c for c in codes if codes.count(c) > 1}
    if dupes:
        sys.exit(f"Duplicate codes: {sorted(dupes)}")

    # Every code that appears in the scraped data must be covered.
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            used = {r[0] for r in conn.execute("SELECT DISTINCT nation FROM runners WHERE nation IS NOT NULL")}
        missing = sorted(used - set(codes))
        if missing:
            sys.exit(f"Codes in runners without a country: {missing}")
        print(f"All {len(used)} codes used in runners are covered.")

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "iso3", "iso2", "name_en", "name_de"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} countries to {CSV_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
