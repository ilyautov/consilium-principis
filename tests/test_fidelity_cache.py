"""C5 + H10: нормализованные чанки корпуса и лексюниты кешируются по (path, mtime).
best_match зовётся на ~56 кандидатов → без кеша полный ре-скан corpus.jsonl ×56.
Кеш инвалидируется сменой mtime (пересборка корпуса) — fail-safe, не stale."""
import os
import sys
import builtins
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def _counting_open(monkeypatch):
    real_open = builtins.open
    calls = {"n": 0}
    def counting(*a, **k):
        if a and str(a[0]).endswith("corpus.jsonl"):
            calls["n"] += 1
        return real_open(*a, **k)
    monkeypatch.setattr(builtins, "open", counting)
    return calls


def test_corpus_cached_by_mtime(tmp_path, monkeypatch):
    import engine.fidelity as F
    F._CHUNK_CACHE.clear()
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    corp = adv / "build" / "corpus.jsonl"
    corp.write_text('{"text":"the quick brown fox jumps far","tier":"P1"}\n', encoding="utf-8")
    calls = _counting_open(monkeypatch)
    F.best_match("the quick brown fox jumps far", str(adv))
    F.best_match("the quick brown fox jumps far", str(adv))
    assert calls["n"] == 1                        # второй вызов из кеша
    corp.write_text('{"text":"a wholly different sentence here","tier":"P1"}\n', encoding="utf-8")
    os.utime(corp, (9e9, 9e9))
    F.best_match("a wholly different sentence here", str(adv))
    assert calls["n"] == 2                         # mtime сменился → ре-чтение


def test_lexical_units_cached_by_mtime(tmp_path, monkeypatch):
    import engine.lexical as L
    L._UNITS_CACHE.clear()
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    corp = adv / "build" / "corpus.jsonl"
    corp.write_text('{"text":"the quick brown fox jumps far.","tier":"P1"}\n', encoding="utf-8")
    calls = _counting_open(monkeypatch)
    L._split_units(str(adv)); L._split_units(str(adv))
    assert calls["n"] == 1
    corp.write_text('{"text":"a wholly different sentence here now.","tier":"P1"}\n', encoding="utf-8")
    os.utime(corp, (9e9, 9e9))
    L._split_units(str(adv))
    assert calls["n"] == 2
