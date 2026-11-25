"""
Scoring the reader and matcher on a corpus of requests
======================================================
    python -m cer_intent.imf.corpus [tests/corpus/intents.jsonl] [--show-failures]

Each case is read (rule reader), matched against the end-to-end flow's network
(two sites over one 60 GHz hop, the backhaul slice in service) at a fixed time,
and compared field by field with what it should read as. The scores are per field
and per case; CI holds them above thresholds (tests/test_imf_corpus.py).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cer_intent.imf.match import Matcher, Policy
from cer_intent.imf.model import IntentRecord
from cer_intent.imf.network import NetworkModel
from cer_intent.imf.reader import RuleReader

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "tests" / "corpus" / "intents.jsonl"
NOW = dt.datetime(2026, 11, 25, 10, 0)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    return str(a).lower() == str(b).lower()


def evaluate(text: str, net: Optional[NetworkModel] = None) -> Tuple[IntentRecord, List[Any]]:
    net = net or NetworkModel.demo()
    reading = RuleReader(net.names(), NOW).read(text)
    rec = IntentRecord(text=text, expectations=reading.expectations, out_of_scope=reading.out_of_scope)
    questions = Matcher(net, Policy()).match(rec)
    return rec, questions


def check_case(case: Dict[str, Any], net: Optional[NetworkModel] = None) -> Dict[str, bool]:
    exp = case["expect"]
    rec, questions = evaluate(case["text"], net)
    got: Dict[str, bool] = {}
    kinds = [e.kind.value for e in rec.expectations if not (e.kind.value == "ask" and e.action.get("type") == "unknown")]
    got["kinds"] = kinds == exp["kinds"]
    got["out_of_scope"] = bool(rec.out_of_scope) == bool(exp.get("out_of_scope"))
    e = rec.expectations[0] if rec.expectations else None
    if e is None:
        for k in exp:
            if k not in ("kinds", "out_of_scope"):
                got[k] = False
        return got
    if "endpoints" in exp:
        got["endpoints"] = [x.node for x in e.object.endpoints] == exp["endpoints"]
    if "ids" in exp:
        got["ids"] = all(i in e.object.ids for i in exp["ids"])
    if "targets" in exp:
        ok = True
        for metric, (op, value) in exp["targets"].items():
            t = e.target(metric)
            if t is None or not _same(t.value, value) or (op != t.op and not (op == "ge" and t.op == "gt") and not (op == "le" and t.op == "lt")):
                ok = False
        got["targets"] = ok
    if "contexts" in exp:
        have = {c.kind for c in e.contexts}
        got["contexts"] = set(exp["contexts"]) <= have
    if "action" in exp:
        got["action"] = _same(e.action.get("op"), exp["action"])
    if "rule" in exp:
        got["rule"] = _same(e.action.get("rule"), exp["rule"])
    if "question_type" in exp:
        got["question_type"] = _same(e.action.get("question"), exp["question_type"])
    if "metric" in exp:
        got["metric"] = (e.action.get("metrics") or [None])[0] == exp["metric"]
    if "profile" in exp:
        got["profile"] = e.profile == exp["profile"]
    if "strictness" in exp:
        got["strictness"] = e.strictness.value == exp["strictness"]
    if "priority" in exp:
        got["priority"] = e.priority == exp["priority"]
    if "name" in exp:
        got["name"] = e.name == exp["name"]
    if "revert" in exp:
        got["revert"] = bool(e.action.get("revert")) == bool(exp["revert"])
    if "shed" in exp:
        got["shed"] = e.action.get("shed_first") == exp["shed"]
    if "question" in exp:
        got["question"] = any(q.field == exp["question"] for q in questions)
    return got


def score(path: Path = DEFAULT, show: bool = False) -> Dict[str, Any]:
    cases = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    net = NetworkModel.demo()
    fields: Dict[str, List[bool]] = defaultdict(list)
    whole, failures = [], []
    for c in cases:
        got = check_case(c, net)
        for k, v in got.items():
            fields[k].append(v)
        ok = all(got.values())
        whole.append(ok)
        if not ok:
            failures.append({"text": c["text"], "failed": [k for k, v in got.items() if not v]})
    out = {"cases": len(cases), "all_fields": round(sum(whole) / len(whole), 4),
           "fields": {k: {"n": len(v), "accuracy": round(sum(v) / len(v), 4)} for k, v in sorted(fields.items())},
           "failures": failures}
    if show:
        print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1))
        for f in failures:
            print(f"  ✗ {f['text']}  [{', '.join(f['failed'])}]")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    score(Path(args[0]) if args else DEFAULT, show=True)
