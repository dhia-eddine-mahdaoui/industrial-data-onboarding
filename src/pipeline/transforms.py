"""Column-level transforms: timestamps, units, asset-name keys, de-duplication."""
from __future__ import annotations

import difflib
import re

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

SI_UNIT_BY_QUANTITY = {"temperature": "degC", "pressure": "kPa"}
EPOCH_RE = r"^[0-9]{9,11}$"
_WORD = re.compile(r"[a-z]+|[0-9]+")


def alias_key(text, abbreviations: dict, stopwords: set) -> str:
    """Normalise a free-text asset name into a comparable key.

    Letter/digit runs are split, stopwords dropped, abbreviations expanded and
    leading zeros removed: 'Pump 3A', 'PMP-03A' and 'pump3a north' -> 'pmp3a'.
    """
    if text is None:
        return ""
    parts = []
    for word in _WORD.findall(str(text).lower()):
        if word in stopwords:
            continue
        if word.isdigit():
            word = str(int(word))
        parts.append(abbreviations.get(word, word))
    return "".join(parts)


def similarity(a, b) -> float:
    """Sequence similarity in [0, 1] between two normalised keys."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def parse_timestamp(col: Column, cfg: dict) -> Column:
    """Parse a raw timestamp column into a UTC timestamp.

    Tries, in order: unix epoch seconds, strings carrying their own offset or Z,
    and naive wall-clock strings interpreted in ``naive_timezone``. Requires the
    Spark session time zone to be UTC (see pipeline.session).
    """
    text = F.trim(col.cast("string"))
    parts = []
    if cfg.get("epoch_seconds", False):
        parts.append(F.when(text.rlike(EPOCH_RE), F.timestamp_seconds(text.cast("long"))))
    offset_fmts = cfg.get("offset_formats") or []
    if offset_fmts:
        parts.append(F.coalesce(*[F.to_timestamp(text, fmt) for fmt in offset_fmts]))
    naive_fmts = cfg.get("naive_formats") or []
    if naive_fmts:
        naive = F.coalesce(*[F.to_timestamp(text, fmt) for fmt in naive_fmts])
        parts.append(F.to_utc_timestamp(naive, cfg["naive_timezone"]))
    return F.coalesce(*parts)


def to_si(value: Column, unit: Column, conversions: dict):
    """Convert a raw value to SI using a unit table.

    Returns (si_value, quantity). Unknown units give nulls for both, so the
    caller can quarantine them. Conversion is linear: si = value * scale + offset.
    """
    key = F.lower(F.trim(unit))
    si = F.lit(None).cast("double")
    quantity = F.lit(None).cast("string")
    for raw_unit, spec in conversions.items():
        cond = key == F.lit(str(raw_unit).lower())
        si = F.when(cond, value * float(spec["scale"]) + float(spec["offset"])).otherwise(si)
        quantity = F.when(cond, F.lit(str(spec["quantity"]))).otherwise(quantity)
    return si.cast("double"), quantity


def dedupe(df: DataFrame, keys: list[str]) -> DataFrame:
    """Keep the first row (by the internal _row_id) for each key combination."""
    window = Window.partitionBy(*keys).orderBy("_row_id")
    return (df.withColumn("_rn", F.row_number().over(window))
              .filter(F.col("_rn") == 1)
              .drop("_rn"))
