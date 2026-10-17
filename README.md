# dryline

Where can I go today? A daily, cited digest of conditions on 20 Lake Tahoe and Truckee trails.
Each trail gets one line: **likely dry**, **likely muddy**, **snow**, **closed**, or **unknown**.
Every reason links its source and fetch time. If there's no source, the line says "unknown" and what's missing.

```sh
uv sync
uv run dryline collect   # fetch today's sources into data/raw/YYYY-MM-DD/ (network)
uv run dryline build     # rules -> data/lines/YYYY-MM-DD.json -> site/
uv run dryline eval      # score labels/trail-days.csv against published lines
uv run dryline label     # local labeling page at http://127.0.0.1:8765
uv run dryline resolve   # rare: refresh nws_grid.yaml (NWS gridpoints and nearest METAR stations)
uv run pytest            # offline tests (sockets blocked)
```

## How it decides

The rules in `src/dryline/rules.py` are fixed and deterministic, with no LLM. Precedence is
closed > snow > muddy > dry > unknown.

- **Closed:** an official alert (USFS, NV State Parks) or TRTA entry names the trail and a closure.
- **Snow:** a SNOTEL station within 40 km and ±1,000 ft of the trail's elevation range reports ≥ 2 in of snow
  at or below the trail's high point.
- **Muddy:** ≥ 0.25 in of precipitation in 48 h at the nearest SNOTEL gauge or METAR station.
- **Dry:** needs positive evidence on both counts. A similar-elevation station must show no snow, and the
  precipitation record must be complete and low.
- **Stale data** counts as missing. That means 2 days for SNOTEL, 6 h for NWS observations, and 14 days for
  a conditions page.

## Files

- `trails.yaml`: 20 trails, all `confirmed: false` until reviewed. See `docs/TRAILS_REVIEW.md`.
- `stations.yaml`: SNOTEL stations. `nws_grid.yaml` holds the NWS forecast gridpoint and METAR station
  for each trail.
- `SOURCES.md`: every source, its robots.txt and terms, and whether it's used.
- `PLAN.md` describes the design. `PROGRESS.md` has evidence for each milestone.
- `.github/workflows/daily.yml`: a 6:40am Pacific cron that collects, builds, commits, and publishes to Pages.

Not safety advice. Check the land manager's page before you go.
