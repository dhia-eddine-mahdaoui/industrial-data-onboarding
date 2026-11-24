"""Asset-name entity resolution.

Each raw name (from a readings export or a maintenance log) is normalised to a
key and compared with the keys of every register alias. The best candidate
gets a confidence score in [0, 1]. Status is:
  matched    score >= auto_accept and no competing asset within ambiguity_margin
  review     review_min <= score < auto_accept, or two assets tie
  unmatched  no candidate, or score < review_min
Only "matched" names flow into the asset model; the rest form a review queue.
"""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType
from pyspark.sql.window import Window

from pipeline.transforms import alias_key, similarity


def make_key_udf(er: dict):
    abbreviations = {str(k).lower(): str(v).lower() for k, v in (er.get("abbreviations") or {}).items()}
    stopwords = {str(w).lower() for w in (er.get("stopwords") or [])}
    return F.udf(lambda text: alias_key(text, abbreviations, stopwords), StringType())


def resolve_entities(names: DataFrame, aliases: DataFrame, er: dict) -> DataFrame:
    """Resolve (source, raw_name) pairs against (asset_id, alias_text) pairs."""
    key = make_key_udf(er)
    sim = F.udf(similarity, DoubleType())
    auto = float(er["auto_accept"])
    review_min = float(er["review_min"])
    margin = float(er["ambiguity_margin"])

    names_k = (names.select("source", "raw_name").distinct()
                    .withColumn("alias_key", key(F.col("raw_name"))))
    alias_k = (aliases.withColumn("cand_key", key(F.col("alias_text")))
                      .filter(F.col("cand_key") != "")
                      .select("asset_id", "cand_key").distinct())

    cand = names_k.crossJoin(alias_k).withColumn("score", sim(F.col("alias_key"), F.col("cand_key")))
    # one candidate per asset (its best alias), so a second alias of the same asset is not a rival
    per_asset = Window.partitionBy("source", "raw_name", "asset_id").orderBy(F.desc("score"))
    cand = (cand.withColumn("ar", F.row_number().over(per_asset))
                .filter(F.col("ar") == 1).drop("ar"))
    window = Window.partitionBy("source", "raw_name").orderBy(F.desc("score"), F.asc("asset_id"))
    ranked = cand.withColumn("rk", F.row_number().over(window))
    best = (ranked.filter(F.col("rk") == 1)
                  .select("source", "raw_name",
                          F.col("asset_id").alias("best_asset"),
                          F.col("score").alias("best_score")))
    second = (ranked.filter(F.col("rk") == 2)
                    .select("source", "raw_name",
                            F.col("asset_id").alias("second_asset"),
                            F.col("score").alias("second_score")))

    out = (names_k.join(best, ["source", "raw_name"], "left")
                  .join(second, ["source", "raw_name"], "left"))
    score = F.coalesce(F.col("best_score"), F.lit(0.0))
    ambiguous = (F.col("second_asset").isNotNull()
                 & (F.col("second_asset") != F.col("best_asset"))
                 & (F.col("second_score") >= score - margin))
    status = (F.when(F.col("best_asset").isNull() | (score < review_min), F.lit("unmatched"))
               .when(ambiguous | (score < auto), F.lit("review"))
               .otherwise(F.lit("matched")))
    method = (F.when(F.col("best_asset").isNull(), F.lit("none"))
               .when(score >= 1.0, F.lit("exact_key"))
               .otherwise(F.lit("fuzzy")))
    return out.select(
        "source", "raw_name", "alias_key",
        F.when(status != "unmatched", F.col("best_asset")).alias("asset_id"),
        F.round(score, 3).alias("confidence"),
        method.alias("method"),
        status.alias("status"),
        F.col("second_asset"),
        F.round(F.col("second_score"), 3).alias("second_score"),
    )
