"""Зеркало дрейфа — заявленное vs выбираемое (анти-MiroFish: не предсказывает, отражает).

Из спора про вектор: движок НЕ знает вектор как цель (знать→оптимизировать = захват). Он
отражает РАЗРЫВ между тем, что юзер говорит, что хочет, и тем, что реально (и одобренно)
выбирает — плюс ДРЕЙФ заявленного вектора во времени (смена = сигнал, не ошибка). Возвращает
агентность: юзер сам смотрит. Ядро чистое (структура на вход) → детерминированный тест.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from mirror import stated_drift, revealed_theme, mirror_report


def test_stated_drift_detects_change():
    d = stated_drift([{"when": "2026-01", "vector": "автономия"},
                      {"when": "2026-06", "vector": "принадлежность"}])
    assert d["changed"] is True
    assert d["current"] == "принадлежность"
    assert d["transitions"] == [("автономия", "принадлежность")]


def test_stated_drift_stable_vector():
    d = stated_drift([{"when": "a", "vector": "рост"}, {"when": "b", "vector": "рост"}])
    assert d["changed"] is False
    assert d["transitions"] == []


def test_revealed_theme_dominant_among_endorsed():
    decisions = [
        {"theme": "люди", "endorsed": True},
        {"theme": "люди", "endorsed": True},
        {"theme": "деньги", "endorsed": True},
    ]
    r = revealed_theme(decisions)
    assert r["theme"] == "люди" and r["count"] == 2


def test_revealed_theme_ignores_unendorsed():
    # 'спор' выбирается часто, но НЕ одобряется задним числом → не должен доминировать
    decisions = [
        {"theme": "спор", "endorsed": False},
        {"theme": "спор", "endorsed": False},
        {"theme": "спор", "endorsed": False},
        {"theme": "люди", "endorsed": True},
    ]
    assert revealed_theme(decisions)["theme"] == "люди"


def test_mirror_reports_gap_when_stated_differs_from_revealed():
    stated = [{"when": "2026-06", "vector": "хочу роста бизнеса"}]
    decisions = [{"theme": "люди", "endorsed": True}, {"theme": "люди", "endorsed": True}]
    rep = mirror_report(stated, decisions)
    assert rep["sufficient"] is True
    assert rep["aligned"] is False
    assert "РАЗРЫВ" in rep["note"]
    assert rep["revealed_dominant"] == "люди"


def test_mirror_reports_alignment_when_match():
    stated = [{"when": "x", "vector": "автономия важнее всего"}]
    decisions = [{"theme": "автономия", "endorsed": True}]
    rep = mirror_report(stated, decisions)
    assert rep["aligned"] is True


def test_mirror_insufficient_without_data():
    rep = mirror_report([], [])
    assert rep["sufficient"] is False
