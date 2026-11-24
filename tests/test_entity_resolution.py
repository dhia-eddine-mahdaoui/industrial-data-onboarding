from pipeline.entity_resolution import resolve_entities

ER = {
    "stopwords": ["north", "south", "old", "unit", "asset", "the"],
    "abbreviations": {"pump": "pmp", "compressor": "cmp", "motor": "mtr", "exchanger": "hx"},
    "auto_accept": 0.92,
    "review_min": 0.75,
    "ambiguity_margin": 0.02,
}


def _resolve(spark, names):
    aliases = spark.createDataFrame([
        ("PMP-03A", "PMP-03A"),
        ("PMP-03A", "Feed Pump 3 (old)"),
        ("PMP-03B", "PMP-03B"),
        ("CMP-01", "CMP-01"),
    ], "asset_id string, alias_text string")
    rows = spark.createDataFrame([("readings", n) for n in names], "source string, raw_name string")
    return {r.raw_name: r for r in resolve_entities(rows, aliases, ER).collect()}


def test_exact_and_fuzzy_matches_with_review_and_unmatched(spark):
    res = _resolve(spark, [
        "Pump 3A",          # exact key
        "pump3a north",     # exact key after stopword removal
        "P-3A (north)",     # fuzzy, between review_min and auto_accept
        "Pump 3",           # ties PMP-03A and PMP-03B
        "PMP-03B",          # exact
        "Pump 9",           # below review_min
        "Compressor C-7",   # below review_min
    ])
    assert res["Pump 3A"].asset_id == "PMP-03A" and res["Pump 3A"].status == "matched"
    assert res["Pump 3A"].method == "exact_key" and res["Pump 3A"].confidence == 1.0
    assert res["pump3a north"].status == "matched"
    assert res["P-3A (north)"].asset_id == "PMP-03A"
    assert res["P-3A (north)"].status == "review" and res["P-3A (north)"].method == "fuzzy"
    assert res["Pump 3"].status == "review"          # ambiguous between two assets
    assert res["PMP-03B"].asset_id == "PMP-03B" and res["PMP-03B"].status == "matched"
    assert res["Pump 9"].status == "unmatched" and res["Pump 9"].asset_id is None
    assert res["Compressor C-7"].status == "unmatched"


def test_renamed_legacy_name_resolves_through_alias(spark):
    res = _resolve(spark, ["Feed Pump 3 (old)"])
    assert res["Feed Pump 3 (old)"].asset_id == "PMP-03A"
    assert res["Feed Pump 3 (old)"].status == "matched"
