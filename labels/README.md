# Labels

- `trail-days.csv` holds **real** hand labels: `date,trail,truth,note`. Truth is one of
  dry, muddy, snow, closed. Add rows by hand or with `uv run dryline label`, which serves a local page at
  http://127.0.0.1:8765. The goal is 50 trail-days.
- `SYNTHETIC-sample.csv` holds 5 made-up rows that exist only to show the harness runs. Don't mix them into real
  labels. Run them with `uv run dryline eval --labels labels/SYNTHETIC-sample.csv`.

`dryline eval` reports per-class accuracy (by true class), the unknown rate, accuracy when dryline did
not say unknown, and a confusion matrix.
