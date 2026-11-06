"""Export the FSA map's numbers for desktop GIS (QGIS, ArcGIS): a GeoPackage that opens styled in
QGIS, the same layer as GeoJSON, one QGIS style (.qml) per metric and a README.

    python analysis/fsa_gis.py --out-dir /tmp/fsa_gis [--since 2026-02]

The metrics and their caveats are fsa_map.py's (see its docstring); this adds kWh per home for
each month. The colour classes match the web map (fsa_map_template.html, light theme): keep the
two in step if either changes."""
import argparse
import sqlite3
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import geopandas as gpd

from fsa_map import MIN_HOMES, ROOT, metrics

LAYER = "fsa_residential"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV = ["#1c5cab", "#5598e7", "#b7d3f6", "#e6e4dd", "#f4b4a3", "#e5735f", "#b8322a"]
NO_DATA = "#e9ebe9"
STYLES = {  # field: (title, thresholds between the 7 classes, ramp, unit)
    "kwh_home": ("kWh per home per month", [450, 600, 700, 800, 950, 1150], SEQ, "kWh"),
    "summer_ratio": ("Summer vs winter (kWh per home, last month / first)", [0.7, 0.8, 0.9, 1.1, 1.3, 1.6], DIV, "x"),
    "density": ("Homes per km2 of land", [5, 25, 100, 500, 1500, 4000], SEQ, ""),
}


def layer(since):
    data, months, first, last, monthly = metrics(since)
    gdf = gpd.read_file(ROOT / "geo" / "fsa_ontario_2021.geojson")[["fsa", "land_km2", "geometry"]]
    # Simplifying the boundaries left ~2% of them self-intersecting; GIS overlays reject those.
    gdf["geometry"] = gdf.geometry.make_valid().apply(_polygons)
    gdf = gdf.merge(data, left_on="fsa", right_index=True, how="left")
    gdf["density"] = (gdf["homes"] / gdf["land_km2"]).round(1)
    monthly.columns = [f"kwh_home_{m.replace('-', '_')}" for m in monthly.columns]
    gdf = gdf.merge(monthly, left_on="fsa", right_index=True, how="left")
    gdf["unstable"] = gdf["unstable"].fillna(False).astype(bool)
    cols = ["fsa", "homes", "kwh_home", "summer_ratio", "density", "land_km2", "unstable", *monthly.columns, "geometry"]
    return gdf[cols].set_crs(4326, allow_override=True), months, first, last


def _polygons(geom):
    """Keep the polygonal part of a repaired geometry (make_valid can add stray lines)."""
    from shapely.geometry import MultiPolygon, Polygon
    if isinstance(geom, (Polygon, MultiPolygon)):
        return MultiPolygon([geom]) if isinstance(geom, Polygon) else geom
    parts = [g for g in getattr(geom, "geoms", []) for g in (g.geoms if isinstance(g, MultiPolygon) else [g]) if isinstance(g, Polygon)]
    return MultiPolygon(parts)


def rgba(hexcolor):
    h = hexcolor.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4)) + ",255"


def qml(field, title, thresholds, ramp, unit):
    """A rule-based QGIS style: seven classes plus grey for no data (graduated renderers leave
    NULLs undrawn). Writes both the <prop> and the <Option> form so older and newer QGIS read it."""
    fmt = (lambda v: f"{v:g}{unit}") if unit == "x" else (lambda v: f"{v:,g} {unit}".strip())
    rules, symbols = [], []
    bounds = [None, *thresholds, None]
    for i, color in enumerate(ramp):
        lo, hi = bounds[i], bounds[i + 1]
        cond = [f'"{field}" >= {lo}' if lo is not None else None, f'"{field}" < {hi}' if hi is not None else None]
        expr = " AND ".join(c for c in cond if c) + f' AND "{field}" IS NOT NULL'
        label = f"< {fmt(hi)}" if lo is None else (f">= {fmt(lo)}" if hi is None else f"{fmt(lo)} - {fmt(hi)}")
        rules.append((expr, label, color))
    rules.append(("ELSE", f"No data or under {MIN_HOMES} homes", NO_DATA))
    for n, (_, _, color) in enumerate(rules):
        props = {"color": rgba(color), "outline_color": "255,255,255,255", "outline_style": "solid",
                 "outline_width": "0.1", "outline_width_unit": "MM", "style": "solid"}
        prop_xml = "".join(f'<prop k="{k}" v="{v}"/>' for k, v in props.items())
        opt_xml = "".join(f'<Option name="{k}" type="QString" value="{v}"/>' for k, v in props.items())
        symbols.append(f'<symbol type="fill" name="{n}" alpha="1" clip_to_extent="1" force_rhr="0">'
                       f'<layer class="SimpleFill" enabled="1" locked="0" pass="0"><Option type="Map">{opt_xml}</Option>'
                       f'{prop_xml}</layer></symbol>')
    rule_xml = "".join(f'<rule key="r{n}" filter={quoteattr(e)} symbol="{n}" label={quoteattr(lab)}/>'
                       for n, (e, lab, _) in enumerate(rules))
    return ("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
            f'<qgis version="3.28.0" styleCategories="Symbology">\n'
            f'<!-- {escape(title)} -->\n'
            '<renderer-v2 type="RuleRenderer" symbollevels="0" enableorderby="0" forceraster="0">'
            f'<rules key="root">{rule_xml}</rules><symbols>{"".join(symbols)}</symbols></renderer-v2>\n</qgis>\n')


def embed_styles(gpkg, styles, default):
    """QGIS reads a GeoPackage's layer_styles table; the default style opens with the layer."""
    with sqlite3.connect(gpkg) as con:
        geom = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?", (LAYER,)).fetchone()[0]
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT,
            f_table_catalog TEXT, f_table_schema TEXT, f_table_name TEXT, f_geometry_column TEXT, styleName TEXT,
            styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT, ui TEXT,
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        for field, text in styles.items():
            con.execute("INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                        "styleName, styleQML, styleSLD, useAsDefault, description) VALUES ('', '', ?, ?, ?, ?, '', ?, ?)",
                        (LAYER, geom, field, text, field == default, STYLES[field][0]))


README = """Ontario residential electricity use by postal area (FSA)
========================================================

Files
  ontario_fsa_residential.gpkg     GeoPackage, layer "{layer}". Opens in QGIS coloured by kWh per
                                   home; the other styles are in Layer Properties > Style > Load Style
                                   (stored in the database).
  ontario_fsa_residential.geojson  The same layer for any other software.
  style_<field>.qml                The same colours as files (QGIS: Layer Properties > Style > Load Style).

Coordinates: WGS 84 (EPSG:4326). For areas or distances reproject, e.g. to Statistics Canada
Lambert (EPSG:3347).

Fields (residential customers only, {first} to {last})
  fsa              Forward Sortation Area: the first three characters of the postal code
  homes            mean number of residential premises
  kwh_home         mean monthly kWh per home
  summer_ratio     kWh per home in {last} divided by {first} (above 1: more in summer)
  density          homes per km2 of land
  land_km2         land area, Statistics Canada
  unstable         True when the home count moves more than 20% between months (see caveats)
  kwh_home_YYYY_MM kWh per home in each month

Caveats
  - Residential only: no industry or large commercial load; small business (<50 kW) is left out.
  - IESO folds FSA x price plan cells with few customers into two-character codes for privacy
    (~20% of all kWh). Per-home values hold; FSA totals would run short.
  - From {first}: IESO changed that privacy method on 2026-02-01 and home counts jump across it.
  - Empty values: no data, or fewer than {min_homes} homes.

Sources: IESO, Hourly Consumption by FSA (public report). Boundaries: Statistics Canada, 2021
Census cartographic boundary file for FSAs (Statistics Canada Open Licence), Ontario only,
simplified. Built by analysis/fsa_gis.py in github.com/lulopdz/ontario-grid.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--since", default="2026-02")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gdf, months, first, last = layer(args.since)
    gpkg = out / "ontario_fsa_residential.gpkg"
    gpkg.unlink(missing_ok=True)
    gdf.to_file(gpkg, layer=LAYER, driver="GPKG")
    gdf.to_file(out / "ontario_fsa_residential.geojson", driver="GeoJSON")
    styles = {f: qml(f, *spec) for f, spec in STYLES.items()}
    for field, text in styles.items():
        (out / f"style_{field}.qml").write_text(text)
    embed_styles(gpkg, styles, default="kwh_home")
    (out / "README.txt").write_text(README.format(layer=LAYER, first=first, last=last, min_homes=MIN_HOMES))
    print(f"{out}: {len(gdf)} FSAs, {gdf['kwh_home'].notna().sum()} with data, months {months[0]}..{months[-1]}")


if __name__ == "__main__":
    main()
