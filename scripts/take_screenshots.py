#!/usr/bin/env python3
"""Render the generated HTML views to PNGs for the README (docs/screenshots/).

Needs `pip install playwright` (browser binaries are not downloaded) and a
Chromium or Chrome binary: set CHROME_PATH, or the usual system locations are tried.
Only element regions of the pages are captured, so no browser chrome, address bar
or file path ends up in an image.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"

# file name -> (page, selectors whose union is captured)
SHOTS = {
    "01-data-quality-report.png": ("plant_alpha/dashboard.html", ["#tiles", "#dq"]),
    "02-entity-review-queue.png": ("plant_alpha/dashboard.html", ["#er"]),
    "03-asset-model-and-queries.png": ("plant_alpha/dashboard.html", ["#model", "#queries"]),
    "04-second-customer-onboarding.png": ("onboarding_diff.html", ["h1", "#diff", "#diff-results"]),
    "05-entity-resolution-eval.png": ("plant_alpha/dashboard.html", ["#eval"]),
}


def find_browser() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env:
        return env
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def union_clip(page, selectors: list[str]) -> dict:
    boxes = [page.locator(sel).first.bounding_box() for sel in selectors]
    pad = 12
    x0 = min(b["x"] for b in boxes) - pad
    y0 = min(b["y"] for b in boxes) - pad
    x1 = max(b["x"] + b["width"] for b in boxes) + pad
    y1 = max(b["y"] + b["height"] for b in boxes) + pad
    return {"x": max(x0, 0), "y": max(y0, 0), "width": x1 - x0, "height": y1 - y0}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=find_browser(), headless=True,
                                     args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1180, "height": 900}, device_scale_factor=2)
        page = context.new_page()
        for name, (rel, selectors) in SHOTS.items():
            page.goto((ROOT / "output" / rel).as_uri())
            page.screenshot(path=str(OUT / name), clip=union_clip(page, selectors), full_page=True)
            print("wrote", (OUT / name).relative_to(ROOT))
        browser.close()


if __name__ == "__main__":
    main()
