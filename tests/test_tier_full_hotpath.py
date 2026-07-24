"""Прод-ретрив (engine.retrieval) не строит семантический индекс в hot-path.

Живой инцидент 2026-07-24: FULL-тир на ~2000-чанковом корпусе (Тиньков) инлайн-эмбедил через
ollama > 60с → таймаут MCP-транспорта, агент увидел «нет опоры». Фикс — readiness-гейт:
retrieval.retrieve дёшево спрашивает eng.index_ready() (файлы+fingerprint, без эмбеддинга) и на
несобранном/устаревшем индексе деградирует на лексический пол, НЕ запуская сборку. Явная сборка
живёт в фоновом джобе build_advisor/doctor/build_index.

При этом ПРЯМОЙ вызов tier_full.retrieve по-прежнему авто-лечит недостающий индекс (контракт
immutable generation-publication, tests/test_generation_publication.py) — гейт только на прод-пути.
"""
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import pytest

pytest.importorskip("numpy")   # tier_full импортит numpy на уровне модуля


def _advisor_with_corpus_no_index(tmp_path):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        json.dumps({"text": "деньги любят счёт и терпение", "tier": "P1"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    return str(adv)


def test_index_ready_is_false_when_index_missing_without_building(tmp_path, monkeypatch):
    """index_ready — дешёвая проба: корпус есть, индекса нет → False, и НИКОГДА не зовёт build."""
    import tier_full

    adv = _advisor_with_corpus_no_index(tmp_path)
    monkeypatch.setattr(tier_full, "build_index", lambda a: (_ for _ in ()).throw(
        AssertionError("index_ready не должен строить индекс")))
    monkeypatch.setattr(tier_full, "embed_batch", lambda _t: (_ for _ in ()).throw(
        AssertionError("index_ready не должен эмбедить")))

    assert tier_full.index_ready(adv) is False


def test_engine_retrieval_degrades_to_lexical_when_index_missing(tmp_path, monkeypatch):
    """Полный контракт hot-path: несобранный семантический индекс → engine.retrieval.retrieve
    отдаёт лексический пол (не падает, не висит), НЕ вызывая build_index."""
    import tier_full
    from engine import retrieval, resolve_engine
    from engine.semantic import SemanticEngine

    adv = _advisor_with_corpus_no_index(tmp_path)
    monkeypatch.setattr(tier_full, "build_index", lambda a: (_ for _ in ()).throw(
        AssertionError("build_index не должен зваться в hot-path")))
    monkeypatch.setattr(tier_full, "embed_batch", lambda _t: (_ for _ in ()).throw(
        AssertionError("hot-path не должен эмбедить несобранный индекс")))
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: True))
    monkeypatch.setattr(resolve_engine, "__wrapped__", None, raising=False)

    out = retrieval.retrieve("деньги", adv, top_k=3, prefer="semantic")
    assert isinstance(out, list) and out, "должен деградировать на лексику и вернуть пассажи"
    assert any("деньги" in p["text"] for p in out)
