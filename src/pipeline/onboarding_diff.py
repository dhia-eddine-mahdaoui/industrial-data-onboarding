"""Build output/onboarding_diff.html from two customer configs and their finished runs.

    python -m pipeline.onboarding_diff configs/plant_alpha.yaml configs/plant_beta.yaml
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from pipeline.config import load_config
from pipeline.report_html import render_onboarding_diff


def _summary(out: Path) -> dict:
    dq = json.loads((out / "dq_report.json").read_text(encoding="utf-8"))
    info = {(r["source"], r["rule"]): r["observed"] for r in dq["rules"] if r["mode"] == "info"}
    with (out / "sql_results" / "03_data_coverage_per_asset.csv").open(newline="", encoding="utf-8") as fh:
        clean = sum(int(r["samples"]) for r in csv.DictReader(fh) if r["samples"])
    matched = sum(v for (src, rule), v in info.items()
                  if src == "entity_resolution" and rule.endswith("_matched"))
    names = sum(v for (src, rule), v in info.items() if src == "entity_resolution")
    rules = [r for r in dq["rules"] if r["passed"] is not None]
    return {"raw_rows": info[("readings", "rows_in")], "clean_rows": clean,
            "names": f"{matched} of {names} auto-matched",
            "rules": f"{sum(1 for r in rules if r['passed'])} of {len(rules)}", "passed": dq["passed"]}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(__doc__)
        return 2
    root = Path(".").resolve()
    cfgs = [load_config(a) for a in args]
    summaries = {c["display_name"]: _summary(root / "output" / c["customer"]) for c in cfgs}
    path = render_onboarding_diff(cfgs[0], cfgs[1], summaries, root / "output" / "onboarding_diff.html")
    print(f"wrote {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
