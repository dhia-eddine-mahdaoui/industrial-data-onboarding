from datetime import datetime, timezone

import pytest
from pyspark.sql import functions as F

from pipeline.transforms import alias_key, dedupe, parse_timestamp, to_si

ABBR = {"pump": "pmp", "compressor": "cmp", "motor": "mtr", "exchanger": "hx"}
STOP = {"north", "old", "unit", "asset", "the"}
TS_CFG = {
    "offset_formats": ["yyyy-MM-dd'T'HH:mm:ssXXX"],
    "naive_formats": ["dd/MM/yyyy HH:mm"],
    "naive_timezone": "Europe/Berlin",
    "epoch_seconds": True,
}


@pytest.mark.parametrize("text, expected", [
    ("Pump 3A", "pmp3a"),
    ("PMP-03A", "pmp3a"),
    ("pump3a north", "pmp3a"),
    ("PMP03A", "pmp3a"),
    ("Feed Pump 3 (old)", "feedpmp3"),
    ("MTR 02", "mtr2"),
    ("Compressor C-7", "cmpc7"),
    (None, ""),
])
def test_alias_key_normalises_asset_names(text, expected):
    assert alias_key(text, ABBR, STOP) == expected


def test_parse_timestamp_normalises_mixed_formats_to_utc(spark):
    # Rendered as text in the session zone (UTC) to avoid Python-side time zone conversion.
    epoch = str(int(datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc).timestamp()))
    cases = {
        "2026-09-01T06:00:00Z": "2026-09-01 06:00",
        "2026-09-01T08:00:00+02:00": "2026-09-01 06:00",
        "01/09/2026 08:00": "2026-09-01 06:00",   # Berlin summer time, UTC+2
        "01/01/2026 12:00": "2026-01-01 11:00",   # Berlin winter time, UTC+1
        epoch: "2026-09-01 06:00",
        "2026/09/01 0800": None,                  # unparseable
    }
    df = spark.createDataFrame([(k,) for k in cases], "raw string")
    rendered = F.date_format(parse_timestamp(F.col("raw"), TS_CFG), "yyyy-MM-dd HH:mm")
    got = {r.raw: r.ts for r in df.select("raw", rendered.alias("ts")).collect()}
    for raw, expected in cases.items():
        assert got[raw] == expected, raw


def test_to_si_converts_units_and_flags_unknown(spark):
    conv = {
        "c": {"quantity": "temperature", "scale": 1.0, "offset": 0.0},
        "degf": {"quantity": "temperature", "scale": 5 / 9, "offset": -160 / 9},
        "bar": {"quantity": "pressure", "scale": 100.0, "offset": 0.0},
        "psi": {"quantity": "pressure", "scale": 6.894757, "offset": 0.0},
    }
    df = spark.createDataFrame([(140.0, "degF"), (4.5, "bar"), (65.2672, "psi"), (10.0, "K")],
                               "v double, u string")
    si, quantity = to_si(F.col("v"), F.col("u"), conv)
    rows = df.select(si.alias("si"), quantity.alias("q")).collect()
    assert rows[0].si == pytest.approx(60.0, abs=1e-6)          # 140 F = 60 C
    assert rows[1].si == pytest.approx(450.0, abs=1e-6)         # 4.5 bar = 450 kPa
    assert rows[2].si == pytest.approx(450.0, abs=0.01)         # 65.2672 psi = 450 kPa
    assert rows[3].si is None and rows[3].q is None             # unknown unit


def test_dedupe_keeps_first_row_per_key(spark):
    df = spark.createDataFrame([("a", 1, 10), ("a", 1, 11), ("b", 1, 12)],
                               "asset string, sensor int, _row_id long")
    out = {(r.asset, r.sensor): r._row_id for r in dedupe(df, ["asset", "sensor"]).collect()}
    assert out == {("a", 1): 10, ("b", 1): 12}
