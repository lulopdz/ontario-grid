"""Bring data/*.csv up to date from IESO's public reports. Run every hour by the workflow.

    python ingest/update.py                       # incremental: re-checks the last WINDOW_DAYS
    python ingest/update.py --window 100          # backfill everything IESO still keeps (~3 months)
    python ingest/update.py --seed-prices DIR     # one-off: start prices.csv from lrg-dashboard's data/

Every pass re-requests what is *missing* inside the window instead of resuming from the last
stored hour, so an hour IESO published late (or a run that failed halfway) is filled on the
next pass rather than left as a permanent hole -- lrg-dashboard lost 2026-10-23 HE12 that way.

Files (all keyed by date + he, IESO market time = EST all year):
  prices/YYYY.csv       date, he, zone, da, rt          nine virtual zonal hubs
  generation/YYYY.csv   date, he, nuclear .. biofuel     MW by fuel
  demand/YYYY.csv       date, he, ontario_demand, market_demand
  interties/YYYY.csv    date, he, {neighbour}_import/_export/_flow
  adequacy.csv          date, he, forecast_demand, supply_capacity, requirement, excess_capacity,
                        created_at -- the last forecast published before the day began
  adequacy_outlook.csv  same columns, the latest forecast for today and the next six days

Market detail, one file per month (data/<name>/YYYY-MM.csv) so an hourly commit only touches
the current month. IESO keeps these ~30 days (some ~90), so they only exist from when this
archive started:
  virtual_transactions/   date, he, zone, load_bid, load_scheduled, supply_offered, supply_scheduled, net_scheduled
  virtual_price_delta/    date, zone, price_delta
  vg_forecast/            date, he, organization, fuel, zone, mw, forecast_at -- the last wind/solar
                          forecast published before the day began
  shadow_prices_da/       date, he, constraint, shadow_price, run
  shadow_prices_rt/       date, he, constraint, shadow_price (mean of the 5-minute intervals)
  intertie_lmp/           date, he, point, da, rt
  generator_output/       date, he, generator, fuel, output, capability, available_capacity
  transmission_outages.csv  one row per outage request and equipment, with when it was first
                          and last seen (first_seen before planned_start = known ahead)

Consumption by postal area (FSA), one file per month, from FSA_FIRST_MONTH on. IESO publishes
each month ~3 months late and keeps them back to 2018. Three levels:
  fsa_hourly/YYYY-MM.csv.gz  date, he, fsa, customer_type, kwh, premises -- every hour, price plans
                          summed (~4.6 MB a month gzipped; the plan split triples it and is in
                          fsa_daily). Written once per month, never rewritten.
  fsa_daily/              date, fsa, customer_type, price_plan, kwh, premises (daily mean), version
  fsa_hourly_profile/     month, fsa, customer_type, he, kwh (mean over the month's days), version
  fsa_manifest.csv        month, version: what is stored. The hourly workflow skips fsa_hourly/ in
                          its checkout, so this, not the files, says which months are done."""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ieso  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
WINDOW_DAYS = 7
FIRST_YEAR = 2018  # interties start here; generation and demand are trimmed to match


# The four big hourly series live as one file per year (data/prices/2026.csv, ...): every run
# rewrites only the current year's file, so past years stay untouched in git instead of being
# re-committed whole every hour. load() and save() hide the split; build.py joins the years.
YEARLY = ("prices.csv", "generation.csv", "demand.csv", "interties.csv")


def load(name):
    if name in YEARLY:
        files = sorted((DATA / name.removesuffix(".csv")).glob("*.csv"))
        return pd.concat(pd.read_csv(f) for f in files) if files else None
    path = DATA / name
    return pd.read_csv(path) if path.exists() else None


def save(df, name, keys):
    df = df.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    if name in YEARLY:
        folder = DATA / name.removesuffix(".csv")
        folder.mkdir(exist_ok=True)
        for year, part in df.groupby(df["date"].str[:4]):
            path, text = folder / f"{year}.csv", part.to_csv(index=False)
            if not path.exists() or path.read_text() != text:  # leave unchanged years alone
                path.write_text(text)
    else:
        df.to_csv(DATA / name, index=False)
    print(f"  {name}: {len(df):,} rows, {df['date'].min()} .. {df['date'].max()}")


def merge(name, new, keys):
    old = load(name)
    if new is None or new.empty:
        return
    save(new if old is None else pd.concat([old, new]), name, keys)


def days(start, end):
    return list(pd.date_range(start, end).date)


# --- monthly files ---------------------------------------------------------------------------

def load_monthly(name, since):
    """Rows of data/<name>/ from the month of `since` on (None if nothing stored)."""
    folder = DATA / name
    files = sorted(folder.glob("*.csv")) if folder.exists() else []
    frames = [pd.read_csv(f) for f in files if f.stem >= f"{since:%Y-%m}"]
    return pd.concat(frames) if frames else None


def save_monthly(name, new, keys):
    if new is None or new.empty:
        return
    folder = DATA / name
    folder.mkdir(exist_ok=True)
    for month, part in new.groupby(new["date"].str[:7]):
        path = folder / f"{month}.csv"
        if path.exists():
            part = pd.concat([pd.read_csv(path), part])
        part = part.drop_duplicates(subset=keys, keep="last").sort_values(keys)
        part.to_csv(path, index=False)
    print(f"  {name}/: +{len(new):,} rows ({new['date'].min()} .. {new['date'].max()})")


def missing_days(name, candidates):
    have = load_monthly(name, min(candidates)) if candidates else None
    have = set() if have is None else set(have["date"])
    return [d for d in candidates if f"{d:%Y-%m-%d}" not in have]


def fetch_days(name, candidates, reader, keys):
    frames = [df for df in (reader(d) for d in missing_days(name, candidates)) if df is not None and not df.empty]
    save_monthly(name, pd.concat(frames) if frames else None, keys)
    return len(frames)


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
    years = range(FIRST_YEAR, year + 1) if full else ([year - 1, year] if ieso.market_now().day_of_year <= 7 else [year])
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


# --- market detail ---------------------------------------------------------------------------

def update_market(window):
    now = ieso.market_now()
    today = now.date()
    start = today - pd.Timedelta(days=window)
    tomorrow = today + pd.Timedelta(days=1)
    counts = {}

    # Published with the DAM (~12:35 EST the day before), so tomorrow may be out already.
    counts["virtual_transactions"] = fetch_days("virtual_transactions", days(start, tomorrow), ieso.virtual_transactions, ["date", "he", "zone"])
    counts["virtual_price_delta"] = fetch_days("virtual_price_delta", days(start, tomorrow), ieso.virtual_price_delta, ["date", "zone"])
    counts["shadow_prices_da"] = fetch_days("shadow_prices_da", days(start, tomorrow), lambda d: ieso.shadow_prices(d, "da"),
                                            ["date", "he", "constraint", "run"])
    # Real-time shadow prices come out about six days late; the window has to reach them.
    rt_start = today - pd.Timedelta(days=max(window, 10))
    counts["shadow_prices_rt"] = fetch_days("shadow_prices_rt", days(rt_start, today), lambda d: ieso.shadow_prices(d, "rt"),
                                            ["date", "he", "constraint"])
    # A day's generator file is final once the day is over.
    counts["generator_output"] = fetch_days("generator_output", days(start, today - pd.Timedelta(days=1)), ieso.generator_output,
                                            ["date", "he", "generator"])

    # Wind/solar: for day T, the last forecast of T-1 (its file covers T and T+1).
    def vg(day):
        df = ieso.vg_forecast(day - pd.Timedelta(days=1))
        return None if df is None else df[df["date"] == f"{day:%Y-%m-%d}"]
    counts["vg_forecast"] = fetch_days("vg_forecast", days(start, today), vg, ["date", "he", "organization", "fuel", "zone"])

    # Intertie LMPs: day-ahead per day, real-time per complete hour (like the zonal prices).
    have = load_monthly("intertie_lmp", start)
    have_da = set() if have is None else set(have.loc[have["da"].notna(), "date"])
    have_rt = set() if have is None else set(zip(have.loc[have["rt"].notna(), "date"], have.loc[have["rt"].notna(), "he"]))
    frames = [ieso.intertie_lmp_da(d) for d in days(start, tomorrow) if f"{d:%Y-%m-%d}" not in have_da]
    for d in days(start, today):
        for he in range(1, (now.hour if d == today else 24) + 1):
            if (f"{d:%Y-%m-%d}", he) not in have_rt:
                frames.append(ieso.intertie_lmp_rt(d, he))
    frames = [f for f in frames if f is not None and not f.empty]
    if frames:
        keys = ["date", "he", "point"]
        new = pd.concat(frames).groupby(keys).first()
        if have is not None:
            new = new.combine_first(have.set_index(keys))
        new = new.reset_index().reindex(columns=[*keys, "da", "rt"])
        save_monthly("intertie_lmp", new[new["date"] >= f"{start:%Y-%m-%d}"], keys)
    counts["intertie_lmp"] = len(frames)

    counts["transmission_outages"] = update_outages(today)
    print("market: " + ", ".join(f"{k} {v}" for k, v in counts.items()))


def update_outages(today):
    """Upsert today's outages and the 30-day planned list into transmission_outages.csv,
    keeping when each outage/equipment pair was first and last seen."""
    keys = ["outage_id", "equipment"]
    frames = []
    for report, source in (("TxOutagesTodayAll", "today"), ("TxOutages1to30DaysPlanned", "planned")):
        df = ieso.transmission_outages(f"{report}/PUB_{report}_{today:%Y%m%d}.xml")
        if df is not None and not df.empty:
            frames.append(df.assign(first_seen=f"{today:%Y-%m-%d}", last_seen=f"{today:%Y-%m-%d}", first_source=source))
    if not frames:
        return 0
    new = pd.concat(frames).drop_duplicates(subset=keys, keep="first")
    old = load("transmission_outages.csv")
    if old is not None:
        first = old.set_index(keys)[["first_seen", "first_source"]]
        new = new.set_index(keys)
        new.update(first)  # an outage keeps the day (and list) it first appeared in
        new = pd.concat([old.set_index(keys), new])
        new = new[~new.index.duplicated(keep="last")].reset_index()
    new = new.sort_values(["first_seen", "outage_id", "equipment"])
    new.to_csv(DATA / "transmission_outages.csv", index=False)
    print(f"  transmission_outages.csv: {len(new):,} rows")
    return len(frames)


# --- consumption by postal area --------------------------------------------------------------

FSA_FIRST_MONTH = "2025-01"  # earlier months (back to 2018) are still on IESO's site
FSA_MANIFEST = DATA / "fsa_manifest.csv"


def update_fsa(first_month=FSA_FIRST_MONTH):
    """Fetch every month (or newer version of one) not yet stored, from first_month on."""
    files = ieso.listing("HourlyConsumptionByFSA")
    manifest = pd.read_csv(FSA_MANIFEST) if FSA_MANIFEST.exists() else pd.DataFrame(columns=["month", "version"])
    stored = dict(zip(manifest["month"], manifest["version"].astype(int)))
    todo = {m: v for m, v in ieso.fsa_months(files).items() if m >= first_month and stored.get(m, 0) < v[1]}
    for month, (name, version) in sorted(todo.items()):
        raw = ieso.fsa_consumption(name)
        if raw is None or raw.empty:
            continue
        daily = (raw.groupby(["date", "fsa", "customer_type", "price_plan"], as_index=False)
                 .agg(kwh=("kwh", "sum"), premises=("premises", "mean")))
        by_hour = raw.groupby(["fsa", "customer_type", "date", "he"], as_index=False)["kwh"].sum()
        profile = by_hour.groupby(["fsa", "customer_type", "he"], as_index=False)["kwh"].mean()
        profile.insert(0, "month", month)
        for out, df, keys in (("fsa_daily", daily, ["date", "fsa", "customer_type", "price_plan"]),
                              ("fsa_hourly_profile", profile, ["fsa", "customer_type", "he"])):
            (DATA / out).mkdir(exist_ok=True)
            df.assign(kwh=df["kwh"].round(1), version=version).round({"premises": 1}).sort_values(keys).to_csv(
                DATA / out / f"{month}.csv", index=False)
        hourly = (raw.groupby(["date", "he", "fsa", "customer_type"], as_index=False)
                  .agg(kwh=("kwh", "sum"), premises=("premises", "sum")))
        (DATA / "fsa_hourly").mkdir(exist_ok=True)
        # mtime=0: the same data always gzips to the same bytes, so a re-run commits nothing.
        hourly.assign(kwh=hourly["kwh"].round(1)).to_csv(
            DATA / "fsa_hourly" / f"{month}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        stored[month] = version
        pd.DataFrame(sorted(stored.items()), columns=["month", "version"]).to_csv(FSA_MANIFEST, index=False)
        print(f"  fsa {month} (v{version}): {raw['fsa'].nunique()} FSAs, {raw['kwh'].sum() / 1e6:,.0f} GWh")
    print(f"fsa: {len(todo)} month(s) fetched")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--window", type=int, default=WINDOW_DAYS, help="days back to re-check for missing data")
    ap.add_argument("--full-years", action="store_true", help=f"re-read every yearly file since {FIRST_YEAR}")
    ap.add_argument("--seed-prices", default=None, help="lrg-dashboard data/ folder to start prices.csv from")
    ap.add_argument("--only", default=None, help="comma list of prices,yearly,adequacy,market,fsa")
    args = ap.parse_args()
    DATA.mkdir(exist_ok=True)
    only = set(args.only.split(",")) if args.only else {"prices", "yearly", "adequacy", "market", "fsa"}
    if args.seed_prices:
        seed_prices(args.seed_prices)
    if "prices" in only:
        update_prices(args.window)
    if "yearly" in only:
        update_yearly(args.full_years or load("generation.csv") is None)
    if "adequacy" in only:
        update_adequacy(args.window)
    if "market" in only:
        update_market(args.window)
    if "fsa" in only:
        update_fsa()


if __name__ == "__main__":
    main()
