"""Data-quality rule collector, threshold evaluation and report writers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class DQReport:
    """Collects rule results per source and renders JSON and Markdown.

    record() evaluates a rule against a threshold key from the config:
      rate_max  observed / total must be <= limit
      rate_min  observed / total must be >= limit
      count_max observed must be <= limit
    A rule whose threshold key is absent is reported as information only.
    """

    def __init__(self, customer: str, thresholds: dict):
        self.customer = customer
        self.thresholds = dict(thresholds or {})
        self.rules: list[dict] = []
        self.lists: list[tuple[str, list[str]]] = []

    def record(self, source: str, rule: str, observed, total, threshold_key: str | None = None,
               mode: str = "rate_max", detail: str = "") -> None:
        observed = int(observed)
        total = int(total)
        if mode == "count_max":
            measure = float(observed)
        else:
            measure = observed / total if total else 0.0
        limit = self.thresholds.get(threshold_key) if threshold_key else None
        passed = None
        if limit is not None:
            limit = float(limit)
            passed = measure >= limit if mode == "rate_min" else measure <= limit
        self.rules.append({
            "source": source, "rule": rule, "observed": observed, "total": total,
            "measure": round(measure, 6), "mode": mode, "limit": limit,
            "passed": passed, "detail": detail,
        })

    def info(self, source: str, rule: str, value, detail: str = "") -> None:
        self.rules.append({
            "source": source, "rule": rule, "observed": value, "total": None,
            "measure": None, "mode": "info", "limit": None, "passed": None, "detail": detail,
        })

    def add_list(self, title: str, items: list[str]) -> None:
        self.lists.append((title, items))

    def failures(self) -> list[dict]:
        return [r for r in self.rules if r["passed"] is False]

    def to_dict(self) -> dict:
        return {
            "customer": self.customer,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "passed": not self.failures(),
            "rules": self.rules,
            "unresolved_lists": [{"title": t, "items": i} for t, i in self.lists],
        }

    def to_markdown(self) -> str:
        status = "PASSED" if not self.failures() else f"FAILED ({len(self.failures())} breaches)"
        lines = [f"# Data-quality report: {self.customer}", "", f"Overall: **{status}**", "",
                 "## Threshold rules", "",
                 "| Source | Rule | Observed | Of total | Measure | Limit | Result |",
                 "|---|---|---:|---:|---:|---:|---|"]
        for r in self.rules:
            if r["mode"] == "info":
                continue
            measure = f"{r['measure']:.4%}" if r["mode"] != "count_max" else f"{int(r['measure'])}"
            limit = "" if r["limit"] is None else (
                f"{r['limit']:.2%}" if r["mode"].startswith("rate") else f"{int(r['limit'])}")
            if r["passed"] is None:
                result = "n/a"
            else:
                result = "pass" if r["passed"] else "**BREACH**"
            lines.append(f"| {r['source']} | {r['rule']} | {r['observed']} | {r['total']} | "
                         f"{measure} | {limit} | {result} |")
        lines += ["", "## Information", "", "| Source | Metric | Value | Note |", "|---|---|---:|---|"]
        for r in self.rules:
            if r["mode"] != "info":
                continue
            value = r["observed"]
            if isinstance(value, float):
                value = f"{value:.4f}"
            lines.append(f"| {r['source']} | {r['rule']} | {value} | {r['detail']} |")
        for title, items in self.lists:
            lines += ["", f"## {title}", ""]
            lines += [f"- {item}" for item in items] or ["- none"]
        return "\n".join(lines) + "\n"

    def write(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "dq_report.json").write_text(
            json.dumps(self.to_dict(), indent=2, default=str), encoding="utf-8")
        (out_dir / "dq_report.md").write_text(self.to_markdown(), encoding="utf-8")
