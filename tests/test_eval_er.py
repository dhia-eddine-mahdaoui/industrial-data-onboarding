from pipeline.eval_er import score_rows


def row(source, raw, status, predicted, truth, method="fuzzy"):
    return {"source": source, "raw_name": raw, "status": status, "method": method,
            "confidence": 0.9, "predicted": predicted, "truth": truth}


def test_precision_recall_and_review_assist():
    rows = [
        row("maintenance", "a", "matched", "Pump A", "Pump A", "exact_key"),   # correct
        row("maintenance", "b", "matched", "Pump A", "Pump B"),                # false accept
        row("maintenance", "c", "review", "Pump C", "Pump C"),                 # fixable by review
        row("maintenance", "d", "unmatched", None, "Pump D"),                  # missed
        row("maintenance", "e", "matched", "Pump A", ""),                      # out-of-register accepted
        row("maintenance", "f", "unmatched", None, ""),                        # correctly rejected
    ]
    res = score_rows(rows)
    o = res["overall"]
    assert (o["accepted"], o["correct"], o["false_accepts"]) == (3, 1, 2)
    assert o["precision"] == round(1 / 3, 4)
    assert o["recall"] == 0.25 and o["assisted_recall"] == 0.5     # 4 in-register names
    assert o["out_of_register_rejected"] == 1
    assert res["exact_key_only_baseline"]["accepted"] == 1
    assert {e["raw_name"] for e in res["errors"]} == {"b", "c", "d", "e"}
