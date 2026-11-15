"""World maps (folium choropleths) for the notebooks in this folder.

    world_map = country_map(values_per_country, color_column="finishers", colormap=..., tooltip_columns={...})
    save_map(world_map, "runners_per_country")   # -> docs/maps/runners_per_country.html
    show_map(world_map)                          # display in marimo

Country shapes: Natural Earth 1:50m (public domain), prepared by scripts/build_world_geojson.py.
Countries are matched by ISO alpha-3 code (column `iso3`).
"""

import json
from functools import cache
from pathlib import Path

import folium
import marimo as mo
import polars as pl

WORLD_GEOJSON_PATH = Path(__file__).resolve().parent / "geo" / "world_countries.geojson"
MAPS_DIR = Path(__file__).resolve().parent.parent / "docs" / "maps"
NO_DATA_COLOR = "#e0e0e0"


@cache
def _world_geojson_text() -> str:
    return WORLD_GEOJSON_PATH.read_text()


def load_world_geojson() -> dict:
    """Country shapes as a GeoJSON dict (a fresh copy on every call, so it can be modified)."""
    return json.loads(_world_geojson_text())


def country_map(values_per_country: pl.DataFrame, color_column: str, colormap, tooltip_columns: dict[str, str]):
    """World map with each country coloured by `color_column`.

    values_per_country: one row per country with an `iso3` column
    colormap: a branca colormap (value -> colour), shown as the legend
    tooltip_columns: column -> label shown when hovering over a country
    Countries without a row are grey.
    """
    rows_by_iso3 = {row["iso3"]: row for row in values_per_country.iter_rows(named=True)}
    world = load_world_geojson()
    for feature in world["features"]:
        row = rows_by_iso3.get(feature["properties"]["iso3"], {})
        feature["properties"]["color_value"] = row.get(color_column)
        for column in tooltip_columns:
            value = row.get(column)
            feature["properties"][column] = f"{value:,}" if isinstance(value, int) else (value or "–")

    def style(feature):
        value = feature["properties"]["color_value"]
        return {
            "fillColor": NO_DATA_COLOR if value is None else colormap(value),
            "fillOpacity": 0.5 if value is None else 0.85,
            "color": "#999999",
            "weight": 0.5,
        }

    # no background tiles (most tile services need an API key): countries on a white background
    world_map = folium.Map(location=[30, 10], zoom_start=2, min_zoom=1, tiles=None,
                           scrollWheelZoom=False, world_copy_jump=True)
    world_map.get_root().header.add_child(folium.Element("<style>.leaflet-container {background: #ffffff;}</style>"))
    folium.GeoJson(
        world,
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=["name", *tooltip_columns],
                                      aliases=["country", *tooltip_columns.values()]),
    ).add_to(world_map)
    colormap.add_to(world_map)
    return world_map


def save_map(world_map, name: str):
    """Save a map as a standalone page docs/maps/<name>.html and return it."""
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    world_map.save(MAPS_DIR / f"{name}.html")
    return world_map


def show_map(world_map, height: str = "480px"):
    """Display a folium map in marimo with a fixed height."""
    return mo.iframe(world_map.get_root().render(), height=height)
