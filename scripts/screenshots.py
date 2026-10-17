"""Take mobile and desktop screenshots of the built site into docs/screenshots/.

Usage: uv run python scripts/screenshots.py [site_dir]
Uses the preinstalled Chromium at /opt/pw-browsers when present (cloud sessions), else Playwright's.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
VIEWPORTS = {"mobile": (390, 844), "desktop": (1280, 900)}


def chromium_path() -> str | None:
    for p in (os.environ.get("DRYLINE_CHROMIUM"), "/opt/pw-browsers/chromium"):
        if p and Path(p).is_file():
            return p
    return None


def main() -> int:
    site = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
    pages = {"today": site / "index.html", "archive": site / "archive" / "index.html"}
    trail_pages = sorted((site / "trails").glob("*/index.html"))
    if trail_pages:
        pages["trail"] = trail_pages[0]
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium_path())
        for vname, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=2 if vname == "mobile" else 1,
                reduced_motion="reduce",  # skip the arrival animation for stable shots
            )
            page = ctx.new_page()
            for name, path in pages.items():
                page.goto(path.resolve().as_uri())
                page.evaluate("document.fonts.ready")
                full = name != "today" or vname == "desktop"
                target = OUT / f"{name}-{vname}.png"
                page.screenshot(path=str(target), full_page=full)
                overflow = page.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                )
                print(f"{target.relative_to(ROOT)}  horizontal-overflow={overflow}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
