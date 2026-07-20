"""C1 (Правило A): гард обрезки, рвущей отрицание. Обрезка, отсекающая ведущее
отрицание из исходного предложения, переворачивает смысл — такой матч НЕ должен
давать 🔵. Честная цитата с сохранённым отрицанием остаётся 🔵.
См. docs/superpowers/plans/2026-07-18-audit-remediation.md, PHASE 2 / Task 2.2."""
import json
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


def _mk_advisor(tmp_path, text, tier="P1"):
    d = tmp_path / "adv"
    d.mkdir(exist_ok=True)
    with open(d / "corpus.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"source": "t", "tier": tier, "text": text},
                            ensure_ascii=False) + "\n")
    return str(d)

def test_contraction_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "You can't win by cheating. Play straight and win.")
    assert fidelity.marker_status("win by cheating", adv)["status"] == "🟡"

def test_distant_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "He did not in any real sense believe in omens or dreams.")
    assert fidelity.marker_status("believe in omens", adv)["status"] == "🟡"

def test_without_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "Without cruelty when the state is new it may stand.")
    assert fidelity.marker_status("cruelty when the state", adv)["status"] == "🟡"

def test_negation_in_other_sentence_still_blue(tmp_path):
    # «not» в СОСЕДНЕМ предложении не должно топить честную цитату (recall-контроль)
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "It is not right. Do the right thing wholly.")
    assert fidelity.marker_status("do the right thing", adv)["status"] == "🔵"

def test_clean_quote_unaffected(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "The impediment to action advances action.")
    assert fidelity.marker_status("the impediment to action", adv)["status"] == "🔵"


# Финальное ревью 2026-07-20 (Important): сплиттер НЕ режет по «:» и кавычкам — иначе
# отрицание до двоеточия/кавычек отрывается от цитаты и C2-гард пропускает обрезку.

def test_negation_before_colon_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "He did not recommend: win by cheating when cornered, ever.")
    assert fidelity.marker_status("win by cheating", adv)["status"] == "🟡"

def test_negation_before_quotes_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, 'He never said "believe in omens lightly".')
    assert fidelity.marker_status("believe in omens lightly", adv)["status"] == "🟡"

def test_clean_quote_after_colon_still_blue(tmp_path):
    # позитивный контроль: чистая цитата после двоеточия без отрицания остаётся 🔵
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "He said: do the right thing wholly.")
    assert fidelity.marker_status("do the right thing", adv)["status"] == "🔵"
