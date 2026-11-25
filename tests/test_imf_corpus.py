"""The reader and matcher on the request corpus (tests/corpus/intents.jsonl), held above thresholds."""
from __future__ import annotations

from cer_intent.imf.corpus import DEFAULT, score

THRESHOLDS = {"kinds": 0.97, "endpoints": 0.97, "targets": 0.95, "ids": 0.95, "contexts": 0.95, "action": 0.95,
              "out_of_scope": 0.97}


def test_the_corpus_reads_as_annotated():
    s = score(DEFAULT)
    assert s["cases"] >= 390
    low = {k: v["accuracy"] for k, v in s["fields"].items() if k in THRESHOLDS and v["accuracy"] < THRESHOLDS[k]}
    assert not low, (low, s["failures"][:10])
    assert s["all_fields"] >= 0.95, s["failures"][:10]
