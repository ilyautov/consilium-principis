"""Шасси-онбординг: создать Принцепс из ответов юзера + подсказать «что собрать дальше».

Пробел #3 (шасси): Принцепс писался руками. Юзер, находясь в Claude, отвечает на вопросы —
скилл скаффолдит principis.md (round-trip через load_principis). next_step ведёт за руку:
один приоритетный шаг по состоянию доски (preflight). Вектор НЕ фиксируем — пробел держим
живым (совет допрашивает), это из спора про вектор-как-зеркало.
"""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from scaffold import scaffold_principis, next_step
from principis import load_principis


def test_scaffold_roundtrips_through_loader():
    md = scaffold_principis({"who": "Илья, фаундер", "interface_mode": "rigor",
                             "temperament": "рублю с плеча", "not_known": "финансы детально"})
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "principis.md")
        open(p, "w", encoding="utf-8").write(md)
        loaded = load_principis(p)
    assert loaded["ok"] is True
    assert loaded["interface_mode"] == "rigor"
    assert loaded["owner"] == "principis"
    assert any("Кто ты" in s for s in loaded["sections"])


def test_vector_left_open_when_not_given():
    md = scaffold_principis({"who": "X", "interface_mode": "support"})
    assert "ПРОБЕЛ" in md                       # вектор не фиксируем — держим живым
    assert "Вектор" in md


def test_invalid_mode_falls_back_to_rigor():
    md = scaffold_principis({"who": "X", "interface_mode": "чтотопопало"})
    assert "interface_mode: rigor" in md        # fail-safe к rigor


def test_next_step_principis_first_when_missing():
    pf = {"principis": {"ok": False, "interface_mode": "rigor"}, "advisors": [], "lenses": []}
    ns = next_step(pf)
    assert ns["action"] == "principis"


def test_next_step_add_advisor_when_no_grounded():
    pf = {"principis": {"ok": True, "interface_mode": "rigor"},
          "advisors": [{"name": "x", "has_corpus": False, "blue_eligible": False, "has_kernels": False}],
          "lenses": [{"name": "CFO"}]}
    assert next_step(pf)["action"] == "add-advisor"


def test_next_step_build_kernels_when_corpus_without_kernels():
    pf = {"principis": {"ok": True, "interface_mode": "rigor"},
          "advisors": [{"name": "x", "has_corpus": True, "blue_eligible": True, "has_kernels": False}],
          "lenses": [{"name": "CFO"}]}
    assert next_step(pf)["action"] == "build-kernels"


def test_next_step_ready_when_all_set():
    pf = {"principis": {"ok": True, "interface_mode": "rigor"},
          "advisors": [{"name": "x", "has_corpus": True, "blue_eligible": True, "has_kernels": True}],
          "lenses": [{"name": "CFO"}]}
    assert next_step(pf)["action"] == "ready"
