"""Tier-aware гейт 🔵 в Engine.fidelity_check (prereq B).

Ядро рва на продуктовой поверхности: дословный матч сам по себе НЕ даёт 🔵 —
решает ТИР чанка, где найдена цитата. Комментарий (S1, напр. Тарасов) дословен,
но это не слова автора → 🟢 с атрибуцией комментатору, никогда не голосом советника.
"""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from engine.lexical import LexicalEngine  # конкретный движок; fidelity_check живёт на базе


def _mk(tmp, chunks):
    """chunks = list of (source, tier, text). tier=None → поле tier отсутствует."""
    adv = os.path.join(tmp, "adv")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for src, tier, text in chunks:
            rec = {"source": src, "text": text}
            if tier is not None:
                rec["tier"] = tier
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return adv


def _eng():
    return LexicalEngine()


def test_p1_match_is_blue():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [("prince.txt", "P1", "It is safer to be feared than loved.")])
        r = _eng().fidelity_check("safer to be feared than loved", adv)
        assert r.status == "🔵"
        assert r.verbatim is True
        assert r.source == "prince.txt"


def test_s1_match_is_green_not_blue():
    # Дословный матч в комментарии Тарасова (S1) → 🟢, источник = Тарасов, НЕ 🔵.
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [("tarasov.txt", "S1", "Власть держится на страхе, а не на любви.")])
        r = _eng().fidelity_check("власть держится на страхе", adv)
        assert r.status == "🟢"
        assert r.verbatim is True
        assert r.source == "tarasov.txt"


def test_both_tiers_authoritative_wins():
    # Цитата есть и в S1, и в P1 → 🔵 с источником P1 (самый авторитетный тир побеждает).
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [
            ("tarasov.txt", "S1", "Он писал: лучше быть страшным, чем любимым."),
            ("prince.txt", "P1", "Лучше быть страшным, чем любимым."),
        ])
        r = _eng().fidelity_check("лучше быть страшным, чем любимым", adv)
        assert r.status == "🔵"
        assert r.source == "prince.txt"


def test_no_match_is_yellow():
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [("prince.txt", "P1", "It is safer to be feared than loved.")])
        r = _eng().fidelity_check("you have power over your mind", adv)
        assert r.status == "🟡"
        assert r.verbatim is False
        assert r.source == ""


def test_untiered_chunk_fails_closed_to_yellow():
    # Нет поля tier → провенанс неизвестен → fail-closed 🟡 (не сертифицируем 🔵 вслепую).
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [("legacy.txt", None, "Some sentence with no tier field at all.")])
        r = _eng().fidelity_check("sentence with no tier", adv)
        assert r.status == "🟡"
        assert r.verbatim is False


def test_b_tier_frontmatter_is_yellow():
    # Front-matter/биография переводчика (B) дословен, но не слова автора → 🟡, не 🔵.
    with tempfile.TemporaryDirectory() as t:
        adv = _mk(t, [("prince.txt", "B", "Translated by W. K. Marriott in nineteen oh eight.")])
        r = _eng().fidelity_check("translated by w k marriott", adv)
        assert r.status == "🟡"
