"""M3/PART2 — инертность семантического гейта на SIMPLE (лексическом) тире.

Контекст: полоса судьи [band_lo, band_hi] и порог abstain калиброваны под
СЕМАНТИЧЕСКИЙ косинус (см. docs/dev/calibration-provenance.md). Без живого
ollama резолвится lexical-бэкенд И серверный судья недоступен (M4: вне
semantic-режима гейт судит только при живом судье) → relevance_gate.gate_quote
ИНЕРТЕН (keep=True всегда).

Опасность, которую пиним: инертный гейт НЕ должен молча пропускать
экстраполяцию как grounded. Честность на SIMPLE-тире держит НЕ полоса, а
backend-независимый verbatim-чек engine.fidelity (per-chunk, tier-aware,
fail-closed). Тесты проверяют РОВНО этот инвариант:

  1. is_semantic() под offline-env = False → gate_quote инертен (keep=True);
  2. НЕ-корпусная цитата → маркер 🟡 (не 🔵), даже когда гейт инертен;
  3. настоящая P1-цитата корпуса → 🔵;  S1 (комментарий) → 🟢;
  4. инертный gate_quote(keep=True) НЕ повышает 🟡→🔵 — грунтованность даёт
     verbatim-тир, а не гейт.

Герметично: только tmp-корпус + engine.fidelity/relevance_gate напрямую,
без сети и без движка. Запуск (как в задаче):
  HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 \
    python3 -m pytest tests/test_gate_simple_tier_inert.py -q
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/ — engine это пакет

from engine.fidelity import marker_status
import relevance_gate


# Дословно из P1-чанка = слова автора; из S1 = дословно, но комментарий.
P1_QUOTE = "a prince must learn how not to be good"
S1_QUOTE = "the translator notes this passage echoes an earlier maxim"
# Экстраполяция: осмысленная фраза, которой НЕТ ни в одном чанке корпуса.
OFF_CORPUS_QUOTE = "always trust your feelings above all evidence"


def _mk_corpus(tmp_path):
    """tmp-советник с P1- и S1-чанком (tier проставлен)."""
    adv = tmp_path / "adv"
    adv.mkdir()
    rows = [
        {"source": "prince-ch15.txt", "tier": "P1",
         "text": "Hence it is necessary that " + P1_QUOTE + ", and to use this knowledge."},
        {"source": "giles-notes.txt", "tier": "S1",
         "text": "Editorial apparatus: " + S1_QUOTE + " found in book two."},
    ]
    with open(adv / "corpus.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(adv)


# ───────────────────────── тир действительно SIMPLE ─────────────────────────

def test_offline_env_resolves_lexical_not_semantic(tmp_path):
    """Без ollama резолвится lexical → полоса неприменима, гейт инертен."""
    adv = _mk_corpus(tmp_path)
    assert relevance_gate.is_semantic(adv) is False


def test_gate_quote_inert_on_simple_tier(tmp_path):
    """Не-semantic → gate_quote keep=True всегда (нет косинуса для полосы).
    judge_fn, который бы упал — доказывает, что судья ДАЖE не вызывается."""
    adv = _mk_corpus(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("судья не должен вызываться на SIMPLE-тире")

    # score=None (косинуса нет на SIMPLE) и любое число — оба keep=True инертно.
    assert relevance_gate.gate_quote("q", P1_QUOTE, None, adv, judge_fn=_boom) is True
    assert relevance_gate.gate_quote("q", OFF_CORPUS_QUOTE, 0.44, adv, judge_fn=_boom) is True


# ───────── честность держит verbatim-тир, НЕ полоса (главный инвариант) ──────

def test_off_corpus_quote_is_not_blue_even_on_simple_tier(tmp_path):
    """Экстраполяция (нет в корпусе) → 🟡 fail-closed, НЕ 🔵 — хотя гейт инертен."""
    adv = _mk_corpus(tmp_path)
    m = marker_status(OFF_CORPUS_QUOTE, adv)
    assert m["status"] == "🟡"
    assert m["verbatim"] is False


def test_real_p1_corpus_quote_is_blue(tmp_path):
    """Дословная P1-цитата → 🔵 (слова автора) даже без семантического бэкенда."""
    adv = _mk_corpus(tmp_path)
    m = marker_status(P1_QUOTE, adv)
    assert m["status"] == "🔵"
    assert m["verbatim"] is True


def test_s1_commentary_quote_is_green_not_blue(tmp_path):
    """Дословно, но из комментария (S1) → 🟢 с атрибуцией, НЕ 🔵 голосом автора."""
    adv = _mk_corpus(tmp_path)
    m = marker_status(S1_QUOTE, adv)
    assert m["status"] == "🟢"
    assert m["verbatim"] is True


def test_inert_gate_does_not_upgrade_extrapolation_to_grounded(tmp_path):
    """Связка: gate_quote инертно возвращает keep=True на не-корпусную цитату,
    но маркер той же цитаты остаётся 🟡 — инертный гейт НЕ конвертирует
    экстраполяцию в grounded (грунтованность идёт от verbatim, не от гейта)."""
    adv = _mk_corpus(tmp_path)
    kept = relevance_gate.gate_quote("q", OFF_CORPUS_QUOTE, 0.44, adv,
                                     judge_fn=lambda *a, **k: 0)
    assert kept is True                                   # гейт пропускает (инертен)
    assert marker_status(OFF_CORPUS_QUOTE, adv)["status"] == "🟡"   # но 🔵 НЕ выдан
