"""Pipeline stages: register -> readings -> maintenance -> asset model -> SQL layer.

All row-level work is Spark DataFrame code. Config (configs/<customer>.yaml)
supplies column names, timestamp formats, unit tables, sensor maps, thresholds
and entity-resolution settings, so a new customer is a config change.
"""
from __future__ import annotations

import csv
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType
from pyspark.sql.window import Window

from pipeline.dq import DQReport
from pipeline.entity_resolution import make_key_udf, resolve_entities
from pipeline.transforms import SI_UNIT_BY_QUANTITY, dedupe, parse_timestamp, to_si

READING_REASONS = ["null_value", "unparseable_timestamp", "unknown_unit", "unmapped_sensor",
                   "quantity_mismatch", "out_of_range", "unmatched_asset"]
MAINTENANCE_REASONS = ["missing_work_order", "unparseable_timestamp", "unmatched_asset"]
SQL_VIEWS = ["assets", "readings", "maintenance_events", "entity_map"]


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _write_parquet(df: DataFrame, path: Path) -> None:
    df.write.mode("overwrite").parquet(str(path))


def _read_csv(spark: SparkSession, path: Path, columns: dict) -> DataFrame:
    """Read a customer CSV as strings and rename to canonical column names."""
    if not path.exists():
        raise FileNotFoundError(f"missing input {path}; run `make data` first")
    df = spark.read.option("header", True).csv(str(path))
    missing = [src for src in columns.values() if src not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: configured columns not found: {missing}")
    selected = [F.trim(F.col(src)).alias(dst) for dst, src in columns.items()]
    return df.select(*selected, F.monotonically_increasing_id().alias("_row_id"))


def load_register(spark: SparkSession, path: Path, rcfg: dict, er: dict):
    """Return (assets, aliases) from the asset register.

    Assets without a register ID get a derived id 'UNREG-<name key>' and
    id_status 'unassigned', so they stay visible in the model and the DQ report.
    """
    if not path.exists():
        raise FileNotFoundError(f"missing input {path}; run `make data` first")
    raw = spark.read.option("multiLine", True).json(str(path))
    exploded = raw.select(F.explode(F.col(rcfg["records_key"])).alias("r"))
    fields = set(exploded.schema["r"].dataType.fieldNames())

    def field(name):
        if name and name in fields:
            return F.col("r").getField(name).cast("string")
        return F.lit(None).cast("string")

    legacy = [F.col("r").getField(f).cast("array<string>")
              for f in (rcfg.get("alias_fields") or []) if f in fields]
    key = make_key_udf(er)
    base = exploded.select(
        field(rcfg.get("asset_id")).alias("reg_id"),
        field(rcfg["name"]).alias("asset_name"),
        field(rcfg.get("asset_class")).alias("asset_class"),
        field(rcfg.get("area")).alias("area"),
        F.concat(F.array(field(rcfg["name"]), field(rcfg.get("asset_id"))), *legacy).alias("alias_arr"),
    )
    with_id = (base
               .withColumn("asset_id", F.when(F.col("reg_id").isNotNull(), F.col("reg_id")).otherwise(
                   F.concat(F.lit("UNREG-"), F.upper(key(F.col("asset_name"))))))
               .withColumn("id_status", F.when(F.col("reg_id").isNotNull(), F.lit("registered"))
                           .otherwise(F.lit("unassigned"))))
    assets = with_id.select("asset_id", "asset_name", "asset_class", "area", "id_status").distinct()
    aliases = (with_id.select("asset_id", F.explode("alias_arr").alias("alias_text"))
                      .filter(F.col("alias_text").isNotNull()))
    return assets, aliases


def _sensor_columns(sensor_col, smap: dict):
    name = F.lit(None).cast("string")
    quantity = F.lit(None).cast("string")
    low = F.lower(F.trim(sensor_col))
    for raw_key, spec in smap.items():
        cond = low == F.lit(str(raw_key).lower())
        name = F.when(cond, F.lit(str(spec["name"]))).otherwise(name)
        quantity = F.when(cond, F.lit(str(spec["quantity"]))).otherwise(quantity)
    return name, quantity


def process_readings(raw: DataFrame, rcfg: dict, emap: DataFrame, dq: DQReport,
                     quarantine_dir: Path) -> DataFrame:
    """Normalise, validate, resolve, dedupe and enrich sensor readings.

    Returns the clean readings model rows; rejected rows are written to quarantine.
    """
    df = raw.withColumn("raw_num", F.col("value").cast("double"))
    si, quantity = to_si(F.col("raw_num"), F.col("unit"), rcfg["unit_conversions"])
    sensor_name, sensor_quantity = _sensor_columns(F.col("sensor"), rcfg["sensor_map"])
    df = (df.withColumn("ts_utc", parse_timestamp(F.col("timestamp"), rcfg))
            .withColumn("value_si", si)
            .withColumn("unit_quantity", quantity)
            .withColumn("sensor_name", sensor_name)
            .withColumn("sensor_quantity", sensor_quantity)
            .withColumn("unit_norm", F.lower(F.col("unit"))))

    out_of_range = F.lit(False)
    for name, (lo, hi) in rcfg["valid_range"].items():
        out_of_range = out_of_range | ((F.col("sensor_name") == name)
                                       & ((F.col("value_si") < float(lo)) | (F.col("value_si") > float(hi))))
    df = df.withColumn("out_of_range", F.coalesce(out_of_range, F.lit(False)))

    df = df.withColumn("reason", F.when(F.col("raw_num").isNull(), F.lit("null_value"))
                       .when(F.col("ts_utc").isNull(), F.lit("unparseable_timestamp"))
                       .when(F.col("unit_quantity").isNull(), F.lit("unknown_unit"))
                       .when(F.col("sensor_name").isNull(), F.lit("unmapped_sensor"))
                       .when(F.col("unit_quantity") != F.col("sensor_quantity"), F.lit("quantity_mismatch"))
                       .when(F.col("out_of_range"), F.lit("out_of_range")))

    em = (emap.filter(F.col("source") == "readings")
              .select(F.col("raw_name").alias("equipment"),
                      F.when(F.col("status") == "matched", F.col("asset_id")).alias("asset_id"),
                      F.col("status").alias("entity_status"),
                      F.col("confidence").alias("match_confidence")))
    df = df.join(em, "equipment", "left")
    df = df.withColumn("reason", F.coalesce(F.col("reason"),
                                            F.when(F.col("asset_id").isNull(), F.lit("unmatched_asset"))))
    df = df.cache()

    total = df.count()
    counts = {r["reason"]: r["n"] for r in
              df.groupBy(F.coalesce(F.col("reason"), F.lit("ok")).alias("reason"))
                .agg(F.count(F.lit(1)).alias("n")).collect()}
    dq.info("readings", "rows_in", total, "raw CSV rows after header parsing")
    _write_parquet(df.filter(F.col("reason").isNotNull())
                     .select("timestamp", "equipment", "sensor", "value", "unit", "reason"),
                   quarantine_dir / "readings")
    for reason in READING_REASONS:
        dq.record("readings", reason, counts.get(reason, 0), total,
                  threshold_key=f"readings_{reason}_rate_max")
    for row in df.groupBy("unit_norm").count().collect():
        unit = row["unit_norm"]
        spec = rcfg["unit_conversions"].get(unit)
        note = (f"normalised to SI {SI_UNIT_BY_QUANTITY.get(spec['quantity'], '')} "
                f"(scale {spec['scale']}, offset {spec['offset']})") if spec else "not in unit table"
        dq.info("readings", f"unit_{unit or 'missing'}_rows", row["count"], note)

    clean = df.filter(F.col("reason").isNull())
    deduped = dedupe(clean, ["asset_id", "sensor_name", "ts_utc"])
    n_clean, n_dedup = clean.count(), deduped.count()
    dq.record("readings", "duplicates_removed", n_clean - n_dedup, total,
              threshold_key="readings_duplicate_rate_max",
              detail="same asset, sensor and UTC timestamp")

    window = Window.partitionBy("asset_id", "sensor_name").orderBy("ts_utc")
    m = (deduped.withColumn("prev_value", F.lag("value_si").over(window))
                .withColumn("prev_ts", F.lag("ts_utc").over(window)))
    spike = F.lit(False)
    for name, delta in rcfg["spike_delta"].items():
        spike = spike | ((F.col("sensor_name") == name)
                         & (F.abs(F.col("value_si") - F.col("prev_value")) > float(delta)))
    gap_seconds = float(rcfg["gap_minutes"]) * 60
    m = (m.withColumn("is_spike", F.coalesce(spike, F.lit(False)))
          .withColumn("gap_before", F.coalesce(
              (F.col("ts_utc").cast("long") - F.col("prev_ts").cast("long")) > gap_seconds, F.lit(False))))

    series = Window.partitionBy("asset_id", "sensor_name")
    m = m.withColumn("series_start", F.min("ts_utc").over(series))
    baseline = (m.filter(F.col("ts_utc") < F.col("series_start")
                         + F.expr(f"INTERVAL {int(rcfg['baseline_days'])} DAYS"))
                  .groupBy("asset_id", "sensor_name")
                  .agg(F.avg("value_si").alias("base_mean"), F.stddev("value_si").alias("base_sd")))
    m = (m.join(baseline, ["asset_id", "sensor_name"], "left")
          .withColumn("z_score", (F.col("value_si") - F.col("base_mean")) / F.col("base_sd"))
          .withColumn("is_anomaly", F.coalesce(F.abs(F.col("z_score")) > float(rcfg["anomaly_z"]), F.lit(False))))
    m = m.cache()
    dq.info("readings", "spikes_flagged", m.filter(F.col("is_spike")).count(),
            "kept in model; jump vs previous sample above spike_delta")
    dq.info("readings", "gaps_detected", m.filter(F.col("gap_before")).count(),
            f"sample follows a gap longer than {rcfg['gap_minutes']} minutes")
    dq.info("readings", "anomalies_flagged", m.filter(F.col("is_anomaly")).count(),
            f"|z| > {rcfg['anomaly_z']} vs first {rcfg['baseline_days']} days of each series")

    return m.select(
        "asset_id",
        F.col("sensor_name").alias("sensor"),
        "ts_utc",
        "value_si",
        F.when(F.col("unit_quantity") == "temperature", F.lit("degC")).otherwise(F.lit("kPa")).alias("si_unit"),
        F.col("timestamp").alias("raw_timestamp"),
        F.col("value").alias("raw_value"),
        F.col("unit").alias("raw_unit"),
        "is_spike", "gap_before", "z_score", "is_anomaly",
    )


def process_maintenance(raw: DataFrame, mcfg: dict, emap: DataFrame, dq: DQReport,
                        quarantine_dir: Path) -> DataFrame:
    df = (raw.withColumn("opened_at_utc", F.to_utc_timestamp(
                F.to_timestamp(F.col("opened"), mcfg["date_format"]), mcfg["naive_timezone"]))
              .withColumn("is_failure", F.coalesce(
                  F.upper(F.col("is_failure")).isin([v.upper() for v in mcfg["failure_values"]]),
                  F.lit(False))))
    df = df.withColumn("reason", F.when(F.col("wo_number").isNull(), F.lit("missing_work_order"))
                       .when(F.col("opened_at_utc").isNull(), F.lit("unparseable_timestamp")))
    df = df.cache()
    total = df.count()
    valid = df.filter(F.col("reason").isNull())
    deduped = dedupe(valid, ["wo_number"])
    dq.record("maintenance", "duplicates_removed", valid.count() - deduped.count(), total,
              threshold_key="maintenance_duplicate_rate_max", detail="same work order number")

    em = (emap.filter(F.col("source") == "maintenance")
              .select(F.col("raw_name").alias("asset_text"),
                      F.when(F.col("status") == "matched", F.col("asset_id")).alias("asset_id"),
                      F.col("status").alias("entity_status"),
                      F.col("confidence").alias("match_confidence")))
    joined = deduped.join(em, "asset_text", "left").cache()
    matched = joined.filter(F.col("asset_id").isNotNull())
    unmatched = joined.filter(F.col("asset_id").isNull())

    counts = {r["reason"]: r["n"] for r in
              df.filter(F.col("reason").isNotNull()).groupBy("reason").agg(F.count(F.lit(1)).alias("n")).collect()}
    n_unmatched = unmatched.count()
    for reason in ("missing_work_order", "unparseable_timestamp"):
        dq.record("maintenance", reason, counts.get(reason, 0), total,
                  threshold_key=f"maintenance_{reason}_rate_max")
    dq.record("maintenance", "unmatched_asset", n_unmatched, total,
              threshold_key="maintenance_unmatched_asset_rate_max")
    dq.info("maintenance", "rows_in", total, "raw CSV rows")

    cols = ["wo_number", "asset_text", "opened_at_utc"]
    rejects = df.filter(F.col("reason").isNotNull()).select(*cols, "reason")
    unmatched_rows = unmatched.select(*cols, F.lit("unmatched_asset").alias("reason"))
    _write_parquet(rejects.unionByName(unmatched_rows), quarantine_dir / "maintenance")

    return matched.select("wo_number", "asset_id", "asset_text", "opened_at_utc",
                          F.col("activity_type"), "is_failure", "match_confidence")


def run_pipeline(spark: SparkSession, cfg: dict, root: Path, out: Path, dq: DQReport) -> dict:
    """Run the full ingest -> model pipeline and write Parquet outputs under ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    model_dir = out / "model"
    quarantine_dir = out / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    er = cfg["entity_resolution"]
    thresholds = cfg["dq_thresholds"]

    assets, aliases = load_register(spark, root / cfg["asset_register"]["path"], cfg["asset_register"], er)
    assets = assets.cache()
    n_assets = assets.count()
    n_unassigned = assets.filter(F.col("id_status") == "unassigned").count()
    dq.record("asset_register", "assets_without_register_id", n_unassigned, n_assets,
              threshold_key="register_missing_id_max", mode="count_max",
              detail="canonical id derived from asset name")
    dq.info("asset_register", "assets_loaded", n_assets, "distinct assets in register")

    raw_r = _read_csv(spark, root / cfg["readings"]["path"], cfg["readings"]["columns"]).cache()
    raw_m = _read_csv(spark, root / cfg["maintenance"]["path"], cfg["maintenance"]["columns"]).cache()

    names = (raw_r.select(F.lit("readings").alias("source"), F.col("equipment").alias("raw_name"))
             .unionByName(raw_m.select(F.lit("maintenance").alias("source"),
                                       F.col("asset_text").alias("raw_name"))))
    names = names.filter(F.col("raw_name").isNotNull() & (F.col("raw_name") != ""))
    emap = resolve_entities(names, aliases, er).cache()
    for row in emap.groupBy("source", "status").count().orderBy("source", "status").collect():
        dq.info("entity_resolution", f"{row['source']}_names_{row['status']}", row["count"],
                "distinct raw names")
    unresolved = emap.filter(F.col("status") != "matched").orderBy("source", "raw_name").collect()
    dq.add_list("Unresolved asset names (review queue)",
                [f"{r['source']}: '{r['raw_name']}' -> {r['asset_id'] or 'no candidate'} "
                 f"(status {r['status']}, confidence {r['confidence']})" for r in unresolved])
    _write_csv(out / "entity_review_queue.csv",
               ["source", "raw_name", "suggested_asset_id", "confidence", "status", "second_candidate"],
               [[r["source"], r["raw_name"], r["asset_id"], r["confidence"], r["status"], r["second_asset"]]
                for r in unresolved])

    readings = process_readings(raw_r, cfg["readings"], emap, dq, quarantine_dir)
    maintenance = process_maintenance(raw_m, cfg["maintenance"], emap, dq, quarantine_dir)

    _write_parquet(assets, model_dir / "assets")
    _write_parquet(readings, model_dir / "readings")
    _write_parquet(maintenance, model_dir / "maintenance_events")
    _write_parquet(emap, model_dir / "entity_map")

    return {"assets": n_assets, "readings": readings.count(), "maintenance_events": maintenance.count(),
            "thresholds_loaded": len(thresholds)}


def _render_timestamps(df: DataFrame) -> DataFrame:
    """Format timestamps in Spark (session zone = UTC) so no Python-side zone conversion happens."""
    cols = [F.date_format(F.col(f.name), "yyyy-MM-dd HH:mm:ss").alias(f.name)
            if isinstance(f.dataType, TimestampType) else F.col(f.name)
            for f in df.schema.fields]
    return df.select(*cols)


def run_sql_layer(spark: SparkSession, root: Path, out: Path) -> dict:
    """Register model Parquet as Spark SQL views and run every query in sql/."""
    for view in SQL_VIEWS:
        spark.read.parquet(str(out / "model" / view)).createOrReplaceTempView(view)
    results_dir = out / "sql_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for sql_file in sorted((root / "sql").glob("*.sql")):
        result = _render_timestamps(spark.sql(sql_file.read_text(encoding="utf-8")))
        rows = result.collect()
        _write_csv(results_dir / f"{sql_file.stem}.csv", result.columns, [list(r) for r in rows])
        counts[sql_file.name] = len(rows)
    return counts
