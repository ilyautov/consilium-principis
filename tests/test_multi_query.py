"""Контрактные тесты scripts/engine/multi_query.py (левер 2: multi-query / STORM) — M7.

Без сети: ollama-вызов мокается через urlopen. Контракт: варианты чистятся от нумерации/
буллетов, кириллический код-микс отбраковывается (ретрив хоронит мусор), кап n держится;
multiquery_retrieve сливает выдачи вариантов через RRF, query_lex=сам вариант (hybrid),
с фолбэком на легаси-сигнатуру retrieve без query_lex (TypeError).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import engine.multi_query as mq
from engine import Passage


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def _mock_ollama(monkeypatch, response_text):
    payload = json.dumps({"response": response_text}).encode()
    monkeypatch.setattr(mq.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(payload))


# ───────────────────────── generate_variants ─────────────────────────

def test_generate_variants_strips_numbering_and_bullets(monkeypatch):
    _mock_ollama(monkeypatch, (
        "1. How does a fox outwit every trap set for it?\n"
        "- When should a prudent prince feign virtue?\n"
        "• Why do fortresses crumble from within slowly?\n"
        "3) What makes cruelty well used different in kind?\n"))
    out = mq.generate_variants("q", lenses=["лиса и лев"], n=5)
    assert out == ["How does a fox outwit every trap set for it?",
                   "When should a prudent prince feign virtue?",
                   "Why do fortresses crumble from within slowly?",
                   "What makes cruelty well used different in kind?"]


def test_generate_variants_drops_cyrillic_mix_and_short_lines(monkeypatch):
    _mock_ollama(monkeypatch, (
        "Протёкшая кириллица в варианте хоронит ретрив\n"
        "tiny\n"
        "A clean english variant that survives the filter?\n"))
    out = mq.generate_variants("q", lenses=[], n=5)
    assert out == ["A clean english variant that survives the filter?"]


def test_generate_variants_caps_at_n(monkeypatch):
    _mock_ollama(monkeypatch, "\n".join("Variant number %d with enough length?" % i for i in range(10)))
    assert len(mq.generate_variants("q", lenses=[], n=3)) == 3


def test_generate_variants_empty_llm_output(monkeypatch):
    _mock_ollama(monkeypatch, "")
    assert mq.generate_variants("q", lenses=["лиса"], n=5) == []


# ───────────────────────── multiquery_retrieve ─────────────────────────

class _HybridEngine:
    """retrieve с query_lex (hybrid-сигнатура): запоминает, что query_lex = сам вариант."""
    def __init__(self, by_query):
        self._by = by_query
        self.seen = []

    def retrieve(self, q, advisor_dir, top_k=3, query_lex=None):
        self.seen.append((q, query_lex))
        return self._by[q]


class _LegacyEngine:
    """retrieve БЕЗ query_lex (semantic/lexical) → TypeError-фолбэк внутри multiquery."""
    def __init__(self, by_query):
        self._by = by_query

    def retrieve(self, q, advisor_dir, top_k=3):
        return self._by[q]


def _hits():
    shared = Passage(text="Shared chunk both variants found", score=0.9, source="s.txt", tier="P1")
    solo = Passage(text="Chunk only one variant found", score=0.99, source="s.txt", tier="P1")
    return {"v-one": [solo], "v-two": [shared, solo], "v-three": [shared]}


def test_multiquery_retrieve_rrf_prefers_shared_passage():
    eng = _HybridEngine(_hits())
    fused = mq.multiquery_retrieve(eng, "advisors/x", ["v-one", "v-two", "v-three"], top_k=2)
    assert fused[0].text == "Shared chunk both variants found"   # RRF-консенсус > сырой top-1
    assert len(fused) == 2                                       # top_k уважается


def test_multiquery_retrieve_passes_query_lex_equal_to_variant():
    eng = _HybridEngine(_hits())
    mq.multiquery_retrieve(eng, "advisors/x", ["v-one", "v-two"], top_k=3)
    assert eng.seen == [("v-one", "v-one"), ("v-two", "v-two")]  # вариант = query_lex сам себе


def test_multiquery_retrieve_falls_back_for_legacy_signature():
    eng = _LegacyEngine(_hits())
    fused = mq.multiquery_retrieve(eng, "advisors/x", ["v-two", "v-three"], top_k=5)
    assert fused and fused[0].text == "Shared chunk both variants found"
