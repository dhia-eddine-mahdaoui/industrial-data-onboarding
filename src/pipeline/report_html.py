"""Static HTML views of a pipeline run: per-customer dashboard and the onboarding diff.

Only the standard library is used; the pages are single files with inline CSS
so they can be opened from disk, attached to a ticket, or screenshotted.
"""
from __future__ import annotations

import csv
import json
from html import escape
from pathlib import Path

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mute:#667085;--line:#e4e7ec;--ok:#067647;--okbg:#e7f6ee;
--bad:#b42318;--badbg:#fdecea;--warn:#93560d;--warnbg:#fdf3e1;--acc:#1f5fbf;--accbg:#e8f0fc;--bar:#c9d6ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:1120px;margin:0 auto;padding:24px 20px 40px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 4px}
.sub{color:var(--mute);margin:0 0 16px}.card{background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:18px 20px;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.tile span{color:var(--mute);font-size:12px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:12px;color:var(--mute);font-weight:600;border-bottom:1px solid var(--line);padding:6px 8px}
td{padding:6px 8px;border-bottom:1px solid #f0f2f5;vertical-align:middle}
td.n,th.n{text-align:right}.pill{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600}
.ok{background:var(--okbg);color:var(--ok)}.bad{background:var(--badbg);color:var(--bad)}
.warn{background:var(--warnbg);color:var(--warn)}.na{background:#eef0f3;color:var(--mute)}
.meter{position:relative;height:8px;background:#eef0f3;border-radius:4px;min-width:120px}
.meter i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--bar)}
.meter i.over{background:#e5867c}.meter u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px}.mute{color:var(--mute)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.two{grid-template-columns:1fr}}
"""


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _fmt_num(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return escape(str(value))


def _pct(x, digits=2) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def _page(title: str, body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def _pill(text: str, kind: str) -> str:
    return f'<span class="pill {kind}">{escape(text)}</span>'


def _mono(text) -> str:
    return f'<span class="mono">{escape(str(text))}</span>'


def _table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    head = "".join(f'<th class="{"n" if num else ""}">{escape(h)}</th>' for h, num in headers)
    body = "".join(
        "<tr>" + "".join(f'<td class="{"n" if headers[i][1] else ""}">{cell}</td>'
                         for i, cell in enumerate(row)) + "</tr>"
        for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _meter(measure, limit, scale_max) -> str:
    if measure is None or limit is None or not scale_max:
        return ""
    width = min(100.0, 100.0 * measure / scale_max)
    mark = min(100.0, 100.0 * limit / scale_max)
    cls = "over" if measure > limit else ""
    return (f'<div class="meter"><i class="{cls}" style="width:{width:.1f}%"></i>'
            f'<u style="left:{mark:.1f}%"></u></div>')


def _dq_section(dq: dict) -> str:
    rows = []
    for r in (r for r in dq["rules"] if r["mode"] != "info"):
        measure, limit = r["measure"], r["limit"]
        if r["mode"] == "count_max":
            value = f"{int(measure)}"
            lim = "" if limit is None else f"max {int(limit)}"
            meter = _meter(measure, limit, max(limit or 1, measure) * 1.5)
            observed = _fmt_num(r["observed"])
        else:
            value = _pct(measure)
            lim = "" if limit is None else (f"min {_pct(limit)}" if r["mode"] == "rate_min"
                                           else f"max {_pct(limit)}")
            meter = "" if limit is None else _meter(measure, limit, max(limit, measure) * 1.5)
            observed = f"{_fmt_num(r['observed'])} / {_fmt_num(r['total'])}"
        if r["passed"] is None:
            result = _pill("info", "na")
        else:
            result = _pill("pass", "ok") if r["passed"] else _pill("BREACH", "bad")
        rows.append([escape(r["source"]), _mono(r["rule"]), observed, value, meter, escape(lim), result])
    table = _table([("Source", False), ("Rule", False), ("Observed", True), ("Rate", True),
                    ("Rate vs limit (marker)", False), ("Limit", True), ("Result", False)], rows)
    overall = _pill("PASSED", "ok") if dq["passed"] else _pill("FAILED", "bad")
    return ('<section class="card" id="dq"><h2>Data quality by source and rule ' + overall + "</h2>"
            '<p class="sub">Each rule is checked against a threshold from the customer config. '
            "Rows rejected by a rule are quarantined, not dropped silently.</p>" + table + "</section>")


def _er_section(out: Path, dq: dict) -> str:
    info = {(r["source"], r["rule"]): r["observed"] for r in dq["rules"] if r["mode"] == "info"}
    lines = []
    for source in ("readings", "maintenance"):
        parts = []
        for status, kind in (("matched", "ok"), ("review", "warn"), ("unmatched", "bad")):
            n = info.get(("entity_resolution", f"{source}_names_{status}"), 0)
            parts.append(_pill(f"{n} {status}", kind))
        lines.append(f"<p><b>{source}</b> distinct raw names: {' '.join(parts)}</p>")
    rows = []
    for q in _read_csv(out / "entity_review_queue.csv"):
        kind = "warn" if q["status"] == "review" else "bad"
        rows.append([_mono(q["raw_name"]), escape(q["source"]), escape(q["suggested_asset_id"] or "no candidate"),
                     escape(q["second_candidate"] or ""), q["confidence"], _pill(q["status"], kind)])
    table = (_table([("Raw name", False), ("Source", False), ("Suggested asset", False),
                     ("Runner-up", False), ("Confidence", True), ("Status", False)], rows)
             if rows else '<p class="mute">Review queue is empty.</p>')
    return ('<section class="card" id="er"><h2>Asset-name resolution and review queue</h2>'
            '<p class="sub">Names are normalised, scored against every register alias, and only '
            "confident, unambiguous matches enter the model. The rest wait here for a human.</p>"
            + "".join(lines) + table + "</section>")


def _model_section(out: Path) -> str:
    maint = {r["asset_id"]: r for r in _read_csv(out / "sql_results" / "01_hours_since_last_maintenance.csv")}
    by_asset: dict[str, list[dict]] = {}
    for r in _read_csv(out / "sql_results" / "03_data_coverage_per_asset.csv"):
        by_asset.setdefault(r["asset_id"], []).append(r)
    rows = []
    for asset_id, m in sorted(maint.items()):
        series = [r for r in by_asset.get(asset_id, []) if r["sensor"]]
        sensors = ", ".join(sorted(r["sensor"].replace("_", " ") for r in series)) or "none"
        samples = sum(int(r["samples"]) for r in series)
        cov = (sum(float(r["coverage_pct"]) for r in series) / len(series)) if series else None
        hours = m["hours_since_last_maintenance"]
        rows.append([_mono(asset_id), escape(m["asset_name"]), escape(sensors),
                     _fmt_num(samples) if series else "-",
                     f"{cov:.1f}%" if cov is not None else "-",
                     f"{float(hours):,.0f} h" if hours else "never logged"])
    table = _table([("Asset", False), ("Name", False), ("Sensors", False), ("Clean samples", True),
                    ("Coverage", True), ("Since last maintenance", True)], rows)
    return ('<section class="card" id="model"><h2>Clean asset model</h2>'
            '<p class="sub">One row per canonical asset after normalisation, de-duplication and '
            "name resolution, with results of the example customer queries.</p>" + table + "</section>")


def _queries_section(out: Path) -> str:
    alarms = _read_csv(out / "sql_results" / "04_top_alarms.csv")[:6]
    pre = _read_csv(out / "sql_results" / "02_anomalies_before_failure.csv")
    a_rows = [[_mono(r["asset_id"]), escape(r["sensor"].replace("_", " ")), r["anomalies"], r["spikes"],
               r["max_abs_z"]] for r in alarms]
    p_rows = [[_mono(r["asset_id"]), escape(r["failure_at"][:16]), r["anomalous_readings_72h"],
               escape(r["first_anomaly_at"][:16]), r["max_abs_z"]] for r in pre]
    left = ('<div><h2>Top alarms</h2><p class="sub">Anomalous or spiking samples</p>'
            + _table([("Asset", False), ("Sensor", False), ("Anomalies", True), ("Spikes", True),
                      ("Max |z|", True)], a_rows) + "</div>")
    right = ('<div><h2>Anomalous readings before failure</h2><p class="sub">72 hours before each '
             "logged failure work order (UTC)</p>"
             + (_table([("Asset", False), ("Failure at", False), ("Anomalies", True),
                        ("First anomaly", False), ("Max |z|", True)], p_rows)
                if p_rows else '<p class="mute">No failure events in this dataset.</p>') + "</div>")
    return f'<section class="card" id="queries"><div class="two">{left}{right}</div></section>'


def _eval_section(ev: dict) -> str:
    o, base = ev["overall"], ev["exact_key_only_baseline"]

    def row(label, s):
        return [escape(label), _fmt_num(s["names"]), _fmt_num(s["accepted"]), _pct(s["precision"], 1),
                _pct(s["recall"], 1), _pct(s["assisted_recall"], 1), _fmt_num(s["false_accepts"]),
                _fmt_num(s["review"]), _fmt_num(s["unmatched"])]

    rows = [row("Pipeline, all names", o)]
    rows += [row(f"Pipeline, {src}", s) for src, s in ev["by_source"].items()]
    rows.append(row("Baseline: exact name key only", base))
    table = _table([("Run", False), ("Names", True), ("Auto-accepted", True), ("Precision", True),
                    ("Recall", True), ("Recall with review", True), ("False accepts", True),
                    ("In review", True), ("Unmatched", True)], rows)
    err_rows = [[_mono(e["raw_name"]), escape(e["source"]), escape(e["truth"] or "(not in register)"),
                 escape(e["predicted"] or "-"),
                 _pill(e["status"], "warn" if e["status"] == "review" else
                       ("bad" if e["status"] == "matched" else "na"))] for e in ev["errors"][:8]]
    err_table = (_table([("Raw name", False), ("Source", False), ("True asset", False),
                         ("Suggested", False), ("Outcome", False)], err_rows)
                 if err_rows else '<p class="mute">No errors.</p>')
    tiles = ('<div class="tiles">'
             f'<div class="tile"><b>{_pct(o["precision"], 1)}</b><span>precision of auto-accepted</span></div>'
             f'<div class="tile"><b>{_pct(o["recall"], 1)}</b><span>recall without review</span></div>'
             f'<div class="tile"><b>{_pct(o["assisted_recall"], 1)}</b><span>recall after one-click review</span></div>'
             f'<div class="tile"><b>{o["out_of_register_rejected"]} / {o["out_of_register"]}</b>'
             "<span>out-of-register names not auto-matched</span></div></div>")
    return ('<section class="card" id="eval"><h2>Entity-resolution evaluation</h2>'
            '<p class="sub">Scored against labels written by the data generator, over distinct raw names.</p>'
            + tiles + table + '<h2 style="margin-top:16px">Names that did not resolve cleanly</h2>'
            + err_table + "</section>")


def render_dashboard(out: Path, cfg: dict) -> Path:
    dq = json.loads((out / "dq_report.json").read_text(encoding="utf-8"))
    ev_path = out / "eval" / "er_eval.json"
    ev = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.exists() else None
    info = {(r["source"], r["rule"]): r["observed"] for r in dq["rules"] if r["mode"] == "info"}
    cover = _read_csv(out / "sql_results" / "03_data_coverage_per_asset.csv")
    clean = sum(int(r["samples"]) for r in cover if r["samples"])
    rules = [r for r in dq["rules"] if r["passed"] is not None]
    n_pass = sum(1 for r in rules if r["passed"])
    tiles = [(_fmt_num(info.get(("readings", "rows_in"), 0)), "raw readings rows"),
             (_fmt_num(clean), "clean readings in model"),
             (_fmt_num(info.get(("asset_register", "assets_loaded"), 0)), "assets in model"),
             (f"{n_pass} / {len(rules)}", "DQ threshold rules passed")]
    if ev:
        tiles.append((_pct(ev["overall"]["precision"], 1), "name-match precision"))
    tile_html = "".join(f'<div class="tile"><b>{v}</b><span>{escape(k)}</span></div>' for v, k in tiles)
    body = (f"<h1>{escape(cfg.get('display_name', cfg['customer']))}: onboarding dashboard</h1>"
            '<p class="sub">Synthetic data, generated by the pipeline from the customer config.</p>'
            f'<div class="tiles" id="tiles">{tile_html}</div>'
            + _dq_section(dq) + _er_section(out, dq) + _model_section(out) + _queries_section(out)
            + (_eval_section(ev) if ev else ""))
    path = out / "dashboard.html"
    path.write_text(_page(f"{cfg['customer']} onboarding dashboard", body), encoding="utf-8")
    return path


# ---- onboarding diff -------------------------------------------------------

def _flatten(node, prefix="") -> dict[str, str]:
    flat: dict[str, str] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            flat.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        flat[prefix] = json.dumps(node) if isinstance(node, (list, tuple)) else str(node)
    return flat


def render_onboarding_diff(cfg_a: dict, cfg_b: dict, summaries: dict, out_path: Path) -> Path:
    """Side-by-side view of two customer configs plus the result of running each."""
    fa, fb = _flatten(cfg_a), _flatten(cfg_b)
    keys = [k for k in dict.fromkeys(list(fa) + list(fb))
            if k.split(".")[0] not in {"customer", "display_name"} and k.split(".")[-1] != "path"]
    changed = [k for k in keys if fa.get(k) != fb.get(k)]
    shown = [k for k in changed if k.split(".")[0] != "dq_thresholds"][:26]
    rows = [[_mono(k), _mono(fa.get(k, "(not set)")), _mono(fb.get(k, "(not set)"))] for k in shown]
    table = _table([("Setting", False), (cfg_a["display_name"], False), (cfg_b["display_name"], False)], rows)
    res_rows = [[escape(name), _fmt_num(s["raw_rows"]), _fmt_num(s["clean_rows"]), escape(s["names"]),
                 escape(s["rules"]), _pill("PASSED", "ok") if s["passed"] else _pill("FAILED", "bad")]
                for name, s in summaries.items()]
    results = _table([("Customer", False), ("Raw readings rows", True), ("Clean readings rows", True),
                      ("Raw names resolved", False), ("DQ rules passed", False), ("Run", False)], res_rows)
    body = ("<h1>Onboarding a second site is a config change</h1>"
            f'<p class="sub">{len(changed)} of {len(keys)} settings differ between the two customer '
            "configs; the pipeline code is identical for both runs. File locations are omitted.</p>"
            f'<section class="card" id="diff"><h2>What differs (excluding DQ thresholds)</h2>{table}</section>'
            f'<section class="card" id="diff-results"><h2>Result of running each config</h2>{results}</section>')
    out_path.write_text(_page("Onboarding diff", body), encoding="utf-8")
    return out_path
