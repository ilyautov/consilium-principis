"""Замер тир-осведомлённого ретрива (слой 3) — офлайн-тесты чистых функций.

Зачем инструмент. Дип-ресёрч 2026-07-15 оставил угол «метрики и фальсификация» ПУСТЫМ, а два
его урока целятся ровно в нас:
  • ClaimTrust: метрика без разрешающей способности (substring accuracy 0.015 = 3/200 в ОБОИХ
    режимах) не мешает заключению рапортовать «measurable gains». Метрика обязана разрешать.
  • Airbnb (KDD'20): distribution-matching дал офлайн NDCG +0.03% (нейтрально!) и статзначимое
    падение ОНЛАЙН. Офлайн-нейтральность НЕ доказывает безвредность.

Анти-подгонка. Запросы НЕ придумываются под правку: берём существующий golden (сделан 23–25
июня, задолго до задачи), где auto.jsonl — ПАРНЫЙ дизайн: у literal- и abstract-вопроса ОДИН
якорь и target_tier=P1, то есть стиль запроса меняется при фиксированном искомом пассаже.
Self-bias снят по построению gen_golden: вопросы генерил LLM, ретрив — bge-m3, разные системы.

Две метрики нужны ВМЕСТЕ, и в этом вся соль:
  • blue_share  — сколько 🔵-eligible в пуле (композиция);
  • anchor_rank — доехал ли ИМЕННО ТОТ P1, что отвечает на вопрос (пригодность).
Рост blue_share при падении anchor_rank = квота накупила мусорных P1-слотов. Это ровно
принцип Joachims (KDD'24): «slot constraints act on the relevant items, not all items» —
слот с нерелевантным кандидатом стоит НОЛЬ. Одна blue_share этого не видит и соврёт.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "experiments"))

import tier_pool_probe as P  # noqa: E402


def _h(text, tier):
    return {"text": text, "tier": tier, "score": 0.5, "source": "x.txt"}


# --- anchor_rank: доехал ли нужный пассаж ---

def test_anchor_rank_finds_normalized_substring():
    hits = [_h("Тарасов толкует", "S1"),
            _h("it is much safer to be feared than loved, if one", "P1")]
    assert P.anchor_rank(hits, "safer to be feared than loved") == 2


def test_anchor_rank_none_when_absent():
    assert P.anchor_rank([_h("nothing relevant", "P1")], "safer to be feared") is None


def test_anchor_rank_ignores_case_and_punctuation():
    hits = [_h("SAFER, to be FEARED  than loved!", "P1")]
    assert P.anchor_rank(hits, "safer to be feared than loved") == 1


# --- blue_share: композиция пула ---

def test_blue_share_counts_only_primary():
    hits = [_h("a", "P1"), _h("b", "S1"), _h("c", "P2"), _h("d", "B")]
    assert P.blue_share(hits) == 0.5


def test_unknown_tier_is_not_blue():
    """tier=None = «неизвестен» → fail-closed, НЕ первоисточник (иначе метрика льстит)."""
    assert P.blue_share([_h("a", None), _h("b", "P1")]) == 0.5
    assert P.has_blue([_h("a", None)]) is False


def test_blue_share_of_empty_pool_is_zero():
    assert P.blue_share([]) == 0.0
    assert P.has_blue([]) is False


# --- парность golden ---

def test_pairs_group_literal_and_abstract_by_anchor():
    rows = [{"q": "L1", "anchor": "A", "difficulty": "literal", "target_tier": "P1"},
            {"q": "A1", "anchor": "A", "difficulty": "abstract", "target_tier": "P1"},
            {"q": "L2", "anchor": "B", "difficulty": "literal", "target_tier": "P1"},
            {"q": "A2", "anchor": "B", "difficulty": "abstract", "target_tier": "P1"}]
    pairs = P.pair_by_anchor(rows)
    assert len(pairs) == 2
    assert pairs[0]["literal"] == "L1" and pairs[0]["abstract"] == "A1"


def test_incomplete_pairs_are_dropped_not_guessed():
    """Непарный якорь ломает парную статистику → честно выкинуть, а не достроить."""
    rows = [{"q": "L1", "anchor": "A", "difficulty": "literal"},
            {"q": "L2", "anchor": "B", "difficulty": "literal"},
            {"q": "A2", "anchor": "B", "difficulty": "abstract"}]
    assert [p["anchor"] for p in P.pair_by_anchor(rows)] == ["B"]


# --- сводка ---

def test_summarize_reports_recall_mrr_and_share():
    rows = [{"anchor_rank": 1, "blue_share": 0.5, "has_blue": True},
            {"anchor_rank": 4, "blue_share": 0.25, "has_blue": True},
            {"anchor_rank": None, "blue_share": 0.0, "has_blue": False}]
    s = P.summarize(rows, k=8)
    assert s["n"] == 3
    assert s["anchor_recall"] == 2 / 3
    assert abs(s["anchor_mrr"] - (1 / 1 + 1 / 4 + 0) / 3) < 1e-9
    assert abs(s["blue_share_mean"] - 0.25) < 1e-9
    assert abs(s["citation_ability"] - 2 / 3) < 1e-9


def test_summarize_flags_zero_resolution():
    """Урок ClaimTrust: метрика, где все значения одинаковы, ничего не различает → сказать вслух."""
    rows = [{"anchor_rank": None, "blue_share": 0.0, "has_blue": False} for _ in range(20)]
    s = P.summarize(rows, k=8)
    assert s["degenerate"] is True, "метрика без разрешения обязана честно объявить об этом"


def test_summarize_not_degenerate_when_values_vary():
    rows = [{"anchor_rank": 1, "blue_share": 0.5, "has_blue": True},
            {"anchor_rank": None, "blue_share": 0.1, "has_blue": True}]
    assert P.summarize(rows, k=8)["degenerate"] is False


# --- ДЕТЕКТОР ЛОВУШКИ (главное) ---

def test_compare_flags_junk_slots_when_share_up_but_anchor_down():
    """Joachims: слот, занятый нерелевантным кандидатом, стоит НОЛЬ.
    Больше 🔵 в пуле при худшем ранге нужного пассажа = купили мусор."""
    base = {"anchor_recall": 0.8, "anchor_mrr": 0.70, "blue_share_mean": 0.30, "n": 15}
    treat = {"anchor_recall": 0.5, "anchor_mrr": 0.40, "blue_share_mean": 0.60, "n": 15}
    v = P.compare(base, treat)
    assert v["junk_slots_suspected"] is True
    assert "мусор" in v["verdict"].lower() or "junk" in v["verdict"].lower()


def test_compare_accepts_real_lift_when_both_improve():
    base = {"anchor_recall": 0.5, "anchor_mrr": 0.40, "blue_share_mean": 0.30, "n": 15}
    treat = {"anchor_recall": 0.7, "anchor_mrr": 0.55, "blue_share_mean": 0.45, "n": 15}
    v = P.compare(base, treat)
    assert v["junk_slots_suspected"] is False
    assert v["relevance_tax"] <= 0, "налога нет — якорь не просел"


def test_compare_reports_relevance_tax_even_when_share_wins():
    """Airbnb: одноосевое ограничение «almost always sacrifices relevance» — налог называть вслух."""
    base = {"anchor_recall": 0.80, "anchor_mrr": 0.700, "blue_share_mean": 0.30, "n": 15}
    treat = {"anchor_recall": 0.78, "anchor_mrr": 0.660, "blue_share_mean": 0.50, "n": 15}
    v = P.compare(base, treat)
    assert v["relevance_tax"] > 0, "просадка MRR якоря — это налог, его нельзя молча съесть"


def test_compare_refuses_verdict_on_tiny_sample():
    """Офлайн-нейтральность ничего не доказывает (Airbnb) → на крошечном n вердикта НЕТ."""
    base = {"anchor_recall": 0.5, "anchor_mrr": 0.4, "blue_share_mean": 0.3, "n": 2}
    treat = {"anchor_recall": 1.0, "anchor_mrr": 0.9, "blue_share_mean": 0.6, "n": 2}
    assert P.compare(base, treat)["underpowered"] is True
