"""End-to-end run of the second customer config on generated data (no thresholds breached)."""
from pathlib import Path

from generate_data import generate
from pipeline.config import load_config
from pipeline.dq import DQReport
from pipeline.eval_er import evaluate
from pipeline.export_duckdb import export_duckdb
from pipeline.report_html import render_dashboard
from pipeline.pipeline import run_pipeline, run_sql_layer

ROOT = Path(__file__).resolve().parents[1]


def test_plant_beta_end_to_end(spark, tmp_path):
    generate("plant_beta", tmp_path / "data" / "raw" / "plant_beta", seed=7)
    cfg = load_config(ROOT / "configs" / "plant_beta.yaml")
    dq = DQReport(cfg["customer"], cfg["dq_thresholds"])
    out = tmp_path / "output"

    run_pipeline(spark, cfg, tmp_path, out, dq)
    dq.write(out)
    assert dq.failures() == []

    assets = spark.read.parquet(str(out / "model" / "assets"))
    assert assets.count() == 3
    readings = spark.read.parquet(str(out / "model" / "readings"))
    assert readings.filter("asset_id = 'BT-01'").count() > 0

    counts = run_sql_layer(spark, ROOT, out)
    assert set(counts) == {"01_hours_since_last_maintenance.sql", "02_anomalies_before_failure.sql",
                           "03_data_coverage_per_asset.sql", "04_top_alarms.sql",
                           "05_entity_resolution_status.sql"}
    assert (out / "sql_results" / "01_hours_since_last_maintenance.csv").exists()


def test_plant_beta_eval_duckdb_dashboard_and_breach(spark, tmp_path):
    """Second customer through eval, DuckDB export and dashboard; tight thresholds must fail."""
    generate("plant_beta", tmp_path / "data" / "raw" / "plant_beta", seed=7)
    cfg = load_config(ROOT / "configs" / "plant_beta.yaml")
    out = tmp_path / "output"
    dq = DQReport(cfg["customer"], cfg["dq_thresholds"])
    run_pipeline(spark, cfg, tmp_path, out, dq)
    run_sql_layer(spark, ROOT, out)
    dq.write(out)

    result = evaluate(spark, tmp_path / cfg["evaluation"]["ground_truth"], out / "model", out / "eval")
    assert result["overall"]["precision"] == 1.0 and result["overall"]["recall"] == 1.0

    counts = export_duckdb(out, ROOT)
    assert counts["assets"] == 3 and counts["q01_hours_since_last_maintenance"] == 3
    page = render_dashboard(out, cfg).read_text(encoding="utf-8")
    assert "Data quality by source and rule" in page and "Entity-resolution evaluation" in page

    strict = DQReport(cfg["customer"], {**cfg["dq_thresholds"], "readings_duplicate_rate_max": 0.0})
    run_pipeline(spark, cfg, tmp_path, tmp_path / "strict", strict)
    assert [f["rule"] for f in strict.failures()] == ["duplicates_removed"]
