from pipeline.dq import DQReport


def test_thresholds_flag_breaches_only():
    dq = DQReport("t", {"null_rate_max": 0.01, "dup_max": 2, "match_rate_min": 0.9, "fail_on_breach": True})
    dq.record("readings", "null_value", 5, 100, threshold_key="null_rate_max")      # 5% > 1%: breach
    dq.record("readings", "ok_rate", 1, 100, threshold_key="null_rate_max")         # 1%: pass
    dq.record("asset_register", "missing_ids", 3, 10, threshold_key="dup_max", mode="count_max")  # breach
    dq.record("entity", "match_rate", 95, 100, threshold_key="match_rate_min", mode="rate_min")   # pass
    dq.record("entity", "no_threshold", 7, 100, threshold_key="not_configured")      # info only
    assert [f["rule"] for f in dq.failures()] == ["null_value", "missing_ids"]


def test_markdown_and_json_report_status(tmp_path):
    dq = DQReport("t", {"null_rate_max": 0.01})
    dq.record("readings", "null_value", 5, 100, threshold_key="null_rate_max")
    dq.info("readings", "spikes_flagged", 3, "kept")
    dq.add_list("Unresolved", ["maintenance: 'Pump 9' -> no candidate"])
    md = dq.to_markdown()
    assert "FAILED (1 breaches)" in md
    assert "**BREACH**" in md
    assert "Pump 9" in md
    dq.write(tmp_path)
    assert (tmp_path / "dq_report.json").exists() and (tmp_path / "dq_report.md").exists()
