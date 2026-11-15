"""World maps (folium choropleths) for the notebooks in this folder.

    world_map = country_map(values_per_country, color_column="finishers", colormap=..., tooltip_columns={...})
    map_view = show_map(world_map)                                   # display in marimo (call before save_map)
    legend = color_legend(colormap, "finishers", {1: "1", 10: "10"})  # small legend bar below the map
    save_map(world_map, "runners_per_country", legend=colormap)      # -> docs/maps/runners_per_country.html

Country shapes: Natural Earth 1:50m (public domain), prepared by scripts/build_world_geojson.py.
Countries are matched by ISO alpha-3 code (column `iso3`).
"""

import json
from functools import cache
from pathlib import Path

import folium
import marimo as mo
import polars as pl
from branca.colormap import StepColormap

WORLD_GEOJSON_PATH = Path(__file__).resolve().parent / "geo" / "world_countries.geojson"
MAPS_DIR = Path(__file__).resolve().parent.parent / "docs" / "maps"
NO_DATA_COLOR = "#e0e0e0"
WORLD_BOUNDS = [[-56, -170], [80, 190]]  # south-west, north-east corner (lat, lon); without Antarctica


@cache
def _world_geojson_text() -> str:
    return WORLD_GEOJSON_PATH.read_text()


def load_world_geojson() -> dict:
    """Country shapes as a GeoJSON dict (a fresh copy on every call, so it can be modified)."""
    return json.loads(_world_geojson_text())


def country_map(values_per_country: pl.DataFrame, color_column: str, colormap, tooltip_columns: dict[str, str]):
    """World map with each country coloured by `color_column`.

    values_per_country: one row per country with an `iso3` column
    colormap: a branca colormap (value -> colour)
    tooltip_columns: column -> label shown when hovering over a country
    Countries without a row are grey. The map always zooms to show the whole world,
    whatever size its frame has.
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
            "fillOpacity": 0.5 if value is None else 0.9,
            "color": "#999999",
            "weight": 0.5,
        }

    # no background tiles (most tile services need an API key): countries on a white background
    world_map = folium.Map(tiles=None, zoom_control=True, attribution_control=False,
                           scrollWheelZoom=False, zoom_snap=0.1)
    world_map.fit_bounds(WORLD_BOUNDS)
    folium.GeoJson(
        world,
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=["name", *tooltip_columns],
                                      aliases=["country", *tooltip_columns.values()]),
    ).add_to(world_map)

    root = world_map.get_root()
    root.header.add_child(folium.Element("<style>.leaflet-container {background: #ffffff !important;}</style>"))
    # refit whenever the frame changes size (slides are hidden at first, so the size starts at 0);
    # runs after the page has loaded, because folium creates the map later in the same script
    root.script.add_child(folium.Element(f"""
        document.addEventListener("DOMContentLoaded", function () {{
            var worldMap = {world_map.get_name()};
            new ResizeObserver(function () {{
                worldMap.invalidateSize();
                worldMap.fitBounds({WORLD_BOUNDS});
            }}).observe(worldMap.getContainer());
        }});
    """))
    return world_map


def show_map(world_map, height: str = "400px"):
    """Display a folium map in marimo with a fixed height."""
    return mo.iframe(world_map.get_root().render(), height=height)


def save_map(world_map, name: str, legend=None):
    """Save a map as a standalone page docs/maps/<name>.html, with the colormap as legend.

    Adds the legend to `world_map`, so call show_map() first if the slide should not show it.
    """
    if legend is not None:
        legend.add_to(world_map)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    world_map.save(MAPS_DIR / f"{name}.html")
    return world_map


def color_legend(colormap, title: str, tick_labels: dict[float, str]):
    """Small horizontal colour bar with labels, shown below a map in marimo.

    tick_labels: value -> label; for a StepColormap the values must be step boundaries.
    """
    if isinstance(colormap, StepColormap):
        # equal-width blocks, one per step
        steps = len(colormap.index) - 1
        stops = []
        for i in range(steps):
            color = colormap(colormap.index[i])
            stops += [f"{color} {i / steps:.0%}", f"{color} {(i + 1) / steps:.0%}"]

        def position(value):
            return colormap.index.index(value) / steps
    else:
        samples = 20
        stops = [
            f"{colormap(colormap.vmin + (colormap.vmax - colormap.vmin) * i / samples)} {i / samples:.0%}"
            for i in range(samples + 1)
        ]

        def position(value):
            return (value - colormap.vmin) / (colormap.vmax - colormap.vmin)

    labels = "".join(
        f'<span style="position:absolute; left:{position(value):.1%}; transform:translateX(-50%);">{label}</span>'
        for value, label in tick_labels.items()
    )
    return mo.Html(f"""
        <div style="width: 80%; margin: 4px auto 0; font-size: 12px;">
          <div style="text-align: center; margin-bottom: 2px;">{title}</div>
          <div style="height: 10px; border-radius: 2px; background: linear-gradient(to right, {', '.join(stops)});"></div>
          <div style="position: relative; height: 16px;">{labels}</div>
        </div>
    """)
