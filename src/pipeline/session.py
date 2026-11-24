"""Spark session factory for local runs and tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession

SRC_DIR = Path(__file__).resolve().parents[1]


def get_spark(app_name: str, timezone: str = "UTC") -> SparkSession:
    """Local SparkSession (4 cores and 2g by default; override with SPARK_LOCAL_CORES / SPARK_DRIVER_MEMORY).

    The session time zone is set so naive timestamps are predictable.

    Worker processes need to import the pipeline package, so src/ is put on
    PYTHONPATH before the JVM launches its Python workers.
    """
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ["PYTHONPATH"] = os.pathsep.join(
        p for p in [str(SRC_DIR), os.environ.get("PYTHONPATH", "")] if p)
    spark = (SparkSession.builder
             .master(f"local[{os.environ.get('SPARK_LOCAL_CORES', '4')}]")
             .config("spark.driver.memory", os.environ.get("SPARK_DRIVER_MEMORY", "2g"))
             .appName(app_name)
             .config("spark.sql.session.timeZone", timezone)
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.driver.host", "localhost")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark
