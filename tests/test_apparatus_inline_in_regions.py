"""Инлайн-аппарат в regions-пути (НЕ только в apparatus.mode=tier).

Дефект, вскрытый догфудом 2026-07-14: 🔵-гейт опирается на тир, а инлайн-детект аппарата
(скобки/сноски) жил ТОЛЬКО в ветке tier_records(inline="bracket"), куда попадают источники с
apparatus.mode=="tier". Реальные советники (machiavelli, marcus-aurelius) сидят на `regions` →
clean.tag_regions → микро-защиты не было ВООБЩЕ. Итог: сноска переводчика с цитатой Тацита на
латыни внутри P1-региона получала tier=P1 и была 🔵-eligible — ров заверял чужие слова как
дословную речь советника. Пересборка это НЕ чинила: apparatus.py на этом пути не исполнялся.

Инвариант: fail-closed не бывает opt-in. Инлайн-аппарат понижается до S1 на ЛЮБОМ пути.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import apparatus  # noqa: E402


def _tiers(recs):
    return [(r["text"], r["tier"]) for r in recs]


def test_footnote_definition_inside_body_is_demoted():
    """Сноска-определение '[3] Proclivius est...' — слова переводчика/Тацита, не советника."""
    recs = [{"loc": 1, "text": "A prince must be feared.", "tier": "P1"},
            {"loc": 2, "text": "[3] Proclivius est injuriae. _Tacit. Hist._ iv. 2.", "tier": "P1"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert _tiers(out) == [("A prince must be feared.", "P1"),
                           ("[3] Proclivius est injuriae. _Tacit. Hist._ iv. 2.", "S1")]


def test_bracketed_comment_is_demoted_but_author_text_survives():
    recs = [{"loc": 1, "text": "Fortune is a woman [so says the editor] and must be struck.",
             "tier": "P1"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert ("[so says the editor]", "S1") in _tiers(out)
    assert ("Fortune is a woman", "P1") in _tiers(out)
    assert ("and must be struck.", "P1") in _tiers(out)


def test_multiline_bracket_depth_flows_across_records():
    """Многострочный коммент остаётся 🟢 на ВСЕХ строках — глубина течёт сквозь записи."""
    recs = [{"loc": 1, "text": "The prince said [a long editorial note", "tier": "P1"},
            {"loc": 2, "text": "that continues here", "tier": "P1"},
            {"loc": 3, "text": "and ends here] then acted.", "tier": "P1"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert ("The prince said", "P1") in _tiers(out)
    for text, tier in _tiers(out):
        if "continues here" in text or "ends here" in text.split("]")[0]:
            assert tier == "S1", f"тело коммента утекло в 🔵: {text!r}"
    assert ("then acted.", "P1") in _tiers(out)


def test_non_blue_records_pass_through_untouched_and_do_not_leak_depth():
    """B/S1-записи не 🔵-eligible: их не режем, и их скобки не травят глубину тела."""
    recs = [{"loc": 1, "text": "Introduction by the translator [unclosed bracket", "tier": "B"},
            {"loc": 2, "text": "The prince must be feared.", "tier": "P1"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert _tiers(out) == [("Introduction by the translator [unclosed bracket", "B"),
                           ("The prince must be feared.", "P1")]


def test_p2_is_also_blue_eligible_and_split():
    recs = [{"loc": 1, "text": "Author text [note] more.", "tier": "P2"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert ("[note]", "S1") in _tiers(out)
    assert ("Author text", "P2") in _tiers(out)


def test_extra_fields_are_preserved():
    recs = [{"loc": 7, "text": "Body [ed] tail.", "tier": "P1", "source": "x.txt"}]
    out = apparatus.demote_inline_apparatus(recs)
    assert all(r["source"] == "x.txt" and r["loc"] == 7 for r in out)


# --- интеграция: regions-путь (clean.tag_regions) обязан звать инлайн-гейт ---

def _advisor(tmp_path, manifest):
    import json
    adv = tmp_path / "adv"
    (adv / "sources").mkdir(parents=True)
    (adv / "sources" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return str(adv)


def test_tag_regions_demotes_inline_apparatus(tmp_path):
    """Регресс на живой дефект: regions-путь БЕЗ apparatus.mode=tier тоже обязан ловить сноску."""
    from corpusbuild import clean
    adv = _advisor(tmp_path, {"src.txt": {"tier": "P1", "license": "public-domain"}})
    records = [(1, "A prince must be feared."),
               (2, "[3] Proclivius est injuriae. _Tacit. Hist._ iv. 2.")]
    out = clean.tag_regions(records, "src.txt", adv)
    by_text = {r["text"]: r["tier"] for r in out}
    assert by_text["A prince must be feared."] == "P1"
    assert by_text["[3] Proclivius est injuriae. _Tacit. Hist._ iv. 2."] == "S1", \
        "сноска переводчика осталась 🔵-eligible в regions-пути"
