"""Build notebooks/geo/world_countries.geojson (country shapes for the world maps).

Dev tool, only needed to (re)generate the file:
    uv run python scripts/build_world_geojson.py

Source: Natural Earth 1:50m admin-0 countries (public domain, naturalearthdata.com),
GeoJSON version from github.com/nvkelso/natural-earth-vector. The 1:50m scale includes
small countries (Singapore, Hong Kong, Luxembourg, Malta, ...) that the 1:110m file drops.

To keep the file small, only two properties are kept and coordinates are rounded:
    iso3: ISO alpha-3 code (joins with countries.iso3 in the database)
    name: English country name
"""

import json
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "notebooks" / "geo" / "world_countries.geojson"
DECIMALS = 3  # ~100 m, plenty for a world map

# Natural Earth codes that differ from the ISO alpha-3 codes in the database
CODE_FIXES = {"KOS": "XKX"}  # Kosovo


def iso3_code(properties: dict) -> str:
    """ISO_A3 is -99 for some countries (France, Norway); ISO_A3_EH / ADM0_A3 fill the gaps."""
    for key in ("ISO_A3_EH", "ISO_A3", "ADM0_A3"):
        code = properties.get(key)
        if code and code != "-99":
            return CODE_FIXES.get(code, code)
    raise ValueError(f"no code for {properties.get('NAME')}")


def round_coordinates(coordinates):
    """Round all numbers in a (nested) coordinate list."""
    if isinstance(coordinates[0], (int, float)):
        return [round(value, DECIMALS) for value in coordinates]
    return [round_coordinates(part) for part in coordinates]


def main() -> None:
    with urllib.request.urlopen(SOURCE_URL) as response:
        source = json.load(response)

    features = [
        {
            "type": "Feature",
            "properties": {"iso3": iso3_code(feature["properties"]), "name": feature["properties"]["NAME"]},
            "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": round_coordinates(feature["geometry"]["coordinates"]),
            },
        }
        for feature in source["features"]
    ]
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(f"{len(features)} countries -> {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
