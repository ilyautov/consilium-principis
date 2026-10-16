"""Вердикт-механика совета (council_verdict) — валидация, счёт, поправки-потолки, подача.

Каждая поправка покрыта срабатыванием и несрабатыванием; рендер — наличием ключевых кусков;
хук session_render — тем, что отсутствие вердикта не меняет вывод ни на байт.
"""
import copy
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import council_verdict as cv
import session_render as SR
from council_verdict import compute_verdict, render_verdict_md, validate_scorecard


def _seat(name, weight, a, b, c=None, **kw):
    scores = {"A": a, "B": b}
    if c is not None:
        scores["C"] = c
    s = {"name": name, "weight": weight, "weight_reason": "линза по делу",
         "scores": scores, "confidence": 4, "ruin_risk": "none", "door": "two-way",
         "change_my_mind": "если выручка < 100к за квартал",
         "question_for_user": "готов ли ты потерять полгода?"}
    s.update(kw)
    return s


def _card(**kw):
    """Базовый валидный scorecard: A — статус-кво, B — действие; B выигрывает ~6.4."""
    c = {
        "options": [{"id": "A", "label": "Оставить как есть", "status_quo": True},
                    {"id": "B", "label": "Запустить продукт"}],
        "seats": [_seat("Марк Аврелий", 3, 4, 6),
                  _seat("Макиавелли", 2, 3, 7),
                  _seat("Сунь-цзы", 1, 5, 6)],
        "kill_criteria": ["меньше 10 платящих к 2026-12-01"],
        "steps": [{"when": "день 1", "action": "написать 20 клиентам"}],
    }
    c.update(kw)
    return c


# ── валидация ───────────────────────────────────────────────────────────────

def test_valid_card_has_no_errors():
    assert validate_scorecard(_card()) == []


def test_not_a_dict():
    errs = validate_scorecard([1, 2])
    assert len(errs) == 1 and "JSON-объектом" in errs[0]


def test_errors_accumulate_not_first_only():
    c = _card()
    c["seats"][0]["weight"] = 5
    c["seats"][0]["scores"]["B"] = 11
    c["seats"][1]["change_my_mind"] = "  "
    c["seats"][1]["question_for_user"] = ""
    c["seats"][2]["door"] = "revolving"
    errs = validate_scorecard(c)
    joined = " | ".join(errs)
    assert len(errs) >= 5
    assert "weight" in joined and "от 0 до 10" in joined
    assert "change_my_mind" in joined and "question_for_user" in joined and "door" in joined


def test_single_seat_is_consultation_not_verdict():
    c = _card(seats=[_seat("Марк Аврелий", 3, 4, 6)])
    errs = validate_scorecard(c)
    assert any(cv.SINGLE_VOICE_ERROR in e.lower() for e in errs)


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -1, 10.5, "7", None])
def test_bad_score_values(bad):
    c = _card()
    c["seats"][0]["scores"]["A"] = bad
    assert any("от 0 до 10" in e for e in validate_scorecard(c))


def test_missing_and_unknown_option_scores():
    c = _card()
    del c["seats"][0]["scores"]["B"]
    c["seats"][1]["scores"]["Z"] = 5
    errs = " | ".join(validate_scorecard(c))
    assert "не оценил вариант «B»" in errs
    assert "неизвестный вариант «Z»" in errs


@pytest.mark.parametrize("w", [0, 4, 2.0, True, "2"])
def test_weight_must_be_int_1_3(w):
    c = _card()
    c["seats"][0]["weight"] = w
    assert any("Вес линзы" in e for e in validate_scorecard(c))


def test_duplicate_seat_names():
    c = _card()
    c["seats"][2]["name"] = "Марк Аврелий"
    assert any("повторяется" in e for e in validate_scorecard(c))


def test_bad_enums_and_confidence():
    c = _card()
    c["seats"][0]["ruin_risk"] = "maybe"
    c["seats"][1]["confidence"] = 6
    c["seats"][2]["ruin_on"] = "Q"
    errs = " | ".join(validate_scorecard(c))
    assert "ruin_risk" in errs and "confidence" in errs and "ruin_on" in errs


def test_status_quo_count_must_be_one():
    c = _card()
    c["options"][1]["status_quo"] = True
    assert any("статус-кво" in e for e in validate_scorecard(c))
    c["options"][0]["status_quo"] = "true"
    c["options"][1]["status_quo"] = False
    errs = validate_scorecard(c)
    assert any("литеральным" in e for e in errs)


def test_crux_validation():
    c = _card(cruxes=[{"question": "Есть ли спрос?", "kind": "vibes",
                       "sides": [{"position": "да", "seats": ["Марк Аврелий", "Платон"]}]}])
    errs = " | ".join(validate_scorecard(c))
    assert "fact, numbers или values" in errs and "«Платон»" in errs


def test_minority_requires_right_if():
    c = _card(minority=[{"seat": "Макиавелли", "claim": "рынок занят"}])
    assert any("right_if" in e for e in validate_scorecard(c))


def test_wait_requires_valid_date():
    c = _card(wait={"trigger": "ответ инвестора", "date": "2026-13-45", "if_fails": "идём сами"})
    assert any("YYYY-MM-DD" in e for e in validate_scorecard(c))
    c["wait"]["date"] = "2026-11-01"
    assert validate_scorecard(c) == []


def test_mitigation_endorsed_must_be_bool():
    c = _card(ruin_mitigations=[{"seat": "Макиавелли", "mitigation": "x", "endorsed": "yes"}])
    assert any("endorsed" in e for e in validate_scorecard(c))


def test_compute_raises_with_all_errors():
    c = _card()
    c["seats"][0]["weight"] = 9
    c["seats"][1]["question_for_user"] = ""
    with pytest.raises(ValueError) as ei:
        compute_verdict(c)
    assert "weight" in str(ei.value) and "question_for_user" in str(ei.value)


# ── счёт ───────────────────────────────────────────────────────────────────

def test_weighted_scores_and_math_string():
    r = compute_verdict(_card())
    by = {x["id"]: x for x in r["scores"]}
    # B = (3·6 + 2·7 + 1·6) / 6 = 38/6 = 6.33 → 6.3
    assert by["B"]["score"] == 6.3
    assert by["B"]["math"] == "B (3×6 + 2×7 + 1×6) / 6 = 6.3"
    assert by["A"]["score"] == 3.8                 # (12+6+5)/6 = 3.83
    assert r["recommended"]["id"] == "B"
    assert r["weights_source"] == "relevance"


def test_bands_and_half_up_rounding():
    assert cv._round1(6.45) == 6.5
    assert cv._band(7.5) == cv.GO and cv._band(7.4) == cv.GO_WITH_CONDITIONS
    assert cv._band(6.0) == cv.GO_WITH_CONDITIONS and cv._band(5.9) == cv.RESHAPE
    assert cv._band(4.5) == cv.RESHAPE and cv._band(4.4) == cv.DONT


def test_go_band():
    c = _card(seats=[_seat("Марк Аврелий", 3, 2, 8), _seat("Макиавелли", 2, 3, 9),
                     _seat("Сунь-цзы", 1, 4, 7)])
    r = compute_verdict(c)
    assert r["label"] == cv.GO and r["label_ru"] == "ИДТИ" and r["label_en"] == "GO"
    assert r["complete"] is True and r["missing"] == []


def test_track_multiplier_clamped_and_source():
    r = compute_verdict(_card(), track_weights={"Марк Аврелий": 9.0, "макиавелли ": 0.1,
                                                "Чужой": 1.2})
    w = r["weights"]
    assert w["Марк Аврелий"]["track"] == 1.5 and w["Марк Аврелий"]["effective"] == 4.5
    assert w["Макиавелли"]["track"] == 0.5 and w["Макиавелли"]["effective"] == 1.0
    assert w["Сунь-цзы"]["track"] == 1.0
    assert r["weights_source"] == "relevance×track"
    assert r["track_unmatched"] == ["Чужой"]
    b = next(x for x in r["scores"] if x["id"] == "B")
    assert b["math"].startswith("B (4.5×6 + 1×7 + 1×6) / 6.5")


def test_track_accepts_advisor_weights_output_shape():
    aw = {"scores": {"Марк Аврелий": {"n": 4, "resolved": 4, "hits": 4, "score": 5 / 6},
                     "Макиавелли": {"n": 2, "resolved": 2, "hits": 0, "score": 0.25}},
          "weights": {"Марк Аврелий": 0.77, "Макиавелли": 0.23}}
    r = compute_verdict(_card(), track_weights=aw)
    assert r["weights"]["Марк Аврелий"]["track"] == pytest.approx(5 / 3 if 5 / 3 <= 1.5 else 1.5)
    assert r["weights"]["Макиавелли"]["track"] == 0.5
    # только нормированные доли: share·N → нейтраль 1.0 при равных долях
    r2 = compute_verdict(_card(), track_weights={"weights": {"Марк Аврелий": 0.5, "Макиавелли": 0.5}})
    assert r2["weights"]["Марк Аврелий"]["track"] == 1.0


def test_track_bad_value_fails_closed():
    with pytest.raises(ValueError):
        compute_verdict(_card(), track_weights={"Марк Аврелий": "много"})
    with pytest.raises(ValueError):
        compute_verdict(_card(), track_weights=[1, 2])


def test_spread_and_council_confidence():
    r = compute_verdict(_card())
    assert r["spread"] == 1                       # оценки B: 6, 7, 6
    assert r["council_confidence"] == 8           # avg 4 × 2
    c = _card()
    c["seats"][2]["scores"]["B"] = 1              # разброс 6 → −1
    r = compute_verdict(c)
    assert r["spread"] == 6 and r["council_confidence"] == 7


def test_status_quo_wins_means_dont():
    c = _card(seats=[_seat("Марк Аврелий", 3, 8, 3), _seat("Макиавелли", 2, 7, 5),
                     _seat("Сунь-цзы", 1, 6, 6)])
    r = compute_verdict(c)
    assert r["recommended"]["id"] == "A" and r["recommended"]["status_quo"] is True
    assert r["label"] == cv.DONT and "не делать / оставить как есть" in r["call"]
    assert "kill_criteria" not in r["missing"]   # completeness только для «идти»


def test_tie_prefers_status_quo():
    c = _card(seats=[_seat("Марк Аврелий", 1, 6, 7), _seat("Макиавелли", 1, 7, 6)])
    r = compute_verdict(c)
    assert r["tie"] is True and set(r["tied"]) == {"A", "B"}
    assert r["recommended"]["id"] == "A" and r["label"] == cv.DONT


def test_tie_without_status_quo_takes_first_option():
    c = _card(options=[{"id": "A", "label": "ничего", "status_quo": True},
                       {"id": "B", "label": "б"}, {"id": "C", "label": "в"}],
              seats=[_seat("Марк Аврелий", 1, 1, 8, 7), _seat("Макиавелли", 1, 1, 7, 8)])
    r = compute_verdict(c)
    assert r["tie"] is True and r["recommended"]["id"] == "B"


# ── поправки ───────────────────────────────────────────────────────────────

def _go_card(**kw):
    return _card(seats=[_seat("Марк Аврелий", 3, 2, 8), _seat("Макиавелли", 2, 3, 9),
                        _seat("Сунь-цзы", 1, 4, 7)], **kw)


def test_ruin_cap_without_endorsed_mitigation():
    c = _go_card()
    c["seats"][1]["ruin_risk"] = "likely"        # ruin_on по умолчанию = свой фаворит B
    r = compute_verdict(c)
    assert r["base_label"] == cv.GO and r["label"] == cv.RESHAPE
    o = r["overrides"][0]
    assert o["rule"] == "ruin_cap" and o["seats"] == ["Макиавелли"] and "Макиавелли" in o["reason"]


def test_ruin_cap_lifted_by_endorsed_mitigation_only():
    c = _go_card(ruin_mitigations=[{"seat": "Макиавелли", "mitigation": "лимит 10% капитала",
                                    "endorsed": False}])
    c["seats"][1]["ruin_risk"] = "likely"
    assert compute_verdict(c)["label"] == cv.RESHAPE           # не одобрил сам → потолок
    c["ruin_mitigations"][0]["endorsed"] = True
    r = compute_verdict(c)
    assert r["label"] == cv.GO and r["ruin_mitigated"] == ["Макиавелли"]
    assert not any(o["rule"] == "ruin_cap" for o in r["overrides"])


def test_ruin_on_other_option_does_not_cap():
    c = _go_card()
    c["seats"][1].update(ruin_risk="likely", ruin_on="A")
    assert compute_verdict(c)["label"] == cv.GO


def test_one_way_cap_and_missing_cheapest_test():
    c = _go_card()
    for s in c["seats"]:
        s["door"] = "one-way"
    c["seats"][0]["scores"]["B"] = 10
    c["seats"][2]["scores"]["B"] = 6               # B: 10, 9, 6 → разброс 4, балл 9.3
    r = compute_verdict(c)
    assert r["base_label"] == cv.GO and r["label"] == cv.GO_WITH_CONDITIONS
    assert "cheapest_test" in r["missing"] and r["complete"] is False
    assert any(o["rule"] == "one_way_cap" for o in r["overrides"])
    c["cheapest_test"] = "лендинг + 50 звонков"
    r = compute_verdict(c)
    assert "cheapest_test" not in r["missing"] and r["cheapest_test"] == "лендинг + 50 звонков"


def test_one_way_door_tie_counts_as_one_way():
    c = _card(seats=[_seat("Марк Аврелий", 1, 2, 10, door="one-way"),
                     _seat("Макиавелли", 1, 2, 6, door="two-way")])
    r = compute_verdict(c)
    assert r["door"] == "one-way" and any(o["rule"] == "one_way_cap" for o in r["overrides"])


def test_two_way_majority_no_cap():
    c = _go_card()
    c["seats"][0]["scores"]["B"] = 10
    c["seats"][2]["scores"]["B"] = 6
    r = compute_verdict(c)
    assert r["door"] == "two-way" and r["label"] == cv.GO


def test_unanimity_alarm_does_not_change_label():
    c = _go_card()
    c["seats"][0]["scores"]["B"] = 8
    c["seats"][1]["scores"]["B"] = 8
    c["seats"][2]["scores"]["B"] = 9               # все за B в пределах 1
    r = compute_verdict(c)
    assert r["unanimity_alarm"] is True and r["label"] == cv.GO
    assert "A «Оставить как есть»" in r["unanimity_instruction"]
    assert "малое N" not in r["unanimity_instruction"]
    assert any(o["rule"] == "unanimity" and o["from"] == o["to"] for o in r["overrides"])


def test_unanimity_two_seats_notes_small_n():
    c = _card(seats=[_seat("Марк Аврелий", 1, 2, 8), _seat("Макиавелли", 1, 3, 8)])
    r = compute_verdict(c)
    assert r["unanimity_alarm"] is True and "малое N" in r["unanimity_instruction"]


def test_no_unanimity_when_split():
    r = compute_verdict(_go_card())                # B: 8, 9, 7 → разброс 2
    assert r["unanimity_alarm"] is False and r["unanimity_instruction"] is None


def test_wait_converts_go():
    w = {"trigger": "ответ банка по кредиту", "date": "2026-11-01", "if_fails": "идём без кредита"}
    r = compute_verdict(_go_card(wait=w))
    assert r["label"] == cv.WAIT and r["label_ru"] == "ЖДАТЬ" and r["wait"] == w
    assert r["overrides"][-1]["rule"] == "wait" and r["overrides"][-1]["from"] == cv.GO


def test_wait_not_applied_after_ruin_cap():
    w = {"trigger": "т", "date": "2026-11-01", "if_fails": "ф"}
    c = _go_card(wait=w)
    c["seats"][0]["ruin_risk"] = "likely"
    r = compute_verdict(c)
    assert r["label"] == cv.RESHAPE and r["wait"] is None and r["notes"]


def test_pillar_fixes():
    c = _go_card()
    c["seats"][0]["pillar_score"] = 4
    c["seats"][1]["pillar_score"] = 5
    r = compute_verdict(c)
    assert r["pillar_fixes"] == [{"seat": "Марк Аврелий", "pillar_score": 4}]


def test_completeness_requires_kill_criteria_and_steps():
    c = _go_card()
    del c["kill_criteria"]
    c["steps"] = []
    r = compute_verdict(c)
    assert r["label"] == cv.GO and r["complete"] is False
    assert set(r["missing"]) == {"kill_criteria", "steps"}


def test_echo_blocks():
    c = _go_card(
        cruxes=[{"question": "Есть ли спрос?", "kind": "fact",
                 "sides": [{"position": "да", "seats": ["Макиавелли"]},
                           {"position": "нет", "seats": ["Марк Аврелий"]}]},
                {"question": "Что важнее — свобода или деньги?", "kind": "values",
                 "sides": [{"position": "свобода", "seats": ["Марк Аврелий"]}]}],
        minority=[{"seat": "Сунь-цзы", "claim": "рано", "right_if": "конкурент выйдет до марта"}])
    r = compute_verdict(c)
    assert [x["question"] for x in r["cruxes"]["fact"]] == ["Есть ли спрос?"]
    assert r["cruxes"]["numbers"] == [] and len(r["cruxes"]["values"]) == 1
    assert r["minority"][0]["right_if"] == "конкурент выйдет до марта"
    assert set(r["falsifiers"]) == {"Марк Аврелий", "Макиавелли", "Сунь-цзы"}
    assert r["questions"]["Сунь-цзы"].startswith("готов ли")


def test_input_not_mutated():
    c = _go_card()
    before = copy.deepcopy(c)
    compute_verdict(c, track_weights={"Марк Аврелий": 1.2})
    assert c == before


# ── подача ─────────────────────────────────────────────────────────────────

def test_render_md_plain_ru():
    c = _go_card(minority=[{"seat": "Сунь-цзы", "claim": "рано", "right_if": "конкурент выйдет"}])
    c["seats"][1]["ruin_risk"] = "likely"
    md = render_verdict_md(compute_verdict(c), lang="ru")
    assert "Вердикт совета: ПЕРЕДЕЛАТЬ" in md
    assert "B 8.2" in md and "статус-кво" in md
    assert "права, если конкурент выйдет" in md
    assert "Остановиться, если" in md and "день 1: написать 20 клиентам" in md
    assert "Перед подписью" in md
    assert "Математика" not in md                 # инженерия только в expert


def test_render_md_expert_has_math_and_falsifiers():
    md = render_verdict_md(compute_verdict(_go_card()), lang="ru", depth="expert")
    assert "B (3×8 + 2×9 + 1×7) / 6 = 8.2" in md
    assert "Что изменит позицию" in md and "разные ответы" in md


def test_render_md_en_labels_no_em_dash():
    c = _go_card(wait={"trigger": "bank reply", "date": "2026-11-01", "if_fails": "go without"})
    r = compute_verdict(c)
    md = render_verdict_md(r, lang="en", depth="expert")
    assert "Council verdict: WAIT" in md and "—" not in md.replace(r["call"], "")
    assert cv.label_text(cv.DONT, "en") == "DON'T DO IT"
    assert cv.label_text(cv.GO_WITH_CONDITIONS, "en") == "GO WITH CONDITIONS"


def test_render_lang_from_env(monkeypatch):
    r = compute_verdict(_go_card())
    monkeypatch.setenv("CONSILIUM_LANG", "en")
    assert "Council verdict" in render_verdict_md(r, lang=None)
    monkeypatch.setenv("CONSILIUM_LANG", "ru")
    assert "Вердикт совета" in render_verdict_md(r, lang=None)


def test_render_md_escapes_html():
    c = _go_card()
    c["seats"][0]["question_for_user"] = "<img src=x onerror=alert(1)>"
    md = render_verdict_md(compute_verdict(c))
    assert "<img" not in md and "&lt;img" in md


def test_render_tolerates_garbage():
    assert render_verdict_md({"label": "NOPE"}) == ""
    assert render_verdict_md(None) == ""
    assert cv.verdict_view({"label": "GO", "scores": "x", "minority": [1]}) is not None


# ── хук session_render ─────────────────────────────────────────────────────

def _session(**kw):
    s = {"question": "Запускать продукт?",
         "advisors": [{"name": "Марк Аврелий",
                       "opinions": [{"marker": "yellow", "argument": "Делай, что должно."}]}],
         "synthesis": "Запускать малым шагом.", "step": "Написать 20 клиентам."}
    s.update(kw)
    return s


def test_session_without_verdict_unchanged():
    s = _session()
    s2 = _session(council_verdict=None, verdict=None)
    assert SR.render_md(s) == SR.render_md(s2)
    assert SR.render_widget(s) == SR.render_widget(s2)
    assert SR.render_html(s) == SR.render_html(s2)
    assert "Вердикт совета" not in SR.render_md(s)


def test_string_verdict_alias_still_synthesis():
    s = {"question": "Q?", "advisors": [], "verdict": "Строковый синтез."}
    md = SR.render_md(s)
    assert "## Синтез" in md and "Строковый синтез." in md and "Вердикт совета:" not in md


@pytest.mark.parametrize("key", ["council_verdict", "verdict"])
def test_session_with_verdict_all_surfaces(key, monkeypatch):
    monkeypatch.delenv("CONSILIUM_LANG", raising=False)
    c = _go_card()
    c["seats"][0]["question_for_user"] = "<b>опасно</b>"
    r = compute_verdict(c)
    s = _session(**{key: r})
    md = SR.render_md(s)
    assert "Вердикт совета: ИДТИ" in md and "B 8.2" in md
    assert md.index("## Синтез") < md.index("Вердикт совета:") < md.index("## Шаг")
    assert "<b>опасно" not in md
    w = SR.render_widget(s)
    assert "Вердикт совета · ИДТИ" in w and "<b>опасно" not in w and "&lt;b&gt;опасно" in w
    assert 'class="eng"' in w and "B (3×8 + 2×9 + 1×7) / 6 = 8.2" in w
    h = SR.render_html(s)
    assert "<section class=verdict>" in h and "<b>опасно" not in h
    assert "Вердикт совета: ИДТИ" in h


def test_session_expert_md_depth():
    s = _session(council_verdict=compute_verdict(_go_card()))
    assert "Математика" not in SR.render_md(s)
    assert "Математика" in SR.render_md(s, depth="expert")


def test_session_garbage_verdict_dict_ignored():
    s = _session(council_verdict={"label": "MAYBE"})
    assert SR.render_md(s) == SR.render_md(_session())
    assert SR.render_widget(s) == SR.render_widget(_session())


def test_export_session_carries_verdict():
    s = _session(council_verdict=compute_verdict(_go_card()))
    out = SR.export_session(s, surface="html")
    assert "<section class=verdict>" in out["content"]


# ── persona: «Где линза ошибается» ─────────────────────────────────────────

def test_scaffold_persona_misfires_section_parsed():
    from mdmeta import parse_misfires
    from scaffold import PD_MISFIRES, scaffold_persona
    md = scaffold_persona("Эпиктет", misfires=PD_MISFIRES["epictetus"])
    assert "## Где линза ошибается" in md
    assert parse_misfires(md) == PD_MISFIRES["epictetus"]
    # без misfires — плейсхолдер, парсер его пропускает
    assert parse_misfires(scaffold_persona("Мудрец")) == []
    assert parse_misfires("---\nname: X\n---\n# X\n## Конституция\nтекст\n") == []


def test_pd_misfires_cover_seeded_figures():
    from scaffold import PD_MISFIRES
    for fid in ("marcus-aurelius", "epictetus", "sun-tzu", "machiavelli"):
        assert 2 <= len(PD_MISFIRES[fid]) <= 3
        for line in PD_MISFIRES[fid]:
            assert "«" not in line and "»" not in line      # не цитаты — фактические границы


def test_diversity_loader_exposes_misfires(tmp_path):
    from diversity_check import load_advisor
    from scaffold import PD_MISFIRES, scaffold_persona
    d = tmp_path / "advisors" / "sun-tzu"
    d.mkdir(parents=True)
    (d / "persona.md").write_text(scaffold_persona("Сунь-цзы", misfires=PD_MISFIRES["sun-tzu"]),
                                  encoding="utf-8")
    a = load_advisor(str(d))
    assert a["misfires"] == PD_MISFIRES["sun-tzu"] and a["lenses"] == set()


def test_board_scaffold_persona_adds_pd_misfires(tmp_path):
    import board
    adv = tmp_path / "advisors" / "machiavelli"
    adv.mkdir(parents=True)
    assert board.cmd_scaffold_persona([str(adv), "--name", "Макиавелли"]) == 0
    from mdmeta import parse_misfires
    from scaffold import PD_MISFIRES
    assert parse_misfires((adv / "persona.md").read_text(encoding="utf-8")) == PD_MISFIRES["machiavelli"]


# ── печать (seal): метку считает КОД, хост её подделать не может ───────────

import json  # noqa: E402


def test_compute_verdict_is_sealed_and_verifies():
    r = compute_verdict(_go_card())
    assert isinstance(r["seal"], str) and len(r["seal"]) == 64
    assert cv.verify_seal(r) is True


def test_seal_survives_json_round_trip_and_lost_dot_zero():
    r = compute_verdict(_go_card())
    back = json.loads(json.dumps(r, ensure_ascii=False))
    assert cv.verify_seal(back)
    # хост пересериализовал 8.0 → 8: это не подделка
    back["recommended"]["score"] = int(back["recommended"]["score"]) \
        if float(back["recommended"]["score"]).is_integer() else back["recommended"]["score"]
    back["spread"] = int(back["spread"])
    assert cv.verify_seal(back)


@pytest.mark.parametrize("mutate", [
    lambda r: r.__setitem__("label", cv.GO if r["label"] != cv.GO else cv.DONT),
    lambda r: r.__setitem__("overrides", []),
    lambda r: r["recommended"].__setitem__("score", 9.9),
    lambda r: r.__setitem__("extra", 1),
    lambda r: r.pop("missing"),
    lambda r: r.__setitem__("seal", "0" * 64),
])
def test_tampered_verdict_fails_seal(mutate):
    c = _go_card()
    c["seats"][0]["ruin_risk"] = "likely"                  # есть поправка — её и «теряем»
    r = compute_verdict(c)
    assert cv.verify_seal(r)
    mutate(r)
    assert cv.verify_seal(r) is False


@pytest.mark.parametrize("bad", [None, 5, "GO", [], {"label": "GO"}, {"label": "GO", "seal": 5},
                                 {"label": "GO", "seal": "x"}, {"label": object(), "seal": "x"},
                                 {1: "a", "b": 2, "seal": "x"}, {"label": float("nan"), "seal": "x"}])
def test_verify_seal_never_raises(bad):
    assert cv.verify_seal(bad) is False


def _forged_session(**kw):
    return _session(council_verdict={"label": "GO", "call": "Рекомендация совета: B — ИДТИ.",
                                     "recommended": {"id": "B", "label": "x"}}, **kw)


def test_gate_drops_forged_verdict_and_explains():
    s = _forged_session()
    assert "Вердикт совета" in SR.render_md(s)             # session_render сам НЕ проверяет
    out, rejected = cv.gate_session_verdict(s)
    assert "council_verdict" not in out and "council_verdict" in s   # вход не мутирован
    assert rejected and "не подтверждена кодом council_verdict" in rejected
    assert "Вердикт совета" not in SR.render_md(out)


def test_gate_drops_forged_verdict_alias_keeps_string_alias():
    out, rej = cv.gate_session_verdict(_session(verdict={"label": "GO"}))
    assert rej and "verdict" not in out
    s = {"question": "Q?", "advisors": [], "verdict": "Строковый синтез."}
    out, rej = cv.gate_session_verdict(s)
    assert rej is None and out is s


def test_gate_passes_sealed_verdict_untouched():
    r = compute_verdict(_go_card())
    s = _session(council_verdict=json.loads(json.dumps(r, ensure_ascii=False)))
    out, rej = cv.gate_session_verdict(s)
    assert rej is None and out is s
    assert "Вердикт совета: ИДТИ" in SR.render_md(out)


def test_gate_recomputes_from_scorecard_ignoring_host_verdict():
    c = _go_card()
    s = _forged_session(council_scorecard=c, council_track_weights={"Марк Аврелий": 0.5})
    s["verdict"] = {"label": "GO"}
    out, rej = cv.gate_session_verdict(s)
    assert rej is None and "verdict" not in out
    expect = compute_verdict(c, track_weights={"Марк Аврелий": 0.5})
    assert out["council_verdict"]["label"] == expect["label"]
    assert out["council_verdict"]["weights_source"] == "relevance×track"
    assert cv.verify_seal(out["council_verdict"])


def test_gate_bad_scorecard_drops_block_with_errors():
    c = _go_card()
    c["seats"][0]["weight"] = 9
    out, rej = cv.gate_session_verdict(_forged_session(council_scorecard=c))
    assert "council_verdict" not in out and "weight" in rej
    out, rej = cv.gate_session_verdict(_session(council_scorecard=_go_card(),
                                                council_track_weights={"Марк Аврелий": "x"}))
    assert "council_verdict" not in out and rej


def test_mcp_render_session_rejects_forged_and_recomputes_scorecard():
    import mcp_server as srv
    r = srv._render_session(_forged_session(), surface="md")
    assert "Вердикт совета" not in r["content"]
    assert "не подтверждена кодом council_verdict" in r["verdict_rejected"]
    for surface in ("md", "html", "widget"):
        r = srv._render_session(_forged_session(), surface=surface)
        assert r.get("verdict_rejected") and "ИДТИ" not in r["content"]
    r = srv._render_session(_forged_session(council_scorecard=_go_card()), surface="md")
    assert "verdict_rejected" not in r and "Вердикт совета: ИДТИ" in r["content"]
    # честный путь: выход тула council_verdict → объект заседания как есть
    tool = srv._council_verdict_tool(_go_card())
    assert "seal" in tool["hint"]
    r = srv._render_session(_session(council_verdict=tool["verdict"]), surface="widget")
    assert "verdict_rejected" not in r and "Вердикт совета · ИДТИ" in r["content"]


def test_mcp_export_session_rejects_forged():
    import mcp_server as srv
    out = srv._export_session(_forged_session(), surface="html")
    assert "<section class=verdict>" not in out["content"] and out["verdict_rejected"]
    out = srv._export_session(_session(council_verdict=compute_verdict(_go_card())))
    assert "Вердикт совета: ИДТИ" in out["content"] and "verdict_rejected" not in out


# ── ничья по СЫРОМУ баллу, дубли имён без регистра ─────────────────────────

def test_rounded_equal_but_raw_differs_is_not_a_tie():
    # A (статус-кво) 19.4/3 = 6.467 → 6.5; B 19.6/3 = 6.533 → 6.5. Раньше: «ничья» → статус-кво.
    c = _card(seats=[_seat("Марк Аврелий", 1, 6, 6.5), _seat("Макиавелли", 1, 6, 6.5),
                     _seat("Сунь-цзы", 1, 7.4, 6.6)])
    r = compute_verdict(c)
    by = {x["id"]: x["score"] for x in r["scores"]}
    assert by["A"] == by["B"] == 6.5                      # показ — округлённый
    assert r["tie"] is False and r["tied"] == []
    assert r["recommended"]["id"] == "B" and r["label"] == cv.GO_WITH_CONDITIONS
    assert any("не ничья" in n for n in r["notes"])


def test_raw_ranking_beats_rounding_for_action_options_too():
    c = _card(options=[{"id": "A", "label": "ничего", "status_quo": True},
                       {"id": "B", "label": "б"}, {"id": "C", "label": "в"}],
              seats=[_seat("Марк Аврелий", 1, 1, 7, 7.2), _seat("Макиавелли", 1, 1, 7.1, 7)])
    r = compute_verdict(c)          # B 7.05→7.1, C 7.1 — показ равный, по сырому C выше
    assert r["recommended"]["id"] == "C" and r["tie"] is False


def test_exact_raw_tie_still_prefers_status_quo():
    c = _card(seats=[_seat("Марк Аврелий", 2, 6, 7), _seat("Макиавелли", 2, 7, 6)])
    r = compute_verdict(c, track_weights={"марк аврелий": 1.1, "МАКИАВЕЛЛИ": 1.1})
    assert r["tie"] is True and r["recommended"]["id"] == "A"


@pytest.mark.parametrize("dup", ["марк аврелий", " Марк Аврелий ", "МАРК АВРЕЛИЙ"])
def test_duplicate_seat_names_case_insensitive(dup):
    c = _card()
    c["seats"][1]["name"] = dup
    errs = validate_scorecard(c)
    assert any("повторяется" in e for e in errs)


# ── устойчивость подачи: кривой вердикт от хоста не роняет рендер ──────────

_XSS = "<img src=x onerror=alert(1)>"

_MALFORMED = [
    {"label": "GO", "scores": 5},
    {"label": "GO", "minority": 5},
    {"label": "GO", "overrides": "x"},
    {"label": "GO", "overrides": [5, None, "x", {"rule": "ruin_cap", "seats": 5, "to": ["GO"]}]},
    {"label": "GO", "overrides": [{"rule": "one_way_cap", "spread": "wide", "to": {"a": 1}}]},
    {"label": "GO", "options": "not a list", "scores": {"A": 1}},
    {"label": "GO", "scores": [{"id": _XSS, "score": "nan?"}, {"id": "B", "score": 10 ** 400}]},
    {"label": "GO", "scores": [{"id": _XSS, "score": 7, "math": _XSS}]},
    {"label": "GO", "recommended": "B", "call": _XSS},
    {"label": "GO", "recommended": {"id": [1], "label": {"x": _XSS}}},
    {"label": "GO", "spread": [1], "council_confidence": (1, 2)},
    {"label": "GO", "spread": 10 ** 400},
    {"label": "GO", "kill_criteria": 5, "steps": "abc", "pillar_fixes": 7},
    {"label": "GO", "kill_criteria": [_XSS, None, 3], "steps": [5, {"when": _XSS}]},
    {"label": "GO", "missing": [["cheapest_test"], {"a": 1}, "steps", _XSS]},
    {"label": "GO", "missing": 5, "questions": [1], "falsifiers": "x"},
    {"label": "GO", "questions": {_XSS: _XSS}, "falsifiers": {1: None}},
    {"label": "GO", "weights": {"X": 5, "Y": {"effective": "a"}}, "weights_source": (1, 2)},
    {"label": "GO", "weights": [1, 2]},
    {"label": "GO", "tie": True, "tied": 5},
    {"label": "GO", "tie": True, "tied": [1, None, _XSS]},
    {"label": "GO", "cruxes": 5},
    {"label": "GO", "cruxes": {"fact": 5, "numbers": "abc", "values": [None, {"question": _XSS}]}},
    {"label": "GO", "wait": {"trigger": _XSS, "date": 5}},
    {"label": "GO", "wait": "soon", "cheapest_test": {"a": _XSS}},
    {"label": "GO", "unanimity_alarm": True, "unanimity_instruction": [_XSS]},
    {"label": ["GO"]},
    {"label": {"x": 1}},
    {"label": 5},
    {"label": "GO", "minority": [None, 1, {"seat": _XSS, "claim": [1], "right_if": None}]},
]


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("bad", _MALFORMED)
def test_malformed_verdict_never_raises_and_stays_escaped(bad, lang):
    v = cv.verdict_view(bad, lang)
    assert v is None or isinstance(v, dict)
    for depth in ("plain", "expert"):
        md = render_verdict_md(bad, lang=lang, depth=depth)
        assert "<img" not in md
    s = _session(council_verdict=bad, lang=lang)
    for out in (SR.render_md(s, depth="expert"), SR.render_widget(s, depth="expert"),
                SR.render_html(s), SR.export_session(s)["content"],
                SR.export_session(s, surface="html")["content"]):
        assert "<img" not in out


def test_malformed_verdict_through_mcp_never_raises():
    import mcp_server as srv
    for bad in _MALFORMED:
        for surface in ("md", "html", "widget"):
            r = srv._render_session(_session(council_verdict=bad), surface=surface)
            assert r.get("verdict_rejected") and "<img" not in r["content"]


def test_opening_kind_on_full_renderer_still_gates_verdict():
    """kind="opening" + md/html рисует полный рендерер → гейт печати обязан работать и там."""
    import mcp_server as srv
    for surface in ("md", "html"):
        out = srv._render_session(_forged_session(), surface=surface, kind="opening")
        assert out.get("verdict_rejected") and "ИДТИ" not in out["content"], surface
