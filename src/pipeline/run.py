"""CLI entry point.

    python -m pipeline.run --config configs/plant_alpha.yaml

Exit code 1 when any DQ threshold is breached and fail_on_breach is true.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.config import load_config
from pipeline.dq import DQReport
from pipeline.eval_er import evaluate
from pipeline.export_duckdb import export_duckdb
from pipeline.pipeline import run_pipeline, run_sql_layer
from pipeline.report_html import render_dashboard
from pipeline.session import get_spark


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the onboarding pipeline for one customer.")
    parser.add_argument("--config", required=True, help="customer YAML config")
    parser.add_argument("--root", default=".", help="project root that config paths are relative to")
    parser.add_argument("--out", default=None, help="output directory (default: output/<customer>)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    root = Path(args.root).resolve()
    out = Path(args.out).resolve() if args.out else root / "output" / cfg["customer"]
    dq = DQReport(cfg["customer"], cfg["dq_thresholds"])

    spark = get_spark(f"onboarding-{cfg['customer']}", cfg["session"]["timezone"])
    try:
        summary = run_pipeline(spark, cfg, root, out, dq)
        sql_counts = run_sql_layer(spark, root, out)
        truth = (cfg.get("evaluation") or {}).get("ground_truth")
        eval_result = evaluate(spark, root / truth, out / "model", out / "eval") if truth else None
    finally:
        spark.stop()

    dq.write(out)
    duckdb_counts = export_duckdb(out, root)
    render_dashboard(out, cfg)
    if eval_result:
        o = eval_result["overall"]
        print(f"[{cfg['customer']}] ER eval: precision {o['precision']} recall {o['recall']} "
              f"recall-with-review {o['assisted_recall']} ({o['names']} names)")
    print(f"[{cfg['customer']}] DuckDB export: {duckdb_counts}")
    print(f"[{cfg['customer']}] model rows: {summary}")
    print(f"[{cfg['customer']}] SQL results: {sql_counts}")
    print(f"[{cfg['customer']}] reports: dq_report.md, dq_report.json, dashboard.html in {out.name}/")
    failures = dq.failures()
    for f in failures:
        print(f"DQ BREACH {f['source']}.{f['rule']}: measure {f['measure']} > limit {f['limit']}",
              file=sys.stderr)
    if failures and cfg["dq_thresholds"].get("fail_on_breach", True):
        print(f"[{cfg['customer']}] FAILED: {len(failures)} data-quality threshold breach(es)", file=sys.stderr)
        return 1
    print(f"[{cfg['customer']}] DQ thresholds passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
