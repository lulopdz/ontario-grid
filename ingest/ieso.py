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
import time
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


RETRIES = 4  # IESO's server resets the odd connection; one reset used to abort the whole update


def get(url):
    """Body of url, or None on 404 (not published yet / no longer kept). Connection errors and
    5xx answers are retried with a growing pause (2, 4, 8 s) before giving up."""
    for attempt in range(RETRIES):
        try:
            r = SESSION.get(url, timeout=120)
            if r.status_code == 404:
                return None
            if r.status_code < 500:
                r.raise_for_status()
                return r.content
            error = requests.HTTPError(f"{r.status_code} for {url}")
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            error = e
        if attempt < RETRIES - 1:
            time.sleep(2 ** (attempt + 1))
    raise error


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


# --- Market detail (daily files IESO keeps ~30 days; archived monthly by update.py) --------

def _L(e):
    return e.tag.split("}")[-1]


def _xml(path):
    body = get(f"{BASE}/{path}")
    return None if body is None else ET.fromstring(body)


def _children(e, name):
    return [c for c in e if _L(c) == name]


def _text(e, name):
    for c in e:
        if _L(c) == name:
            return c.text
    return None


VT_TYPES = {"Total Load Bid": "load_bid", "Total Load Scheduled": "load_scheduled", "Total Supply Offered": "supply_offered",
            "Total Supply Scheduled": "supply_scheduled", "Net Scheduled": "net_scheduled", "Total Net Scheduled": "net_scheduled"}


def virtual_transactions(day):
    """Day-ahead virtual transactions by zonal hub and hour (MW): date, he, zone, load_bid,
    load_scheduled, supply_offered, supply_scheduled, net_scheduled. zone TOTAL is IESO's
    Ontario-wide total. Published with the DAM, the day before delivery."""
    root = _xml(f"DAVirtualTransactions/PUB_DAVirtualTransactions_{day:%Y%m%d}.xml")
    if root is None:
        return None
    rows = []
    for vt in root.iter():
        if _L(vt) == "ZonalTransactions":
            zone, hours, tx = _text(vt, "ZoneName").replace(":HUB", ""), "HourlyTransactions", "Transactions"
        elif _L(vt) == "VTTotals":
            zone, hours, tx = "TOTAL", "HourlyTotalTransactions", "TotalTransactions"
        else:
            continue
        for h in _children(vt, hours):
            row = {"date": f"{day:%Y-%m-%d}", "he": int(_text(h, "DeliveryHour")), "zone": zone}
            for t in _children(h, tx):
                row[VT_TYPES.get(_text(t, "Type"), _text(t, "Type"))] = float(_text(t, "Value"))
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=["date", "he", "zone", *dict.fromkeys(VT_TYPES.values())])


def virtual_price_delta(day):
    """IESO's daily virtual transaction price delta by zone ($/MWh): date, zone, price_delta."""
    root = _xml(f"PriceDeltaVirtualTransactionDaily/PUB_PriceDeltaVirtualTransactionDaily_{day:%Y%m%d}.xml")
    if root is None:
        return None
    rows = [(f"{day:%Y-%m-%d}", _text(z, "Name"), float(_text(z, "PriceDelta"))) for z in root.iter() if _L(z) == "Zone"]
    return pd.DataFrame(rows, columns=["date", "zone", "price_delta"])


def vg_forecast(published_day):
    """Wind and solar forecast (MW) from the last VGForecastSummary of published_day, which
    covers the next two days: date, he, organization (MARKET PARTICIPANT = grid-connected,
    EMBEDDED = distribution-connected), fuel, zone, mw, forecast_at."""
    root = _xml(f"VGForecastSummary/PUB_VGForecastSummary_{published_day:%Y%m%d}.xml")
    if root is None:
        return None
    stamp = next((e.text for e in root.iter() if _L(e) == "ForecastTimeStamp"), None)
    rows = []
    for org in root.iter():
        if _L(org) != "OrganizationData":
            continue
        org_type = _text(org, "OrganizationType")
        for fuel in _children(org, "FuelData"):
            for res in _children(fuel, "ResourceData"):
                for fc in _children(res, "EnergyForecast"):
                    for iv in _children(fc, "ForecastInterval"):
                        rows.append((_text(fc, "ForecastDate"), int(_text(iv, "ForecastHour")), org_type,
                                     _text(fuel, "FuelType").lower(), _text(res, "ZoneName"), float(_text(iv, "MWOutput")), stamp))
    return pd.DataFrame(rows, columns=["date", "he", "organization", "fuel", "zone", "mw", "forecast_at"])


def shadow_prices(day, market):
    """Shadow price of every binding transmission constraint ($/MWh): date, he, constraint,
    shadow_price (real-time: mean of the 5-minute intervals) and, day-ahead, run."""
    if market == "da":
        root = _xml(f"DAConstrShadowPrices/PUB_DAConstrShadowPrices_{day:%Y%m%d}.xml")
    else:
        root = _xml(f"RealtimeConstrShadowPrices/PUB_RealtimeConstrShadowPrices_{day:%Y%m%d}.xml")
    if root is None:
        return None
    rows = []
    for hp in root.iter():
        if _L(hp) != "HourlyPrice":
            continue
        name = " ".join((_text(hp, "ConstraintName") or "").split())
        if market == "da":
            sp = _children(hp, "ShadowPrices")[0] if _children(hp, "ShadowPrices") else hp
            hours = [c for c in sp if _L(c) == "Hour"]
            prices = [c for c in sp if _L(c) == "ShadowPrice"]
            for h, p in zip(hours, prices):
                rows.append((f"{day:%Y-%m-%d}", int(h.text), name, float(p.text), int(_text(hp, "RunNo") or 1)))
        else:
            vals = [float(_text(iv, "ShadowPrice")) for iv in _children(hp, "IntervalShadowPrices")]
            if vals:
                rows.append((f"{day:%Y-%m-%d}", int(_text(hp, "DeliveryHour")), name, sum(vals) / len(vals), None))
    df = pd.DataFrame(rows, columns=["date", "he", "constraint", "shadow_price", "run"])
    return df if market == "da" else df.drop(columns="run")


def _intertie_points(root, hourly_tag, value_tag, he=None, day=None):
    rows = []
    for p in root.iter():
        if _L(p) != "IntertieLMPrice":
            continue
        point = _text(p, "IntertiePLName").replace(":LMP", "")
        for comp in _children(p, "Components"):
            if _text(comp, "LMPComponent") != "Intertie LMP":
                continue
            items = _children(comp, hourly_tag)
            if he is None:
                rows += [(day, int(_text(i, "DeliveryHour")), point, float(_text(i, value_tag))) for i in items]
            elif items:
                rows.append((day, he, point, sum(float(_text(i, value_tag)) for i in items) / len(items)))
    return rows


def intertie_lmp_da(day):
    """Day-ahead LMP at each intertie point ($/MWh): date, he, point, da."""
    root = _xml(f"DAHourlyIntertieLMP/PUB_DAHourlyIntertieLMP_{day:%Y%m%d}.xml")
    if root is None:
        return None
    return pd.DataFrame(_intertie_points(root, "HourlyLMP", "LMP", day=f"{day:%Y-%m-%d}"), columns=["date", "he", "point", "da"])


def intertie_lmp_rt(day, he):
    """Real-time LMP at each intertie point for one hour, mean of its 5-minute intervals."""
    root = _xml(f"RealTimeIntertieLMP/PUB_RealTimeIntertieLMP_{day:%Y%m%d}{he:02d}.xml")
    if root is None:
        return None
    return pd.DataFrame(_intertie_points(root, "IntervalLMP", "LMP", he=he, day=f"{day:%Y-%m-%d}"), columns=["date", "he", "point", "rt"])


def generator_output(day):
    """Hourly output, capability and available capacity (MW) of every grid-connected
    generator: date, he, generator, fuel, output, capability, available_capacity. The day's
    final version is published shortly after midnight."""
    root = _xml(f"GenOutputCapability/PUB_GenOutputCapability_{day:%Y%m%d}.xml")
    if root is None:
        return None
    parts = {"Outputs": "output", "Capabilities": "capability", "Capacities": "available_capacity"}
    rows = []
    for g in root.iter():
        if _L(g) != "Generator":
            continue
        name, fuel, hours = _text(g, "GeneratorName"), _text(g, "FuelType"), {}
        for part, col in parts.items():
            for block in _children(g, part):
                for item in block:
                    h, v = _text(item, "Hour"), _text(item, "EnergyMW")
                    if h:
                        hours.setdefault(int(h), {})[col] = float(v) if v not in (None, "") else None
        rows += [{"date": f"{day:%Y-%m-%d}", "he": h, "generator": name, "fuel": (fuel or "").lower(), **v} for h, v in hours.items()]
    return pd.DataFrame(rows).reindex(columns=["date", "he", "generator", "fuel", *parts.values()])


def transmission_outages(name):
    """One TxOutages report (TxOutagesTodayAll or TxOutages1to30DaysPlanned): one row per
    outage request and equipment."""
    root = _xml(name)
    if root is None:
        return None
    rows = []
    for req in root.iter():
        if _L(req) != "OutageRequest":
            continue
        base = {"outage_id": _text(req, "OutageID"), "planned_start": _text(req, "PlannedStart"), "planned_end": _text(req, "PlannedEnd"),
                "priority": _text(req, "Priority"), "recurrence": _text(req, "Recurrence"),
                "recall_time": _text(req, "EquipmentRecallTime"), "status": _text(req, "OutageRequestStatus")}
        for eq in _children(req, "EquipmentRequested"):
            rows.append({**base, "equipment": _text(eq, "EquipmentName"), "equipment_type": _text(eq, "EquipmentType"),
                         "voltage": _text(eq, "EquipmentVoltage"), "constraint_type": _text(eq, "ConstraintType")})
    return pd.DataFrame(rows)
