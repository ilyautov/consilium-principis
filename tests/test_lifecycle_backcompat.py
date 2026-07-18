"""Аддитивность жизненного цикла (§3) — старое НЕ ломаем.

Card надстраивается над картой/протоколом/журналом; проверяем что:
  • старый journal без якоря <!-- card: … --> по-прежнему отдаёт predicted через _FORECAST_RE;
  • новый якорь поднимает card_id по UUID (card_id_from_block);
  • build_record без card_id == прежний skeleton (моат-инвариант тиров цел);
  • build_record с card_id аддитивно несёт его;
  • pending_from_cards сканирует decisions/*.card.json и не трогает markdown-путь.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import outcome_loop as ol  # noqa: E402
from decision_record import build_record  # noqa: E402


_OLD_BLOCK = ("Шипнуть\n- Прогноз: 📐 P(лучший) 0.83 (карта: decisions/x.json)\n"
              "- **ИСХОД: ⏳ pending**\n")

_NEW_BLOCK = ("Шипнуть\n- Прогноз: 📐 метрика 105 ед (карта: decisions/x.json) "
              "<!-- card: dc_abc123 -->\n- **ИСХОД: ⏳ pending**\n")


# ── _FORECAST_RE остаётся fallback для старых журналов ───────────────────────

def test_old_journal_predicted_still_extracted():
    assert ol.predicted_from_block(_OLD_BLOCK).startswith("P(лучший) 0.83")


def test_new_journal_predicted_still_extracted_with_anchor():
    # даже с якорем строка прогноза читается регексом (якорь — часть хвоста, безвреден)
    assert "метрика 105" in ol.predicted_from_block(_NEW_BLOCK)


# ── новый якорь: подъём card_id по UUID ──────────────────────────────────────

def test_card_id_from_block_reads_anchor():
    assert ol.card_id_from_block(_NEW_BLOCK) == "dc_abc123"


def test_card_id_from_block_absent_is_none():
    assert ol.card_id_from_block(_OLD_BLOCK) is None


def test_card_id_from_block_non_str_is_none():
    assert ol.card_id_from_block(None) is None


# ── build_record: аддитивный card_id, моат тиров не тронут ───────────────────

def _session():
    return {"question": "q", "synthesis": "s",
            "advisors": [{"name": "М", "opinions": [{"marker": "yellow", "argument": "a"}]}]}


def test_build_record_without_card_id_is_prior_skeleton():
    rec = build_record(_session())
    assert "card_id" not in rec        # без card_id форма байт-в-байт прежняя


def test_build_record_with_card_id_carries_it():
    rec = build_record(_session(), card_id="dc_abc123")
    assert rec["card_id"] == "dc_abc123"


def test_build_record_card_id_does_not_touch_tiers():
    # моат: тир копируется as-is (yellow→🟡), card_id ничего не поднимает
    rec = build_record(_session(), card_id="dc_x")
    tiers = [a["tier"] for p in rec["positions"] for a in p["assumptions"]]
    assert tiers == ["🟡"]


# ── pending_from_cards: сканирует decisions/*.card.json ──────────────────────

def _write_card(root, cid, outcome=None):
    d = os.path.join(root, "decisions")
    os.makedirs(d, exist_ok=True)
    card = {"schema_version": "1.0.0", "id": cid, "kind": "decision_card",
            "created": "2026-07-18", "question": "Q-" + cid, "chosen_option": "x",
            "prediction": {"id": "p", "kind": "event", "statement": "s",
                           "probability": 0.6, "horizon_days": 30},
            "outcome": outcome}
    with open(os.path.join(d, "2026-07-18-%s.card.json" % cid), "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False)


def test_pending_from_cards_lists_open_cards(tmp_path):
    _write_card(str(tmp_path), "dc_open1")
    _write_card(str(tmp_path), "dc_closed1",
                outcome={"resolved_on": "2026-08-01", "occurred": True})
    pend = ol.pending_from_cards(str(tmp_path))
    titles = {p["title"] for p in pend}
    assert "Q-dc_open1" in titles and "Q-dc_closed1" not in titles
    assert pend[0]["card_id"] == "dc_open1"


def test_pending_from_cards_missing_dir_is_quiet(tmp_path):
    assert ol.pending_from_cards(str(tmp_path)) == []


def test_pending_from_cards_bad_file_skipped(tmp_path):
    d = os.path.join(str(tmp_path), "decisions")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "junk.card.json"), "w", encoding="utf-8") as f:
        f.write("{ не json")
    assert ol.pending_from_cards(str(tmp_path)) == []


# ── старый decisions/*.json (decision_map артефакт) грузится без Card ─────────

def test_old_decision_map_artifact_still_loads(tmp_path):
    d = os.path.join(str(tmp_path), "decisions")
    os.makedirs(d, exist_ok=True)
    art = {"kind": "decision_map", "saved": "2026-07-01", "map": {"question": "q"},
           "calculation": {"seed": 1, "n": 10, "predicted": "…", "result": {}}}
    p = os.path.join(d, "2026-07-01-old.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(art, f, ensure_ascii=False)
    # pending_from_cards игнорит не-.card.json артефакты (только карты, не card)
    assert ol.pending_from_cards(str(tmp_path)) == []
    # и сам старый артефакт по-прежнему читаем как раньше
    assert json.load(open(p, encoding="utf-8"))["kind"] == "decision_map"
