#!/usr/bin/env python3
"""Re-record docs/demo.gif (and docs/demo.mp4) from a finished `make run`.

Replays the real pipeline log in a styled terminal page, then scrolls through the
generated dashboard and the onboarding-diff page, recording the headless browser
with Playwright and converting with a static ffmpeg (imageio-ffmpeg).

    make demo          # runs the pipeline, then this script

Needs requirements-dev.txt and a Chrome or Chromium binary (CHROME_PATH or system).
Only the page viewport is recorded: no address bar, shell prompt, user or host.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

from take_screenshots import find_browser

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
DOCS = ROOT / "docs"
SIZE = {"width": 1000, "height": 620}
KEEP = re.compile(r"^(generated |\[plant_)")

TERMINAL = """<!doctype html><html><head><meta charset="utf-8"><title>run</title><style>
body{margin:0;background:#0f1720;color:#d6deeb;font:15px/1.5 ui-monospace,Menlo,Consolas,monospace}
.bar{background:#1b2735;padding:10px 16px;color:#8da2b8;font-size:13px;border-bottom:1px solid #26364a}
#log{padding:16px 22px;white-space:pre-wrap;word-break:break-word}
.l{margin:0 0 7px}.ok{color:#5fd38d;font-weight:700}.dim{color:#7f93a8}.hd{color:#7cb7ff;font-weight:700;margin-top:10px}
</style></head><body><div class="bar">pipeline run: ingest, normalise, resolve names, check data quality</div>
<div id="log"></div><script>
const lines=__LINES__;const el=document.getElementById('log');let i=0;
function next(){if(i>=lines.length)return;const [cls,text]=lines[i++];
const p=document.createElement('p');p.className='l '+cls;p.textContent=text;el.appendChild(p);
window.scrollTo(0,document.body.scrollHeight);setTimeout(next,cls==='hd'?350:230);}
next();</script></body></html>"""


def terminal_lines(log: Path) -> list[list[str]]:
    out: list[list[str]] = []
    last = None
    for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not KEEP.match(line):
            continue
        m = re.match(r"^\[(plant_\w+)\]", line)
        if m and m.group(1) != last:
            last = m.group(1)
            out.append(["hd", f"== {last} =="])
        if line.startswith("[") and "reports:" in line:
            continue
        cls = "ok" if "thresholds passed" in line else ("dim" if "DuckDB export" in line or "SQL results" in line else "")
        out.append([cls, line])
    return out


def scroll_to(page, y: float, ms: int = 900) -> None:
    page.evaluate(
        """([y, ms]) => new Promise(res => {
          const s = window.scrollY, t0 = performance.now();
          const f = t => { const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2)/2;
            window.scrollTo(0, s + (y - s) * e); k < 1 ? requestAnimationFrame(f) : res(); };
          requestAnimationFrame(f); })""", [y, ms])


def record(browser_path: str | None, tmp: Path) -> Path:
    log = OUT / "run.log"
    if not log.exists():
        raise SystemExit("output/run.log missing: run `make demo` (or make run > output/run.log)")
    term = OUT / "demo_terminal.html"
    term.write_text(TERMINAL.replace("__LINES__", json.dumps(terminal_lines(log))), encoding="utf-8")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=browser_path, headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport=SIZE, record_video_dir=str(tmp), record_video_size=SIZE)
        page = ctx.new_page()
        page.goto(term.as_uri())
        page.wait_for_timeout(7200)
        page.goto((OUT / "plant_alpha" / "dashboard.html").as_uri())
        page.wait_for_timeout(1200)
        for sel, pause in (("#dq", 1400), ("#er", 1800), ("#model", 1500), ("#queries", 1800)):
            top = page.evaluate(f"document.querySelector('{sel}').getBoundingClientRect().top + window.scrollY - 12")
            scroll_to(page, top)
            page.wait_for_timeout(pause)
        page.goto((OUT / "onboarding_diff.html").as_uri())
        page.wait_for_timeout(1500)
        top = page.evaluate("document.querySelector('#diff-results').getBoundingClientRect().top + window.scrollY - 12")
        scroll_to(page, top, 1400)
        page.wait_for_timeout(2000)
        video = Path(page.video.path())
        ctx.close()
        browser.close()
    return video


def convert(video: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    DOCS.mkdir(exist_ok=True)
    gif = DOCS / "demo.gif"
    vf = ("fps=8,scale=800:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=40:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle")
    mp4 = DOCS / "demo.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", "0.6", "-i", str(video), "-an",
                    "-vf", "scale=1000:-2,format=yuv420p", "-c:v", "libx264", "-crf", "30",
                    "-preset", "veryfast", str(mp4)], check=True)
    # the GIF is made from the cleaned-up mp4: far less colour noise, much smaller file
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(mp4), "-vf", vf,
                    "-loop", "0", str(gif)], check=True)
    print(f"wrote docs/demo.gif ({gif.stat().st_size / 1e6:.2f} MB) and docs/demo.mp4")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="demo_rec_"))
    try:
        convert(record(find_browser(), tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
