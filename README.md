# Ontario Grid

Ontario's electricity market from IESO's public data: day-ahead and real-time prices for the nine
virtual zonal hubs and their spread (DART), generation by fuel, actual demand against the
forecast, interties with the neighbours, and next week's adequacy.

**Site:** https://lulopdz.github.io/ontario-grid/ (English; Spanish behind the EN/ES button)

Independent project, not affiliated with IESO.

## How it works

Everything comes from IESO's public reports (https://reports-public.ieso.ca/public/): no API keys,
no quotas. A GitHub Action (`.github/workflows/update.yml`) runs every hour:

1. `ingest/update.py` fetches what's new and re-requests anything missing from the last 7 days,
   so a report IESO published late is filled in on the next run.
2. The CSVs in `data/` are committed if they changed.
3. `build.py` builds the site into `_site/` (one compact JSON per view, the CSVs for download,
   and plotly.js) and it is published to GitHub Pages.

| File | Contents | Since |
|---|---|---|
| `data/prices.csv` | Day-ahead and real-time (mean of the twelve 5-minute intervals) price by zone, $/MWh | 2025-05-20 |
| `data/generation.csv` | Generation by fuel, MW | 2018 |
| `data/demand.csv` | Ontario demand and market demand (with exports), MW | 2018 |
| `data/interties.csv` | Scheduled imports and exports and actual flow by neighbour, MW (flow > 0: Ontario exports) | 2018 |
| `data/adequacy.csv` | Demand forecast, supply capacity, requirement and margin: the last forecast published before each day began | 2026-09-17 |
| `data/adequacy_outlook.csv` | The same for today and the next six days, from the latest forecast | — |

All times are IESO market time: Eastern Standard Time all year, no daylight saving; `he` is the
hour ending (1-24).

IESO keeps about three months of its daily reports online (prices, adequacy). Earlier price
history comes from [lrg-dashboard](https://github.com/lulopdz/lrg-dashboard) (GridStatus, checked
against these same reports). Generation, demand and interties have yearly files, so their full
history can always be rebuilt:

```bash
pip install -r requirements.txt
python ingest/update.py --window 100 --full-years   # everything IESO still keeps
python build.py                                     # site in _site/
```
