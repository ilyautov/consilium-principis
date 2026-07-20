"""Контрактные тесты scripts/gen_golden.py (генератор eval-golden) — нулевое покрытие (M7).

Без сети: LLM-вызов мокается (gen_questions / urlopen), корпус — синтетика на tmp_path.
Контракт: стратификация отбраковывает служебные чанки, anchor = характерное предложение,
run() пишет meta-головой + по строке на вопрос (target_tier=P1, anchor ⊂ чанк).
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import gen_golden as g


def _chunk(text, source="book.txt"):
    return {"text": text, "source": source}


_SENT = "Courage is the quiet stand of reason against the sudden pull of fear and doubt."  # 83 симв
_FILLER = " ".join(["Filler words extend the chunk body far beyond the stratify floor."] * 12)


# ───────────────────────── stratified ─────────────────────────

def test_stratified_filters_short_and_service_chunks():
    good = _chunk(_FILLER)
    short = _chunk("слишком короткий чанк")
    service = _chunk("# SOURCE: x.txt\n" + _FILLER)
    out = g.stratified([short, service, good], k=10)
    assert out == [good]                       # k > |good| → все хорошие, брак отброшен


def test_stratified_spreads_evenly_over_corpus():
    chunks = [_chunk(_FILLER + " #%d" % i) for i in range(10)]
    out = g.stratified(chunks, 3)
    assert len(out) == 3
    assert out[0] is chunks[0]                 # равномерно от начала (step = 10/3)
    assert all(c in chunks for c in out)


# ───────────────────────── anchor_of ─────────────────────────

def test_anchor_of_picks_longest_valid_sentence():
    text = "Short one. %s Tiny. %s" % (_SENT, "A" * 150)
    assert g.anchor_of(text) == "A" * 150      # самое длинное в окне 30..200


def test_anchor_of_returns_none_when_no_sentence_fits():
    assert g.anchor_of("Too small. Also tiny.") is None
    assert g.anchor_of("X" * 250) is None      # длиннее 200 и без точки — не предложение


# ───────────────────────── gen_questions (парс ответа LLM) ─────────────────────────

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


def test_gen_questions_parses_literal_and_abstract(monkeypatch):
    payload = json.dumps({"response": "LITERAL: Direct question here?\n"
                                      "ABSTRACT: Conceptual one without terms?\n"}).encode()
    monkeypatch.setattr(g.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(payload))
    lit, ab = g.gen_questions("Author", "passage", "m")
    assert lit == "Direct question here?"
    assert ab == "Conceptual one without terms?"


def test_gen_questions_tolerates_dash_and_missing_lines(monkeypatch):
    payload = json.dumps({"response": "abstract- only abstract?\nnoise line\n"}).encode()
    monkeypatch.setattr(g.urllib.request, "urlopen", lambda req, timeout=0: _FakeResp(payload))
    lit, ab = g.gen_questions("Author", "passage", "m")
    assert lit is None and ab == "only abstract?"


# ───────────────────────── run() сквозной на tmp ─────────────────────────

def test_run_writes_meta_head_and_pair_records(tmp_path, monkeypatch):
    slug = "demo-figure"
    corpus_dir = tmp_path / "advisors" / slug / "build"
    corpus_dir.mkdir(parents=True)
    texts = []
    for i in range(2):
        text = "%s %s" % (_SENT, _FILLER + " variant %d." % i)
        texts.append(text)
        (corpus_dir / "corpus.jsonl").write_text(
            "".join(json.dumps(_chunk(t, source="src%d.txt" % j), ensure_ascii=False) + "\n"
                    for j, t in enumerate(texts)),
            encoding="utf-8")
    (tmp_path / "scripts" / "golden").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(g, "gen_questions",
                        lambda author, passage, model: ("Literal question about this?",
                                                        "Abstract question without terms?"))
    g.run(slug, k=5, model="m")

    out = tmp_path / "scripts" / "golden" / ("%s.auto.jsonl" % slug)
    rows = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    meta, data = rows[0], rows[1:]
    assert meta["_meta"]["advisor"] == slug and len(meta["_meta"]["corpus_sha12"]) == 12
    assert len(data) == 4                       # 2 чанка × (literal + abstract)
    by_diff = {(r["q"], r["difficulty"]) for r in data}
    assert ("Literal question about this?", "literal") in by_diff
    assert ("Abstract question without terms?", "abstract") in by_diff
    for r in data:
        assert r["target_tier"] == "P1"
        assert r["anchor"] == _SENT             # якорь — дословная подстрока чанка (hit-проверка eval)
        assert any(r["anchor"] in t for t in texts)
        assert r["source"].startswith("src")


def test_run_skips_chunks_without_anchor(tmp_path, monkeypatch, capsys):
    slug = "no-anchor"
    corpus_dir = tmp_path / "advisors" / slug / "build"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / "corpus.jsonl").write_text(
        json.dumps(_chunk("nocapitalsentence " * 40)) + "\n",   # нет предложения 30..200 → anchor None
        encoding="utf-8")
    (tmp_path / "scripts" / "golden").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(g, "gen_questions", lambda *a: ("Q one here?", "Q two here?"))
    g.run(slug, k=5, model="m")
    rows = [json.loads(ln) for ln in
            (tmp_path / "scripts" / "golden" / ("%s.auto.jsonl" % slug))
            .read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert all("_meta" in r for r in rows)      # вопросов без якоря нет — только meta-голова
