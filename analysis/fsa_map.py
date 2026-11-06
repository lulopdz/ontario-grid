"""Choropleth of residential electricity use by postal area (FSA), from data/fsa_daily/ and the
StatCan 2021 FSA boundaries in geo/. Writes one self-contained HTML page (not part of the site).

    python analysis/fsa_map.py --out /tmp/fsa_map.html [--since 2026-02]

Metrics, residential customers only, over the months from --since on:
  kwh_home     mean monthly kWh per home
  summer_ratio kWh per home in the latest month against the first (2026-07 vs 2026-02: cooling vs
               heating). Only meaningful while the range spans a summer and a winter month.
  density      homes per km2 of land

Why per home: IESO moves any FSA x customer type x price plan cell with too few premises into a
two-character code (K0, M5, ...), ~20% of all kWh. Those premises leave an FSA's kWh and its
premise count together, so kWh per home holds while FSA totals run short. Why from 2026-02: IESO
changed that privacy method on 2026-02-01 and premise counts jump across the date."""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MIN_HOMES = 100  # fewer and one household's habits move the number


def metrics(since):
    d = pd.concat(pd.read_csv(f) for f in sorted((ROOT / "data" / "fsa_daily").glob("*.csv")))
    d["month"] = d["date"].str[:7]
    r = d[(d["customer_type"] == "Residential") & (d["month"] >= since) & (d["fsa"].str.len() == 3)]
    # Homes on a day = premises summed over price plans; a month's homes = mean over its days.
    daily = r.groupby(["fsa", "month", "date"]).agg(kwh=("kwh", "sum"), homes=("premises", "sum")).reset_index()
    m = daily.groupby(["fsa", "month"]).agg(kwh=("kwh", "sum"), homes=("homes", "mean")).reset_index()
    m["per_home"] = m["kwh"] / m["homes"]
    pv = m.pivot(index="fsa", columns="month", values="per_home")
    first, last = pv.columns.min(), pv.columns.max()
    homes = m.groupby("fsa")["homes"].mean()
    out = pd.DataFrame({
        "homes": homes.round(0),
        "kwh_home": pv.mean(axis=1).round(0),
        "summer_ratio": (pv[last] / pv[first]).round(2),
        # Premise counts that swing month to month mean IESO moved cells in and out of the FSA.
        "unstable": (m.groupby("fsa")["homes"].std() / homes > 0.2),
    })
    out.loc[out["homes"] < MIN_HOMES, ["kwh_home", "summer_ratio"]] = None
    months = sorted(m["month"].unique())
    pv.loc[homes[homes < MIN_HOMES].index] = None
    return out, months, first, last, pv.round(0)


def build(out_path, since):
    data, months, first, last, _ = metrics(since)
    geo = json.loads((ROOT / "geo" / "fsa_ontario_2021.geojson").read_text())
    for f in geo["features"]:
        p = f["properties"]
        row = data.loc[p["fsa"]] if p["fsa"] in data.index else None
        p["homes"] = None if row is None else float(row["homes"])
        p["kwh_home"] = None if row is None or pd.isna(row["kwh_home"]) else float(row["kwh_home"])
        p["summer_ratio"] = None if row is None or pd.isna(row["summer_ratio"]) else float(row["summer_ratio"])
        p["density"] = None if row is None or not p["land_km2"] else round(float(row["homes"]) / p["land_km2"], 1)
        p["unstable"] = bool(row["unstable"]) if row is not None else False
    meta = {"months": months, "first": first, "last": last, "min_homes": MIN_HOMES,
            "fsas": int(data["kwh_home"].notna().sum()), "homes": int(data["homes"].sum())}
    template = (Path(__file__).parent / "fsa_map_template.html").read_text()
    page = template.replace("/*__GEO__*/null", json.dumps(geo, separators=(",", ":"))).replace(
        "/*__META__*/null", json.dumps(meta))
    Path(out_path).write_text(page)
    print(f"{out_path}: {meta['fsas']} FSAs, {meta['homes']:,} homes, {months[0]}..{months[-1]}, {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2026-02", help="first month (YYYY-MM); 2026-02 avoids IESO's privacy-method change")
    args = ap.parse_args()
    build(args.out, args.since)
