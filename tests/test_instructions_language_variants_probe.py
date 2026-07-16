"""Офлайн-тесты пробы ПЛЕЧЕЙ (варианты INSTRUCTIONS против языкового прайора).

Сеть не трогаем: чистые функции (патч вариантов, счёт withheld, двусторонний вердикт) бьются
изолированно, вызов модели мокается. Env правим ТОЛЬКО через monkeypatch — соседний тест
(tests/test_antisycophancy_probe.py) течёт LLM_BACKEND=openrouter на весь прогон, и любой
настоящий ключ в os.environ увёл бы сьют в живую сеть.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "scripts"), os.path.join(_ROOT, "scripts", "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import instructions_language_probe as BASE  # noqa: E402
import instructions_language_variants_probe as V  # noqa: E402


# --- набор плечей ------------------------------------------------------------

def test_required_arms_present():
    # Четыре плеча заказаны владельцем; en_bottom — наш пятый (обоснование в докстринге).
    assert {"baseline", "ru_top", "en_top", "en_top_plus_rule7"} <= set(V.ARMS)


def test_baseline_is_first_arm():
    # Baseline меряется первым: не воспроизвёлся — весь замер под вопросом, дальше можно не читать.
    assert V.ARMS[0] == "baseline"


def test_arms_unique():
    assert len(set(V.ARMS)) == len(V.ARMS)


# --- патч вариантов: baseline ------------------------------------------------

def test_baseline_arm_leaves_instructions_untouched():
    base = "ПРАВИЛА. 7. Подача: язык юзера; дальше."
    assert V.apply_variant(base, "baseline") == base


def test_unknown_arm_raises_not_silently_baseline():
    # Опечатка в имени плеча обязана падать: молчаливый откат к baseline дал бы «плечо не
    # работает» на плече, которого не было.
    with pytest.raises(ValueError):
        V.apply_variant("ПРАВИЛА", "en_topp")


# --- патч вариантов: верхние блоки -------------------------------------------

def test_ru_top_prepends_block_at_very_start():
    base = "Consilium. 0. БЕЗОПАСНОСТЬ. 7. Подача: язык юзера; дальше."
    out = V.apply_variant(base, "ru_top")
    assert out.startswith(V.RU_TOP_BLOCK)
    assert out.index(V.RU_TOP_BLOCK) < out.index("0. БЕЗОПАСНОСТЬ")   # до Правила 0


def test_en_top_prepends_block_at_very_start():
    base = "Consilium. 0. БЕЗОПАСНОСТЬ. 7. Подача: язык юзера; дальше."
    out = V.apply_variant(base, "en_top")
    assert out.startswith(V.EN_TOP_BLOCK)
    assert out.index(V.EN_TOP_BLOCK) < out.index("0. БЕЗОПАСНОСТЬ")


def test_top_arms_preserve_base_text_verbatim():
    # Плечо = base + блок, РОВНО. Тронули бы сам текст — мерили бы уже не INSTRUCTIONS.
    base = "Consilium. 0. БЕЗОПАСНОСТЬ. 7. Подача: язык юзера; дальше."
    for arm in ("ru_top", "en_top"):
        assert base in V.apply_variant(base, arm)


def test_en_top_block_has_no_cyrillic():
    # Плечо «англ. блок» обязано быть английским: русский внутри него смазал бы контраст с ru_top.
    assert BASE.cyrillic_share(V.EN_TOP_BLOCK) == 0.0


def test_ru_top_block_is_russian():
    assert BASE.cyrillic_share(V.RU_TOP_BLOCK) > 0.5


def test_ru_top_and_en_top_differ():
    base = "Consilium. 7. Подача: язык юзера;"
    assert V.apply_variant(base, "ru_top") != V.apply_variant(base, "en_top")


# --- патч вариантов: правка самой строки Правила 7 ----------------------------

def test_en_top_plus_rule7_replaces_rule7_line_and_keeps_top_block():
    base = "Consilium. 0. БЕЗОПАСНОСТЬ. 7. Подача: язык юзера; 🔵-цитата дословна."
    out = V.apply_variant(base, "en_top_plus_rule7")
    assert out.startswith(V.EN_TOP_BLOCK)
    assert V.RULE7_ANCHOR not in out                 # старая формулировка ушла
    assert V.RULE7_EN_RULE in out                    # новая на её месте
    assert "🔵-цитата дословна." in out              # остаток строки Правила 7 не пострадал


def test_en_top_plus_rule7_is_strictly_more_than_en_top():
    # Гард против вырождения: если патч Правила 7 не сработал, плечо стало бы копией en_top,
    # и мы бы приписали его результат правке, которой не было.
    base = "Consilium. 7. Подача: язык юзера; дальше."
    assert V.apply_variant(base, "en_top_plus_rule7") != V.apply_variant(base, "en_top")


def test_rule7_patch_raises_when_anchor_missing():
    # Fail-closed: текст INSTRUCTIONS растёт, якорь может уехать. Молча вернуть непропатченное —
    # значит выдать ложный вывод о плече.
    with pytest.raises(ValueError):
        V.apply_variant("Правила без седьмого пункта", "en_top_plus_rule7")


def test_rule7_patch_raises_when_anchor_ambiguous():
    with pytest.raises(ValueError):
        V.apply_variant("Подача: язык юзера ... и снова Подача: язык юзера", "en_top_plus_rule7")


def test_rule7_replacement_is_english():
    assert BASE.cyrillic_share(V.RULE7_EN_RULE) == 0.0


# --- премисы на ЖИВОМ продуктовом тексте (ловят дрейф) -----------------------

def test_anchor_exists_exactly_once_in_product_instructions():
    # Премиса плеча en_top_plus_rule7. Разъедется — тест упадёт здесь, а не в вердикте.
    assert BASE.load_instructions().count(V.RULE7_ANCHOR) == 1


def test_all_arms_build_from_live_instructions():
    built = V.build_variants()
    assert set(built) == set(V.ARMS)
    assert built["baseline"] == BASE.load_instructions()
    for arm in V.ARMS:
        if arm != "baseline":
            assert len(built[arm]) > len(built["baseline"])


def test_variants_come_from_product_code_not_a_copy():
    import mcp_server
    assert V.build_variants()["baseline"] == mcp_server.INSTRUCTIONS


def test_variant_prompt_embeds_variant_and_question():
    p = V.build_variant_prompt("ПРАВИЛА ТУТ", "Should I raise prices?")
    assert "ПРАВИЛА ТУТ" in p and "Should I raise prices?" in p


# --- withheld на виду --------------------------------------------------------

def test_withheld_count_counts_failed_calls():
    rows = [{"withheld": True, "category": None}, {"withheld": False, "category": "english"},
            {"withheld": True, "category": None}]
    assert V.withheld_count(rows) == 2


def test_withheld_count_zero_when_all_answered():
    assert V.withheld_count([{"withheld": False, "category": "english"}]) == 0


def test_withheld_count_includes_empty_answers_that_did_not_raise():
    # Пустой ответ (контент-фильтр/квирк провайдера) вызов НЕ роняет, но доли не даёт — он так же
    # выпадает из знаменателя. Считать только упавшие = напечатать «withheld=0» над цифрой,
    # посчитанной по огрызку выборки. Ровно этот дефект уже дал ложный вердикт в этой сессии.
    rows = [{"withheld": False, "category": None}, {"withheld": False, "category": "english"}]
    assert V.withheld_count(rows) == 1


def test_run_arm_empty_answer_is_counted_withheld():
    arm = V.run_arm(BASE.build_battery(n=1), "baseline", "ПРАВИЛА", "fake", call=lambda p, m: "")
    assert arm["strata"]["en_with"]["withheld"] == 1


# --- пол выборки: вердикт по огрызку — не вердикт -----------------------------

def test_min_measured_floor_is_sane():
    assert 1 < V.MIN_MEASURED <= BASE.DEFAULT_N


def test_thin_sample_cannot_fix_en_even_at_100_percent():
    # 7 из 8 не ответили, единственный выживший — английский. share=1.0, n=1: без пола выборки
    # это «плечо работает». Это не результат, это один ответ.
    thin = _rows(None, n=7) + _rows("english", n=1)
    v = V.arm_verdict(thin, _rows("russian"), _SENSITIVE)
    assert v["fixes_en"] is False
    assert v["works"] is False


def test_thin_sample_cannot_certify_ru_intact():
    thin = _rows(None, n=7) + _rows("russian", n=1)
    v = V.arm_verdict(_rows("english"), thin, _SENSITIVE)
    assert v["keeps_ru"] is False


def test_full_sample_at_supermajority_still_passes():
    # Пол не должен зарубать здоровый замер: 8 из 8 измерены.
    v = V.arm_verdict(_rows("english"), _rows("russian"), _SENSITIVE)
    assert v["works"] is True


def test_calibration_floor_blinds_instrument_on_thin_controls():
    # Калибровка по двум выжившим ответам «подтверждает» чувствительность и разблокирует ВСЕ
    # плечи. Пол обязан ослепить прибор вместо этого.
    thin_ru = _rows(None, n=6) + _rows("russian", n=2)
    c = V.calibration_with_floor(thin_ru, _rows("english"))
    assert c["sensitive"] is False and c["label"] == "ПРИБОР СЛЕП"


def test_calibration_floor_passes_healthy_controls():
    c = V.calibration_with_floor(_rows("russian"), _rows("english"))
    assert c["sensitive"] is True


def test_calibration_floor_keeps_base_reasons():
    c = V.calibration_with_floor(_rows("english"), _rows("english"))
    assert c["sensitive"] is False and any("контроль 1" in r for r in c["reasons"])


# --- пересчёт вердиктов из сохранённого сырья --------------------------------

def _fake_entry(en_cat, ru_cat):
    def rows(cat):
        return [{"id": str(i), "withheld": cat is None, "share": 0.0 if cat == "english" else 1.0,
                 "category": cat, "excerpt": ""} for i in range(8)]
    arms = {a: {"arm": a, "strata": {"en_with": {"rows": rows(en_cat)},
                                     "ru_with": {"rows": rows(ru_cat)}}} for a in V.ARMS}
    return {"model": "fake", "control_en_bare": {"rows": rows("english")}, "arms": arms}


def test_recompute_rebuilds_verdicts_from_stored_rows():
    e = V.recompute_model(_fake_entry("english", "russian"))
    assert e["calibration"]["sensitive"] is True
    assert e["arms"]["en_top"]["verdict"]["works"] is True
    assert e["summary"]["winners"]


def test_recompute_applies_current_stricter_logic():
    # Сырьё дорогое (сотни живых вызовов), логика вердикта — бесплатная. Ужесточили правила →
    # пересчитываем сохранённое сырьё, а не платим за сеть заново и не оставляем старый вердикт.
    e = V.recompute_model(_fake_entry("russian", "russian"))
    assert e["arms"]["baseline"]["verdict"]["works"] is False
    assert e["summary"]["winners"] == []


def test_run_arm_failed_call_is_withheld_not_guessed():
    def boom(prompt, model):
        raise RuntimeError("сеть отвалилась")
    arm = V.run_arm(BASE.build_battery(n=1), "baseline", "ПРАВИЛА", "fake", call=boom)
    assert arm["strata"]["en_with"]["withheld"] == 1
    assert arm["strata"]["en_with"]["dominant"]["label"] is None


def test_run_arm_measures_both_sides():
    # Обе стороны обязательны: плечо, чинящее EN и ломающее RU, — провал, а увидеть это можно
    # только замерив ru_with на КАЖДОМ плече, а не только на baseline.
    seen = []

    def call(prompt, model):
        seen.append(prompt)
        return "Answer."
    arm = V.run_arm(BASE.build_battery(n=1), "baseline", "ПРАВИЛА", "fake", call=call)
    assert set(arm["strata"]) == {"en_with", "ru_with"}
    assert len(seen) == 2


def test_run_arm_uses_the_patched_instructions_it_was_given():
    seen = []

    def call(prompt, model):
        seen.append(prompt)
        return "Answer."
    V.run_arm(BASE.build_battery(n=1), "en_top", "ПАТЧЕНЫЙ ТЕКСТ ПЛЕЧА", "fake", call=call)
    assert all("ПАТЧЕНЫЙ ТЕКСТ ПЛЕЧА" in p for p in seen)


# --- ДВУСТОРОННИЙ вердикт (сердце задачи) ------------------------------------

_SENSITIVE = {"sensitive": True, "label": "ПРИБОР ЧУВСТВИТЕЛЕН", "reasons": []}
_BLIND = {"sensitive": False, "label": "ПРИБОР СЛЕП", "reasons": ["контроль 2 не отработал"]}


def _rows(cat, n=8):
    return [{"category": cat, "withheld": cat is None} for _ in range(n)]


def test_arm_works_only_when_en_fixed_and_ru_intact():
    v = V.arm_verdict(_rows("english"), _rows("russian"), _SENSITIVE)
    assert v["works"] is True and v["fixes_en"] is True and v["keeps_ru"] is True
    assert "РАБОТАЕТ" in v["text"]


def test_arm_that_fixes_en_but_breaks_ru_is_failure_not_victory():
    v = V.arm_verdict(_rows("english"), _rows("english"), _SENSITIVE)
    assert v["works"] is False and v["fixes_en"] is True and v["keeps_ru"] is False
    assert "СЛОМАЛ РУССКИЙ" in v["text"].upper()


def test_arm_that_leaves_en_russian_does_not_work():
    v = V.arm_verdict(_rows("russian"), _rows("russian"), _SENSITIVE)
    assert v["works"] is False and v["fixes_en"] is False and v["keeps_ru"] is True
    assert "НЕ РАБОТАЕТ" in v["text"].upper()


def test_arm_mixed_en_is_failure_not_rounded_into_success():
    # Смесь — самостоятельная категория провала: англоязычный юзер получил кашу.
    v = V.arm_verdict(_rows("mixed"), _rows("russian"), _SENSITIVE)
    assert v["works"] is False and v["fixes_en"] is False


def test_arm_mixed_ru_breaks_the_owner_path():
    v = V.arm_verdict(_rows("english"), _rows("mixed"), _SENSITIVE)
    assert v["works"] is False and v["keeps_ru"] is False


def test_arm_needs_supermajority_on_both_sides():
    half = [{"category": "english", "withheld": False}] * 4 + \
           [{"category": "russian", "withheld": False}] * 4
    assert V.arm_verdict(half, _rows("russian"), _SENSITIVE)["fixes_en"] is False
    assert V.arm_verdict(_rows("english"), half, _SENSITIVE)["keeps_ru"] is False


def test_arm_verdict_annulled_when_instrument_blind():
    v = V.arm_verdict(_rows("english"), _rows("russian"), _BLIND)
    assert v["works"] is None and "АННУЛИР" in v["text"].upper()


def test_arm_verdict_shouts_about_withheld():
    rows = _rows("english", n=5) + _rows(None, n=3)
    v = V.arm_verdict(rows, _rows("russian"), _SENSITIVE)
    assert v["withheld"]["en_with"] == 3
    assert "WITHHELD" in v["text"].upper()


def test_arm_verdict_silent_when_nothing_withheld():
    v = V.arm_verdict(_rows("english"), _rows("russian"), _SENSITIVE)
    assert v["withheld"] == {"en_with": 0, "ru_with": 0}
    assert "WITHHELD" not in v["text"].upper()


def test_arm_verdict_text_is_russian():
    for en, ru in (("english", "russian"), ("russian", "russian"), ("english", "english")):
        assert BASE.cyrillic_share(V.arm_verdict(_rows(en), _rows(ru), _SENSITIVE)["text"]) > 0.5


# --- сводка по плечам --------------------------------------------------------

def test_summary_names_a_winner_when_one_arm_does_both():
    arms = {"baseline": {"verdict": {"works": False}},
            "en_top": {"verdict": {"works": True}}}
    s = V.summarize_arms(arms)
    assert s["winners"] == ["en_top"]


def test_summary_reports_no_winner_when_all_arms_fail():
    arms = {"baseline": {"verdict": {"works": False}}, "en_top": {"verdict": {"works": False}}}
    s = V.summarize_arms(arms)
    assert s["winners"] == []
    assert "НЕТ" in s["text"].upper()


def test_summary_excludes_arms_that_broke_russian_from_winners():
    arms = {"en_top": {"verdict": {"works": False, "fixes_en": True, "keeps_ru": False}}}
    assert V.summarize_arms(arms)["winners"] == []


def test_summary_ignores_annulled_arms():
    arms = {"en_top": {"verdict": {"works": None}}}
    assert V.summarize_arms(arms)["winners"] == []


def test_summary_of_fully_annulled_run_is_not_reported_as_a_negative_result():
    # Слепой прибор ≠ «правка не помогла». Печатать «текстовая правка провалилась» над
    # несостоявшимся замером — то самое уверенное враньё, против которого построена проба.
    arms = {a: {"verdict": {"works": None}} for a in V.ARMS}
    s = V.summarize_arms(arms)
    assert s["winners"] == []
    assert "АННУЛИР" in s["text"].upper()
    assert "провалилась" not in s["text"]


def test_summary_flags_partially_annulled_arms():
    arms = {"baseline": {"verdict": {"works": False, "fixes_en": False, "keeps_ru": True}},
            "en_top": {"verdict": {"works": None}}}
    s = V.summarize_arms(arms)
    assert s["annulled"] == ["en_top"]
    assert "en_top" in s["text"]


# --- приватность / гигиена ---------------------------------------------------

def test_probe_carries_no_private_advisor_slugs():
    src = open(V.__file__, encoding="utf-8").read()
    assert "advisors/" not in src


def test_probe_never_prints_key_value():
    import re
    src = open(V.__file__, encoding="utf-8").read()
    assert not re.search(r"print\([^)]*getenv\(['\"]OPENROUTER_API_KEY", src)


# --- CLI ---------------------------------------------------------------------

def test_dry_run_exits_clean_without_network(capsys):
    assert V.main([]) == 0
    out = capsys.readouterr().out
    assert "--run" in out
    for arm in V.ARMS:
        assert arm in out


def test_live_run_refuses_without_key(monkeypatch, capsys):
    # Без ключа — честный выход, а не тихий прогон в никуда.
    monkeypatch.setattr(V, "_load_key_from_dotenv", lambda: False)
    assert V.main(["--run"]) == 2
