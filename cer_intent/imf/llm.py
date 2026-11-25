"""
Language-model readers, held to the same record as the rules
============================================================
The rule reader always runs. A language model, when one is configured, reads the
same words into the same JSON (cer_intent/imf/model.py:reading_schema) and the
two readings are compared:

  * where both read the same thing, the reading stands as stated;
  * where the rules found nothing, the model's reading is used and every value
    it supplies is marked "model": an acting value is confirmed by the operator
    before it changes the network;
  * where they disagree, the rules' value is kept and the disagreement is shown.

Providers (CER_IMF_LLM):
  gemini      Google Gemini REST API     GEMINI_API_KEY, CER_IMF_GEMINI_MODEL
  anthropic   Anthropic Messages API     ANTHROPIC_API_KEY, CER_IMF_ANTHROPIC_MODEL
  openai      any OpenAI-compatible API  CER_IMF_OPENAI_URL, CER_IMF_OPENAI_KEY, CER_IMF_OPENAI_MODEL
              (a local vLLM or Ollama server works the same way)
  recorded    readings stored in a file  CER_IMF_RECORDED (JSON: text -> reading)
  none        rules only (default)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from cer_intent.imf.model import Expectation, Kind, Reading, Source

KIND_HELP = {
    "deliver": "create connectivity between two sites (a slice / VPN)",
    "change": "modify an existing slice: bandwidth, latency, VLAN, modulation floor, priority",
    "lifecycle": "suspend, resume or remove existing slices",
    "keep": "a standing objective that must keep holding (bandwidth >= X, availability >= Y)",
    "optimise": "minimise or maximise something (energy, latency) under constraints",
    "guard": "a rule other intents must respect (freeze window, approval, minimum modulation, headroom)",
    "observe": "a report or an alert",
    "explore": "a what-if or headroom question answered on the digital twin; changes nothing",
    "ask": "a question about the network, a slice or a decision",
}


def system_prompt(names: Dict[str, List[str]]) -> str:
    known = "; ".join(f"{k}: {', '.join(v)}" for k, v in names.items() if v) or "none listed"
    kinds = "\n".join(f"  {k}: {v}" for k, v in KIND_HELP.items())
    return (
        "You read requests from the operator of a wireless transport network into JSON.\n"
        "Return one JSON object with key \"expectations\" (a list) and, if the request is not about this network, "
        "\"out_of_scope\" (a short reason). Each expectation has: kind, verb, object {type, mentions, endpoints "
        "[{mention, port, vlan, ip}], selector}, targets [{metric, op, value, unit}], contexts [{kind, params}], "
        "strictness (must|prefer|best_effort), priority (1-8), profile, action, name.\n"
        f"Kinds:\n{kinds}\n"
        "Metrics: bandwidth (Mbps), latency (ms), jitter (ms), loss (%), availability (%), modulation_floor (MCS1-MCS12), "
        "headroom (%), energy (W), tx_power (dBm), vlan, technology (L2VPN|L3VPN).\n"
        "Ops: ge, le, eq, between, minimize, maximize, set, scale, add.\n"
        "Contexts: window {start, end, days, label}, schedule {every, seconds}, weather {rain_mmh}, "
        "condition {metric, op, value, unit}.\n"
        f"Names the network knows: {known}. Use them as written when the request means them.\n"
        "Copy numbers as given; never invent a value the request does not state. JSON only, no prose."
    )


def _json_from(text: str) -> Dict[str, Any]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("no JSON object in the model's answer")
    return json.loads(m.group(0))


def to_reading(data: Dict[str, Any], reader: str) -> Reading:
    """Validate a model's JSON against the reading schema; every value it sets is marked as the model's."""
    exps = []
    for raw in data.get("expectations", []) or []:
        raw = dict(raw)
        if raw.get("kind") not in {k.value for k in Kind}:
            continue
        e = Expectation.model_validate(raw)
        for t in e.targets:
            t.source = Source.MODEL
        for c in e.contexts:
            c.source = Source.MODEL
        e.object.source = Source.MODEL
        exps.append(e)
    return Reading(expectations=exps, out_of_scope=data.get("out_of_scope"), reader=reader)


class Provider:
    name = "none"

    def read(self, text: str, names: Dict[str, List[str]]) -> Optional[Reading]:
        raise NotImplementedError


class RecordedProvider(Provider):
    """Readings stored in a file, keyed by the request text; for tests and offline demos."""
    name = "recorded"

    def __init__(self, path: Optional[str] = None, data: Optional[Dict[str, Any]] = None):
        self.data = data if data is not None else {}
        if path and data is None:
            try:
                self.data = json.loads(Path(path).read_text())
            except (OSError, ValueError):
                self.data = {}

    def read(self, text: str, names: Dict[str, List[str]]) -> Optional[Reading]:
        hit = self.data.get(text.strip())
        return to_reading(hit, f"recorded:{hit.get('_model', 'model')}") if hit else None


class _HttpProvider(Provider):
    def __init__(self, session: Optional[requests.Session] = None, timeout: float = 20.0):
        self.session = session or requests.Session()
        self.timeout = timeout


class GeminiProvider(_HttpProvider):
    name = "gemini"

    def __init__(self, model: Optional[str] = None, key: Optional[str] = None, **kw):
        super().__init__(**kw)
        self.model = model or os.getenv("CER_IMF_GEMINI_MODEL", "gemini-2.5-flash")
        self.key = key or os.getenv("GEMINI_API_KEY", "")

    def read(self, text: str, names: Dict[str, List[str]]) -> Optional[Reading]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system_prompt(names)}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
        r = self.session.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=self.timeout)
        r.raise_for_status()
        out = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return to_reading(_json_from(out), f"gemini:{self.model}")


class AnthropicProvider(_HttpProvider):
    name = "anthropic"

    def __init__(self, model: Optional[str] = None, key: Optional[str] = None, **kw):
        super().__init__(**kw)
        self.model = model or os.getenv("CER_IMF_ANTHROPIC_MODEL", "claude-haiku-5-5")
        self.key = key or os.getenv("ANTHROPIC_API_KEY", "")

    def read(self, text: str, names: Dict[str, List[str]]) -> Optional[Reading]:
        body = {"model": self.model, "max_tokens": 2000, "temperature": 0, "system": system_prompt(names),
                "messages": [{"role": "user", "content": text}]}
        r = self.session.post("https://api.anthropic.com/v1/messages", json=body, timeout=self.timeout,
                              headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        out = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        return to_reading(_json_from(out), f"anthropic:{self.model}")


class OpenAICompatProvider(_HttpProvider):
    name = "openai"

    def __init__(self, model: Optional[str] = None, key: Optional[str] = None, url: Optional[str] = None, **kw):
        super().__init__(**kw)
        self.model = model or os.getenv("CER_IMF_OPENAI_MODEL", "gpt-4o-mini")
        self.key = key or os.getenv("CER_IMF_OPENAI_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.url = (url or os.getenv("CER_IMF_OPENAI_URL", "https://api.openai.com/v1")).rstrip("/")

    def read(self, text: str, names: Dict[str, List[str]]) -> Optional[Reading]:
        body = {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system_prompt(names)}, {"role": "user", "content": text}]}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        r = self.session.post(f"{self.url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"]
        return to_reading(_json_from(out), f"openai:{self.model}")


def provider_from_env() -> Optional[Provider]:
    name = os.getenv("CER_IMF_LLM", "none").strip().lower()
    if name == "gemini" and os.getenv("GEMINI_API_KEY"):
        return GeminiProvider()
    if name == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if name == "openai":
        return OpenAICompatProvider()
    if name == "recorded":
        return RecordedProvider(os.getenv("CER_IMF_RECORDED"))
    return None


# ── comparing two readings ────────────────────────────────────────────────────

def _sig(e: Expectation) -> Tuple[str, Tuple]:
    return e.kind.value, tuple(sorted((t.metric, t.op, str(t.value)) for t in e.targets if t.metric != "technology"))


def merge(rules: Reading, model: Optional[Reading]) -> Tuple[Reading, Dict[str, Any]]:
    """The reading to use, and how the two readers compared."""
    info: Dict[str, Any] = {"rules": [e.summary() for e in rules.expectations], "model": None,
                            "reader": "rules", "agreement": None, "disagreements": []}
    if model is None:
        return rules, info
    info["model"] = [e.summary() for e in model.expectations]
    info["model_reader"] = model.reader
    unread = (not rules.expectations or all(e.kind == Kind.ASK and e.action.get("type") == "unknown"
                                            for e in rules.expectations))
    if rules.out_of_scope and not model.out_of_scope:
        info["disagreements"].append(f"rules: out of scope ({rules.out_of_scope}); model read {len(model.expectations)} expectation(s)")
        return rules, info
    if unread and model.expectations:
        info["reader"] = "model"
        info["agreement"] = 0.0
        return Reading(expectations=model.expectations, out_of_scope=model.out_of_scope, reader=model.reader,
                       notes=["the rules did not read this request; the model's reading is used and confirmed before acting"]), info
    agree = 0
    for i, r in enumerate(rules.expectations):
        m = model.expectations[i] if i < len(model.expectations) else None
        if m is None:
            continue
        if m.kind != r.kind:
            info["disagreements"].append(f"expectation {i + 1}: rules read {r.kind.value}, model read {m.kind.value}")
            continue
        if _sig(m) == _sig(r):
            agree += 1
            continue
        for t in m.targets:
            mine = r.target(t.metric)
            if mine is None:
                r.targets.append(t)            # the model saw a value the rules missed: marked "model"
            elif str(mine.value) != str(t.value) or mine.op != t.op:
                info["disagreements"].append(f"{t.metric}: rules {mine.text()}, model {t.text()}")
    if len(model.expectations) > len(rules.expectations):
        info["disagreements"].append(f"the model read {len(model.expectations) - len(rules.expectations)} more expectation(s)")
    info["agreement"] = round(agree / max(1, len(rules.expectations)), 2)
    info["reader"] = "rules+model"
    return rules, info
