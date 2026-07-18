"""C1 (Правило A): гард обрезки, рвущей отрицание. Обрезка, отсекающая ведущее
отрицание из исходного предложения, переворачивает смысл — такой матч НЕ должен
давать 🔵. Честная цитата с сохранённым отрицанием остаётся 🔵.
См. docs/superpowers/plans/2026-07-18-audit-remediation.md, PHASE 2 / Task 2.2."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_negation_crop_not_blue(tmp_path):
    from engine.fidelity import best_match
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        '{"text":"it is not only to do but to be that matters","tier":"P1"}\n',
        encoding="utf-8",
    )
    assert best_match("only to do but to be", str(adv)) is None            # обрезка срезала «not» → не 🔵
    assert best_match("not only to do but to be", str(adv)) is not None    # честная цитата с контекстом → 🔵
