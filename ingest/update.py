"""Bring data/*.csv up to date from IESO's public reports. Run every hour by the workflow.

    python ingest/update.py                       # incremental: re-checks the last WINDOW_DAYS
    python ingest/update.py --window 100          # backfill everything IESO still keeps (~3 months)
    python ingest/update.py --seed-prices DIR     # one-off: start prices.csv from lrg-dashboard's data/

Every pass re-requests what is *missing* inside the window instead of resuming from the last
stored hour, so an hour IESO published late (or a run that failed halfway) is filled on the
next pass rather than left as a permanent hole -- lrg-dashboard lost 2026-10-23 HE12 that way.

Files (all keyed by date + he, IESO market time = EST all year):
  prices.csv            date, he, zone, da, rt          nine virtual zonal hubs
  generation.csv        date, he, nuclear .. biofuel     MW by fuel
  demand.csv            date, he, ontario_demand, market_demand
  interties.csv         date, he, {neighbour}_import/_export/_flow
  adequacy.csv          date, he, forecast_demand, supply_capacity, requirement, excess_capacity,
                        created_at -- the last forecast published before the day began
  adequacy_outlook.csv  same columns, the latest forecast for today and the next six days"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ieso  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
WINDOW_DAYS = 7
FIRST_YEAR = 2018  # interties start here; generation and demand are trimmed to match


def load(name):
    path = DATA / name
    return pd.read_csv(path) if path.exists() else None


def save(df, name, keys):
    df = df.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    df.to_csv(DATA / name, index=False)
    print(f"  {name}: {len(df):,} rows, {df['date'].min()} .. {df['date'].max()}")


def merge(name, new, keys):
    old = load(name)
    if new is None or new.empty:
        return
    save(new if old is None else pd.concat([old, new]), name, keys)


def days(start, end):
    return list(pd.date_range(start, end).date)


# --- prices ----------------------------------------------------------------------------------

def update_prices(window):
    now = ieso.market_now()
    today = now.date()
    old = load("prices.csv")
    have_da = set() if old is None else set(old.loc[old["da"].notna(), "date"])
    have_rt = set() if old is None else set(zip(old.loc[old["rt"].notna(), "date"], old.loc[old["rt"].notna(), "he"]))
    start = today - pd.Timedelta(days=window)

    # Day-ahead: every day in the window plus tomorrow (out ~12:35 EST).
    frames = []
    for day in days(start, today + pd.Timedelta(days=1)):
        if f"{day:%Y-%m-%d}" not in have_da:
            df = ieso.da_prices(day)
            if df is not None:
                frames.append(df)
    da = pd.concat(frames) if frames else None

    # Real-time: every complete hour in the window. The current hour is still open.
    frames = []
    for day in days(start, today):
        last_he = now.hour if day == today else 24
        for he in range(1, last_he + 1):
            if (f"{day:%Y-%m-%d}", he) not in have_rt:
                df = ieso.rt_prices(day, he)
                if df is not None:
                    frames.append(df)
    rt = pd.concat(frames) if frames else None
    print(f"prices: {0 if da is None else da['date'].nunique()} DA days, {0 if rt is None else len(rt) // 9} RT hours fetched")

    if da is None and rt is None:
        return
    keys = ["date", "he", "zone"]
    new = pd.concat([x for x in (da, rt) if x is not None]).groupby(keys).first()  # one row per hour, da and/or rt
    if old is not None:
        new = new.combine_first(old.set_index(keys))  # fetched values win; everything else stays
    save(new.reset_index().reindex(columns=[*keys, "da", "rt"]), "prices.csv", keys)


def seed_prices(src):
    """prices.csv from lrg-dashboard's ieso_dam_prices.csv / ieso_rtm_prices.csv (GridStatus,
    checked value-for-value against these same IESO reports there on 2026-09-22)."""
    src = Path(src)
    out = []
    for name, col in (("ieso_dam_prices.csv", "da"), ("ieso_rtm_prices.csv", "rt")):
        df = pd.read_csv(src / name)
        ts = df["interval_start_local"].str[:19]
        out.append(pd.DataFrame({"date": ts.str[:10], "he": ts.str[11:13].astype(int) + 1,
                                 "zone": df["location"], col: df["lmp"]}).set_index(["date", "he", "zone"]))
    merged = out[0].join(out[1], how="outer").reset_index()
    save(merged[["date", "he", "zone", "da", "rt"]], "prices.csv", ["date", "he", "zone"])


# --- yearly files ----------------------------------------------------------------------------

def update_yearly(full):
    year = ieso.market_now().year
    years = range(FIRST_YEAR, year + 1) if full else ([year - 1, year] if ieso.market_now().dayofyear <= 7 else [year])
    for name, reader in (("generation.csv", ieso.generation), ("demand.csv", ieso.demand), ("interties.csv", ieso.interties)):
        frames = [df for df in (reader(y) for y in years) if df is not None]
        if not frames:
            continue
        new = pd.concat(frames)
        new = new.dropna(subset=[c for c in new.columns if c not in ("date", "he")], how="all")
        old = load(name)
        if old is not None:
            fetched = set(new["date"].str[:4])
            old = old[~old["date"].str[:4].isin(fetched)]  # a year's file supersedes what we had for it
            new = pd.concat([old, new])
        save(new, name, ["date", "he"])


# --- adequacy --------------------------------------------------------------------------------

def update_adequacy(window):
    today = ieso.market_now().date()
    files = ieso.listing("Adequacy3")
    old = load("adequacy.csv")
    have = set() if old is None else set(old["date"])
    frames = []
    for day in days(today - pd.Timedelta(days=window), today):
        if f"{day:%Y-%m-%d}" in have:
            continue
        # The last version published before the day began (the listing's times are Eastern).
        before = [n for n, t in ieso.adequacy_versions(files, day) if t < pd.Timestamp(day)]
        if before:
            df = ieso.adequacy(before[-1])
            if df is not None:
                frames.append(df)
    if frames:
        merge("adequacy.csv", pd.concat(frames), ["date", "he"])
    print(f"adequacy: {len(frames)} day-ahead days fetched")

    outlook = [ieso.adequacy(f"PUB_Adequacy3_{day:%Y%m%d}.xml") for day in days(today, today + pd.Timedelta(days=6))]
    outlook = [df for df in outlook if df is not None]
    if outlook:
        save(pd.concat(outlook), "adequacy_outlook.csv", ["date", "he"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--window", type=int, default=WINDOW_DAYS, help="days back to re-check for missing data")
    ap.add_argument("--full-years", action="store_true", help=f"re-read every yearly file since {FIRST_YEAR}")
    ap.add_argument("--seed-prices", default=None, help="lrg-dashboard data/ folder to start prices.csv from")
    ap.add_argument("--only", default=None, help="comma list of prices,yearly,adequacy")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    only = set(args.only.split(",")) if args.only else {"prices", "yearly", "adequacy"}
    if args.seed_prices:
        seed_prices(args.seed_prices)
    if "prices" in only:
        update_prices(args.window)
    if "yearly" in only:
        update_yearly(args.full_years or not (DATA / "generation.csv").exists())
    if "adequacy" in only:
        update_adequacy(args.window)


if __name__ == "__main__":
    main()
