"""Readers for IESO's public reports (https://reports-public.ieso.ca/public/). No API key, no
quota. Every reader returns a DataFrame keyed by `date` (YYYY-MM-DD) and `he` (hour ending,
1-24), both in IESO market time: Eastern Standard Time all year, no daylight saving.

What each report keeps online decides how far back a reader can go:
  GenOutputbyFuelHourly, Demand, IntertieScheduleFlowYear -- one file per year, back to 2015,
      2002 and 2018: the whole history is always one download away.
  DAHourlyZonal, RealtimeZonalEnergyPrices, Adequacy3 -- one file per day (RT: per hour), kept
      for ~3 months. What isn't saved here before then is gone, which is why update.py runs
      every hour and the price history was seeded from lrg-dashboard (back to 2025-05-20)."""
import io
import re
import xml.etree.ElementTree as ET

import pandas as pd
import requests

BASE = "https://reports-public.ieso.ca/public"
NS = "{http://www.ieso.ca/schema}"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ontario-grid (https://github.com/lulopdz/ontario-grid)"

FUELS = ["nuclear", "gas", "hydro", "wind", "solar", "biofuel"]
# Interties grouped by neighbour. Quebec is ten separate ties (PQ.*); Manitoba's two are summed.
INTERTIES = {"manitoba": ["MANITOBA", "MANITOBA SK"], "minnesota": ["MINNESOTA"], "michigan": ["MICHIGAN"],
             "new_york": ["NEW-YORK"], "quebec": "PQ."}


def market_now():
    return pd.Timestamp.now(tz="UTC").tz_convert("-05:00")


def get(url):
    """Body of url, or None on 404 (not published yet / no longer kept)."""
    r = SESSION.get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def listing(report):
    """{file name: last-modified Timestamp} from a report's directory index."""
    html = get(f"{BASE}/{report}/").decode("utf-8", "replace")
    rows = re.findall(r'href="(PUB_[^"]+)">[^<]*</a>\s+(\d{2}-\w{3}-\d{4} \d{2}:\d{2})', html)
    return {name: pd.Timestamp(stamp) for name, stamp in rows}


def _t(e, tag):
    return e.findtext(NS + tag)


# --- Zonal prices ---------------------------------------------------------------------------

def da_prices(day):
    """Day-ahead 'Zonal Price' of the nine virtual zonal hubs for one delivery day: date, he,
    zone, da. None if not published."""
    body = get(f"{BASE}/DAHourlyZonal/PUB_DAHourlyZonal_{day:%Y%m%d}.xml")
    if body is None:
        return None
    rows = []
    for zone in ET.fromstring(body).iter(NS + "TransactionZone"):
        name = _t(zone, "ZoneName").replace(":HUB", "")
        for comp in zone.findall(NS + "Components"):
            if _t(comp, "PriceComponent") != "Zonal Price":
                continue
            for dh in comp.findall(NS + "DeliveryHour"):
                rows.append((f"{day:%Y-%m-%d}", int(_t(dh, "Hour")), name, float(_t(dh, "LMP"))))
    return pd.DataFrame(rows, columns=["date", "he", "zone", "da"])


def rt_prices(day, he):
    """Real-time zonal price for one hour: the mean of its twelve 5-minute intervals, per hub.
    None if the hour isn't published yet or isn't complete."""
    body = get(f"{BASE}/RealtimeZonalEnergyPrices/PUB_RealtimeZonalEnergyPrices_{day:%Y%m%d}{he:02d}.xml")
    if body is None:
        return None
    rows = []
    for zone in ET.fromstring(body).iter(NS + "TransactionZone"):
        prices = [float(_t(ip, "ZonalPrice")) for ip in zone.findall(NS + "IntervalPrice")]
        if len(prices) < 12:
            return None
        rows.append((f"{day:%Y-%m-%d}", he, _t(zone, "ZoneName").replace(":HUB", ""), sum(prices) / len(prices)))
    return pd.DataFrame(rows, columns=["date", "he", "zone", "rt"]) if rows else None


# --- Yearly files ----------------------------------------------------------------------------

def generation(year):
    """Hourly output by fuel (MW) for one year: date, he, nuclear, gas, hydro, wind, solar, biofuel."""
    body = get(f"{BASE}/GenOutputbyFuelHourly/PUB_GenOutputbyFuelHourly_{year}.xml")
    if body is None:
        return None
    rows = []
    for day in ET.fromstring(body).iter(NS + "DailyData"):
        date = _t(day, "Day")
        for hour in day.findall(NS + "HourlyData"):
            row = {"date": date, "he": int(_t(hour, "Hour"))}
            for ft in hour.findall(NS + "FuelTotal"):
                out = ft.find(NS + "EnergyValue").findtext(NS + "Output")
                row[_t(ft, "Fuel").lower()] = float(out) if out not in (None, "") else None
            rows.append(row)
    df = pd.DataFrame(rows)
    return df.reindex(columns=["date", "he", *FUELS])


def _yearly_csv(report, year):
    body = get(f"{BASE}/{report}/PUB_{report}_{year}.csv")
    if body is None:
        return None
    lines = [l for l in body.decode("utf-8", "replace").splitlines() if not l.startswith("\\")]
    return lines


def demand(year):
    """Hourly demand (MW) for one year: date, he, ontario_demand, market_demand. Ontario demand
    is what Ontario consumes; market demand adds exports."""
    lines = _yearly_csv("Demand", year)
    if lines is None:
        return None
    df = pd.read_csv(io.StringIO("\n".join(lines)))
    df = df.rename(columns={"Date": "date", "Hour": "he", "Ontario Demand": "ontario_demand", "Market Demand": "market_demand"})
    return df[["date", "he", "ontario_demand", "market_demand"]]


def interties(year):
    """Hourly intertie imports, exports and actual flow (MW) by neighbour for one year: date,
    he, then {neighbour}_import / _export / _flow for each INTERTIES group and total. Flow is
    the metered actual, positive when Ontario exports; import/export are the schedules."""
    lines = _yearly_csv("IntertieScheduleFlowYear", year)
    if lines is None:
        return None
    ties = lines[0].split(",")  # tie name row, three columns each (Imp, Exp, Flow)
    kinds = lines[1].split(",")
    body = pd.read_csv(io.StringIO("\n".join(lines[2:])), header=None)
    out = pd.DataFrame({"date": body[0], "he": body[1].astype(int)})
    names = {"Imp": "import", "Exp": "export", "Flow": "flow"}
    for group, members in {**INTERTIES, "total": ["Total"]}.items():
        for kind in ("Imp", "Exp", "Flow"):
            cols = [i for i, (t, k) in enumerate(zip(ties, kinds)) if k == kind and
                    (t.startswith(members) if isinstance(members, str) else t in members)]
            out[f"{group}_{names[kind]}"] = body[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    return out


# --- Adequacy (day-ahead demand forecast, supply capacity, margin) ----------------------------

def adequacy(name):
    """One Adequacy3 file (e.g. 'PUB_Adequacy3_20261030_v3.xml'): date, he, forecast_demand
    (Ontario demand), supply_capacity (total forecast supply), requirement (demand plus
    reserves and exports) and excess_capacity, all MW. None if gone."""
    body = get(f"{BASE}/Adequacy3/{name}")
    if body is None:
        return None
    root = ET.fromstring(body)
    doc = root.find(NS + "DocBody")
    day = _t(doc, "DeliveryDate")

    def hourly(path, leaf, value="EnergyMW"):
        node = doc.find(path)
        return {} if node is None else {int(_t(e, "DeliveryHour")): float(_t(e, value)) for e in node.findall(NS + leaf)}

    series = {
        "forecast_demand": hourly(f"{NS}ForecastDemand/{NS}OntarioDemand/{NS}ForecastOntDemand", "Demand"),
        "supply_capacity": hourly(f"{NS}ForecastSupply/{NS}TotalSupplies", "Supply"),
        "requirement": hourly(f"{NS}ForecastDemand/{NS}TotalRequirements", "Requirement"),
        "excess_capacity": hourly(f"{NS}ForecastDemand/{NS}ExcessCapacities", "Capacity"),
    }
    df = pd.DataFrame({"he": range(1, 25)})
    for col, values in series.items():
        df[col] = df["he"].map(values)
    df.insert(0, "date", day)
    df["created_at"] = _t(root.find(NS + "DocHeader"), "CreatedAt")
    return df


def adequacy_versions(listing_map, day):
    """Adequacy3 files for one delivery day, oldest first: [(name, last_modified)]. The
    unversioned name is the latest version, listed last."""
    stem = f"PUB_Adequacy3_{day:%Y%m%d}"
    files = [(n, t) for n, t in listing_map.items() if n.startswith(stem)]
    return sorted(files, key=lambda x: x[1])
