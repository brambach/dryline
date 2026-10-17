# dryline

Where can I go today? A daily, cited digest of conditions on 20 Lake Tahoe and Truckee trails.
Each trail gets one line: dry, muddy, snow, closed, or unknown. Every claim links its source and fetch time.

```sh
uv sync
uv run dryline collect   # fetch today's sources (network)
uv run dryline build     # rules -> site/
uv run pytest            # offline tests
```

See `PLAN.md` for the design and `PROGRESS.md` for milestone evidence.
Not safety advice. Check the land manager's page before you go.
