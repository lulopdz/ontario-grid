"""Build the static site into _site/: the pages in site/, one compact JSON per view in
_site/data/, the full CSVs in _site/download/, and plotly.js copied from the Python package
(so the page depends on no CDN).

    python build.py            # then open _site/index.html (or serve _site/)

JSON shape: {"t": [timestamps], "<series>": [values], ...}, columnar to keep it small.
Timestamps are the start of each IESO hour in market time (EST): hour ending 18 on
2026-10-30 is "2026-10-30 17:00". Charts show the last HOURLY_DAYS hourly; longer ranges
read the daily series."""
import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA, SITE, OUT = ROOT / "data", ROOT / "site", ROOT / "_site"
HOURLY_DAYS = 120
YEARLY = ("prices.csv", "generation.csv", "demand.csv", "interties.csv")  # data/<name>/YYYY.csv (see ingest/update.py)
FUELS = ["nuclear", "gas", "hydro", "wind", "solar", "biofuel"]
NEIGHBOURS = ["quebec", "new_york", "michigan", "minnesota", "manitoba"]


def read(name):
    """A dataset as one frame: data/<name>.csv, or every year of data/<name>/YYYY.csv joined."""
    folder = DATA / name.removesuffix(".csv")
    if folder.is_dir():
        df = pd.concat(pd.read_csv(f) for f in sorted(folder.glob("[0-9][0-9][0-9][0-9].csv")))
    else:
        df = pd.read_csv(DATA / name)
    df["t"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["he"] - 1, unit="h")
    return df


def columns(df, cols, digits=1):
    out = {"t": df["t"].dt.strftime("%Y-%m-%d %H:%M").tolist()}
    for c in cols:
        out[c] = [None if pd.isna(v) else round(float(v), digits) for v in df[c]]
    return out


def daily(df, cols, how="mean"):
    d = df.groupby(df["t"].dt.normalize())[cols].agg(how).reset_index()
    return d


def recent(df, days=HOURLY_DAYS):
    return df[df["t"] >= df["t"].max().normalize() - pd.Timedelta(days=days)]


def write(name, obj):
    path = OUT / "data" / name
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
    return path.stat().st_size


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)
    (OUT / "data").mkdir()
    (OUT / "download").mkdir()
    for csv in DATA.glob("*.csv"):
        shutil.copy(csv, OUT / "download" / csv.name)
    for name in YEARLY:  # kept one file per year in data/, offered whole
        read(name).drop(columns="t").to_csv(OUT / "download" / name, index=False)
    import plotly
    (OUT / "vendor").mkdir()
    shutil.copy(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", OUT / "vendor" / "plotly.min.js")

    sizes = {}
    meta = {"built_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")}

    # Prices: one file per zone (hourly, whole history -- it starts 2025-05-20).
    p = read("prices.csv")
    p["dart"] = p["da"] - p["rt"]
    zones = sorted(p["zone"].unique())
    for z in zones:
        sizes[f"prices_{z}"] = write(f"prices_{z}.json", columns(p[p["zone"] == z].sort_values("t"), ["da", "rt", "dart"], 2))
    meta["zones"] = zones
    meta["prices_last_rt"] = p.loc[p["rt"].notna(), "t"].max().strftime("%Y-%m-%d %H:%M")
    meta["prices_last_da"] = p.loc[p["da"].notna(), "t"].max().strftime("%Y-%m-%d")

    # Generation: hourly for the recent window, daily averages for the whole history.
    g = read("generation.csv").sort_values("t")
    sizes["generation_hourly"] = write("generation_hourly.json", columns(recent(g), FUELS, 0))
    sizes["generation_daily"] = write("generation_daily.json", columns(daily(g, FUELS), FUELS, 0))
    meta["generation_last"] = g["t"].max().strftime("%Y-%m-%d %H:%M")

    # Demand: actual against the day-ahead forecast (hourly), and daily peak/average since 2018.
    d = read("demand.csv").sort_values("t")
    a = read("adequacy.csv")[["t", "forecast_demand", "supply_capacity", "requirement", "excess_capacity"]]
    dh = recent(d).merge(a, on="t", how="left")
    sizes["demand_hourly"] = write("demand_hourly.json", columns(dh, ["ontario_demand", "market_demand", "forecast_demand"], 0))
    dd = d.groupby(d["t"].dt.normalize()).agg(peak=("ontario_demand", "max"), avg=("ontario_demand", "mean")).reset_index()
    sizes["demand_daily"] = write("demand_daily.json", columns(dd, ["peak", "avg"], 0))
    meta["demand_last"] = d["t"].max().strftime("%Y-%m-%d %H:%M")

    # Interties: net flow by neighbour (positive = Ontario exports).
    i = read("interties.csv").sort_values("t")
    flows = [f"{n}_flow" for n in NEIGHBOURS] + ["total_flow"]
    sizes["interties_hourly"] = write("interties_hourly.json", columns(recent(i), flows, 0))
    sizes["interties_daily"] = write("interties_daily.json", columns(daily(i, flows), flows, 0))
    meta["interties_last"] = i["t"].max().strftime("%Y-%m-%d %H:%M")

    # Adequacy: day-ahead history and the outlook for the coming week.
    adq_cols = ["forecast_demand", "supply_capacity", "requirement", "excess_capacity"]
    sizes["adequacy_history"] = write("adequacy_history.json", columns(read("adequacy.csv").sort_values("t"), adq_cols, 0))
    o = read("adequacy_outlook.csv").sort_values("t")
    sizes["adequacy_outlook"] = write("adequacy_outlook.json", {**columns(o, adq_cols, 0), "created_at": o["created_at"].max()})

    write("meta.json", meta)
    total = sum(sizes.values())
    print(f"Built {OUT}: {len(sizes)} data files, {total / 1e6:.1f} MB")
    for k, v in sorted(sizes.items(), key=lambda x: -x[1])[:5]:
        print(f"  {k}: {v / 1e3:.0f} KB")


if __name__ == "__main__":
    build()
