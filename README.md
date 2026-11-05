# Ontario Grid

Ontario's electricity market from IESO's public data: day-ahead and real-time prices for the nine
virtual zonal hubs and their spread (DART), generation by fuel, actual demand against the
forecast, interties with the neighbours, next week's adequacy, and what virtual traders as a group
bid, got scheduled and made in the day-ahead market (IESO publishes their totals, not who they are).

**Site:** https://lulopdz.github.io/ontario-grid/ (English; Spanish behind the EN/ES button)

Independent project, not affiliated with IESO.

Next steps and ready-to-use prompts for future work sessions: [`docs/PROMPTS.md`](docs/PROMPTS.md) (in Spanish).

## The site

| Tab | What it shows |
|---|---|
| Prices | Day-ahead and real-time price by zone, DART, and how often DART was positive |
| Generation | The generation mix over the range and hourly output by fuel |
| Demand | Ontario demand against IESO's day-ahead forecast and its error; daily peaks over long ranges |
| Interties | Net flow with each neighbour, and next week's supply capacity against requirement |
| Virtuals | Virtual traders as a group, by hub: net scheduled position (tomorrow's too, once the DAM is out), by hour of day, offered vs scheduled, and their P&L (net MW × DART, before fees) |

Ranges from 7 days to the full history, light and dark themes, a daily table under each tab, and
every series downloadable as CSV.

## Repository

```
ingest/ieso.py      readers for each IESO report (with retries)
ingest/update.py    brings data/ up to date; re-requests whatever is missing
build.py            data/ -> _site/ (one JSON per view, full CSV downloads, plotly.js)
site/               index.html, app.js (views, EN/ES strings), styles.css
data/               the archive (below)
.github/workflows/update.yml   hourly: update, commit data, build, publish to Pages
```

## How it works

Everything comes from IESO's public reports (https://reports-public.ieso.ca/public/): no API keys,
no quotas. A GitHub Action (`.github/workflows/update.yml`) runs every hour:

1. `ingest/update.py` fetches what's new and re-requests anything missing from the last 7 days,
   so a report IESO published late is filled in on the next run.
2. The CSVs in `data/` are committed if they changed.
3. `build.py` builds the site into `_site/` (one compact JSON per view, the CSVs for download,
   and plotly.js) and it is published to GitHub Pages.

GitHub's scheduler is best-effort: runs can come hours late, and some hours are skipped
altogether. Nothing is lost when that happens -- the next run re-requests the gap -- and the
site's header shows when it was last updated. To force a run: Actions -> "Update and publish" ->
Run workflow. If a run fails (IESO down), the site is still published with the previous data and
the run shows red.

The four big hourly series are one CSV per year (`data/prices/2026.csv`, ...), so each hourly
commit rewrites only the current year; the site's download links offer each one whole.

| File | Contents | Since |
|---|---|---|
| `data/prices/` | Day-ahead and real-time (mean of the twelve 5-minute intervals) price by zone, $/MWh | 2025-05-20 |
| `data/generation/` | Generation by fuel, MW | 2018 |
| `data/demand/` | Ontario demand and market demand (with exports), MW | 2018 |
| `data/interties/` | Scheduled imports and exports and actual flow by neighbour, MW (flow > 0: Ontario exports) | 2018 |
| `data/adequacy.csv` | Demand forecast, supply capacity, requirement and margin: the last forecast published before each day began | 2026-09-17 |
| `data/adequacy_outlook.csv` | The same for today and the next six days, from the latest forecast | — |

### Market detail

IESO keeps these reports online for only ~30 days (generator output and intertie prices ~90),
so this archive is the only place their history builds up. It started on 2026-10-31 with
everything IESO still had, hence the different start dates. One CSV per month in
`data/<name>/YYYY-MM.csv`, hourly:

| Folder | Contents | Since |
|---|---|---|
| `virtual_transactions/` | Day-ahead virtual bids and offers by zone (IESO's totals over all traders): load bid, supply offered, and what each scheduled, MW | 2026-10-01 |
| `virtual_price_delta/` | IESO's daily virtual transaction price delta by zone, $/MWh | 2026-09-01 |
| `vg_forecast/` | Wind and solar forecast by zone, grid-connected and embedded: the last one published before each day began, MW | 2026-10-01 |
| `shadow_prices_da/`, `shadow_prices_rt/` | Shadow price of each binding transmission constraint (real-time: hourly mean of the 5-minute values), $/MWh. Real-time comes out ~6 days late | 2026-09-24 |
| `intertie_lmp/` | Day-ahead and real-time LMP at the 18 intertie points, $/MWh | 2026-08-01 |
| `generator_output/` | Output, capability and available capacity of every grid-connected generator, MW | 2026-08-01 |
| `transmission_outages.csv` | Transmission outages (today's and the 30-day planned list), with when each was first and last seen | 2026-10-31 |

### Consumption by postal area (not on the site yet)

IESO's hourly consumption by Forward Sortation Area (FSA, the postal code's first three
characters: 563 areas), for residential and small business customers (under 50 kW) -- about a
third of Ontario's demand; large commercial and industrial load is not in it. Published monthly
about three months late, by customer type and price plan (TOU, Tiered, ULO, Retailer). IESO keeps
it back to 2018; this archive starts at 2025-01 (`FSA_FIRST_MONTH` in `ingest/update.py`). One
file per month at three levels; `data/fsa_manifest.csv` lists the months stored, because the
hourly workflow leaves `fsa_hourly/` (~80 MB a year) out of its checkout:

| Folder | Contents |
|---|---|
| `fsa_hourly/` | Every hour: kWh and premises by FSA and customer type, price plans summed (`YYYY-MM.csv.gz`, ~6.8 MB a month; pandas reads it as is). Written once per month, never rewritten |
| `fsa_daily/` | Daily kWh by FSA, customer type and price plan, with the mean number of premises |
| `fsa_hourly_profile/` | Mean kWh for each hour of the day over the month, by FSA and customer type |

IESO changed its privacy method on 2026-02-01, which can make premise counts jump in some FSAs:
compare across that date with care.

A map of it (kWh per home, summer vs winter, homes per km2), not part of the site:
`python analysis/fsa_map.py --out map.html` builds one self-contained page from these files and
`geo/fsa_ontario_2021.geojson` -- Statistics Canada's 2021 cartographic FSA boundaries, Ontario
only, simplified to 5% in mapshaper (Statistics Canada Open Licence).

All times are IESO market time: Eastern Standard Time all year, no daylight saving; `he` is the
hour ending (1-24).

IESO keeps about three months of its daily reports online (prices, adequacy). Earlier price
history comes from [lrg-dashboard](https://github.com/lulopdz/lrg-dashboard) (GridStatus, checked
against these same reports). Generation, demand and interties have yearly files, so their full
history can always be rebuilt:

```bash
pip install -r requirements.txt
python ingest/update.py --window 100 --full-years   # everything IESO still keeps
python ingest/update.py --only market               # just the market detail (also: prices, yearly, adequacy)
python build.py                                     # site in _site/
```
