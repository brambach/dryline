# Recorded fixtures

Real responses recorded on 2026-10-17 around 05:26 UTC with the dryline User-Agent. Each one is stored as a
gzipped `RawResponse` envelope with url, fetched_at, status, and body.

- `trta.json.gz`: Tahoe Rim Trail Association conditions page
- `usfs-ltbmu.json.gz`, `usfs-tnf.json.gz`: USFS alert listings
- `nws-forecast.json.gz`: NWS gridpoint forecast REV/34,81 (South Lake Tahoe)
- `nws-obs-KTVL.json.gz`: KTVL observations for 48 h, **trimmed** to the hourly METARs (the 5-minute
  records have no rawMessage and aren't used)
- `snotel.json.gz`: AWDB daily SNWD and WTEQ for the 24 stations in `stations.yaml`
- `snotel-prcp.json.gz`: the first live `dryline collect` (2026-10-16 22:40 PT), with SNWD, WTEQ, and PRCP

Changed-layout cases are derived from these inside the tests, so it's explicit what changed.
- `nvparks-tahoe.json.gz`: Lake Tahoe Nevada State Park page from the first live run (statewide fire-restriction banner only, no closures)
