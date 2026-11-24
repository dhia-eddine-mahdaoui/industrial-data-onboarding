"""Export the Parquet asset model to a single DuckDB file.

Customer analysts get one portable file they can open with any DuckDB client
and query with the same SQL that the Spark layer runs. Two Spark functions the
queries use (unix_timestamp, to_date) are defined as DuckDB macros so the
files in sql/ stay the single source of truth.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

TABLES = ["assets", "readings", "maintenance_events", "entity_map"]


def export_duckdb(out: Path, root: Path) -> dict:
    """Write out/model.duckdb with the model tables and one view per sql/*.sql file."""
    db_path = out / "model.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        con.execute("SET TimeZone = 'UTC'")
        for table in TABLES:
            pattern = (out / "model" / table / "*.parquet").as_posix()
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet('{pattern}')")
        con.execute("CREATE OR REPLACE MACRO unix_timestamp(t) AS epoch(CAST(t AS TIMESTAMPTZ))")
        con.execute("CREATE OR REPLACE MACRO to_date(t) AS CAST(t AS DATE)")
        views = []
        for sql_file in sorted((root / "sql").glob("*.sql")):
            name = "q" + sql_file.stem
            con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql_file.read_text(encoding='utf-8')}")
            views.append(name)
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
        counts.update({v: con.execute(f"SELECT count(*) FROM {v}").fetchone()[0] for v in views})
    finally:
        con.close()
    return counts
