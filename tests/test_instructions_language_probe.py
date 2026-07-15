"""Офлайн-тесты пробы языка INSTRUCTIONS. Сеть не трогаем: чистые функции (счёт кириллицы,
категоризация, калибровка, вердикт) бьются изолированно, вызов модели мокается."""
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_ROOT, "scripts"), os.path.join(_ROOT, "scripts", "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import instructions_language_probe as P  # noqa: E402


# --- метрика: доля кириллицы -------------------------------------------------

def test_cyrillic_share_pure_russian():
    assert P.cyrillic_share("Совет директоров") == 1.0


def test_cyrillic_share_pure_english():
    assert P.cyrillic_share("Raise your prices.") == 0.0


def test_cyrillic_share_half():
    assert P.cyrillic_share("абвг abcd") == pytest.approx(0.5)


def test_cyrillic_share_ignores_digits_and_punctuation():
    # Цифры/пунктуация/эмодзи не буквы — не должны разбавлять знаменатель.
    assert P.cyrillic_share("2026!!! 🔵 abcd") == 0.0


def test_cyrillic_share_no_letters_is_none():
    # Ноль букв → доли не существует. Не 0.0 (это соврало бы «английский»).
    assert P.cyrillic_share("123 !!! 🔵") is None
    assert P.cyrillic_share("") is None


def test_cyrillic_share_counts_yo():
    assert P.cyrillic_share("Ёё") == 1.0


# --- категоризация -----------------------------------------------------------

def test_categorize_english_below_threshold():
    assert P.categorize(0.0) == "english"
    assert P.categorize(0.05) == "english"


def test_categorize_russian_above_threshold():
    assert P.categorize(0.8) == "russian"
    assert P.categorize(1.0) == "russian"


def test_categorize_mixed_between():
    assert P.categorize(0.30) == "mixed"


def test_categorize_boundaries_are_mixed_not_rounded_into_success():
    # Ровно на пороге — уже не «английский»; смешанный НЕ округляем в успех.
    assert P.categorize(P.THRESH_EN) == "mixed"
    assert P.categorize(P.THRESH_RU) == "mixed"


def test_categorize_none_share_is_none():
    assert P.categorize(None) is None


def test_thresholds_are_sane():
    assert 0.0 < P.THRESH_EN < P.THRESH_RU < 1.0


# --- INSTRUCTIONS берутся ИЗ КОДА, не копией ---------------------------------

def test_instructions_come_from_product_code():
    import mcp_server
    assert P.load_instructions() == mcp_server.INSTRUCTIONS


def test_instructions_are_mostly_cyrillic_premise_holds():
    # Премиса замера: несущий текст русский. Развалится — проба меряет не то.
    assert P.cyrillic_share(P.load_instructions()) > 0.5


# --- батарея -----------------------------------------------------------------

def test_battery_is_paired_and_sized():
    bat = P.build_battery()
    assert len(bat) == P.DEFAULT_N
    assert all({"id", "en", "ru"} <= set(item) for item in bat)


def test_battery_en_questions_have_no_cyrillic():
    assert all(P.cyrillic_share(i["en"]) == 0.0 for i in P.build_battery())


def test_battery_ru_questions_are_russian():
    assert all(P.cyrillic_share(i["ru"]) > 0.5 for i in P.build_battery())


def test_battery_ids_unique():
    bat = P.build_battery()
    assert len({i["id"] for i in bat}) == len(bat)


def test_battery_respects_n():
    assert len(P.build_battery(n=3)) == 3


def test_battery_carries_no_private_slugs():
    # Приватность: слаги частных советников не живут ни в вопросах, ни в id.
    blob = " ".join(i["id"] + i["en"] + i["ru"] for i in P.build_battery()).lower()
    assert "advisors/" not in blob and "/" not in blob


# --- сборка промпта: плечи различаются РОВНО наличием INSTRUCTIONS ------------

def test_with_instructions_arm_embeds_full_instructions():
    p = P.build_prompt("Should I raise prices?", with_instructions=True)
    assert P.load_instructions() in p
    assert "Should I raise prices?" in p


def test_bare_arm_has_no_instructions():
    p = P.build_prompt("Should I raise prices?", with_instructions=False)
    assert P.load_instructions() not in p
    assert "Should I raise prices?" in p


def test_bare_arm_prompt_has_no_cyrillic():
    # Контроль «базовый язык модели» обязан быть чист: любой русский в промпте — свой же прайор.
    assert P.cyrillic_share(P.build_prompt("Should I raise prices?", with_instructions=False)) == 0.0


# --- прогон страты (сеть мокнута) --------------------------------------------

def test_run_stratum_collects_shares_and_categories():
    rows = P.run_stratum(P.build_battery(n=2), "en", with_instructions=True,
                         model="fake", call=lambda p, m: "Raise your prices now.")
    assert [r["category"] for r in rows] == ["english", "english"]
    assert all(r["share"] == 0.0 for r in rows)


def test_run_stratum_uses_ru_field_for_ru_stratum():
    seen = []

    def call(prompt, model):
        seen.append(prompt)
        return "Подними цены."
    P.run_stratum(P.build_battery(n=1), "ru", with_instructions=True, model="fake", call=call)
    assert P.build_battery(n=1)[0]["ru"] in seen[0]


def test_run_stratum_failed_call_is_withheld_not_guessed():
    def boom(prompt, model):
        raise RuntimeError("сеть отвалилась")
    rows = P.run_stratum(P.build_battery(n=1), "en", with_instructions=True,
                         model="fake", call=boom)
    assert rows[0]["category"] is None and rows[0]["withheld"] is True


def test_run_stratum_does_not_store_raw_answer_verbatim_beyond_excerpt():
    rows = P.run_stratum(P.build_battery(n=1), "en", with_instructions=True, model="fake",
                         call=lambda p, m: "x" * 5000)
    assert len(rows[0]["excerpt"]) <= P.EXCERPT_CHARS


# --- агрегация ---------------------------------------------------------------

def test_dominant_category_picks_majority():
    rows = [{"category": "english"}, {"category": "english"}, {"category": "russian"}]
    dom = P.dominant(rows)
    assert dom["label"] == "english" and dom["share"] == pytest.approx(2 / 3) and dom["n"] == 3


def test_dominant_ignores_withheld():
    rows = [{"category": None}, {"category": "russian"}]
    assert P.dominant(rows)["label"] == "russian" and P.dominant(rows)["n"] == 1


def test_dominant_of_nothing_is_none():
    assert P.dominant([{"category": None}])["label"] is None


# --- КАЛИБРОВКА (сердце замера) ----------------------------------------------

def _rows(cat, n=8):
    return [{"category": cat} for _ in range(n)]


def test_calibration_sensitive_when_both_controls_fire():
    c = P.calibration_verdict(_rows("russian"), _rows("english"))
    assert c["sensitive"] is True and c["label"] == "ПРИБОР ЧУВСТВИТЕЛЕН"


def test_calibration_blind_when_russian_question_gives_english():
    # Контроль 1 провален: модель игнорирует и правило, и язык вопроса → мерить нечем.
    c = P.calibration_verdict(_rows("english"), _rows("english"))
    assert c["sensitive"] is False and c["label"] == "ПРИБОР СЛЕП"
    assert any("контроль 1" in r for r in c["reasons"])


def test_calibration_blind_when_bare_english_gives_russian():
    # Контроль 2 провален: модель и без INSTRUCTIONS отвечает по-русски → эффект не наш.
    c = P.calibration_verdict(_rows("russian"), _rows("russian"))
    assert c["sensitive"] is False
    assert any("контроль 2" in r for r in c["reasons"])


def test_calibration_blind_when_no_measurements():
    c = P.calibration_verdict(_rows(None), _rows(None))
    assert c["sensitive"] is False


def test_calibration_needs_supermajority():
    mixed_bag = [{"category": "russian"}] * 4 + [{"category": "english"}] * 4
    assert P.calibration_verdict(mixed_bag, _rows("english"))["sensitive"] is False


# --- вердикт по Правилу 7 ----------------------------------------------------

_SENSITIVE = {"sensitive": True, "label": "ПРИБОР ЧУВСТВИТЕЛЕН", "reasons": []}
_BLIND = {"sensitive": False, "label": "ПРИБОР СЛЕП", "reasons": ["контроль 1 не отработал"]}


def test_rule7_works_when_english_dominates():
    v = P.rule7_verdict(_rows("english"), _SENSITIVE)
    assert v["works"] is True and "РАБОТАЕТ" in v["text"]


def test_rule7_fails_when_russian_dominates():
    v = P.rule7_verdict(_rows("russian"), _SENSITIVE)
    assert v["works"] is False and "НЕ РАБОТАЕТ" in v["text"]


def test_rule7_mixed_is_failure_not_success():
    # Смешанный ответ — отдельная категория провала для дистрибуции, не «почти успех».
    v = P.rule7_verdict(_rows("mixed"), _SENSITIVE)
    assert v["works"] is False and "СМЕШАН" in v["text"].upper()


def test_rule7_annulled_when_instrument_blind():
    v = P.rule7_verdict(_rows("english"), _BLIND)
    assert v["works"] is None and "АННУЛИР" in v["text"].upper()


def test_rule7_verdict_text_is_russian():
    assert P.cyrillic_share(P.rule7_verdict(_rows("russian"), _SENSITIVE)["text"]) > 0.5


# --- ключ не утекает ---------------------------------------------------------
# ГЕРМЕТИЧНО: загрузчик НИ РАЗУ не читает настоящий .env. Наивная версия этих тестов
# (просто вызвать _load_key_from_dotenv()) затаскивала боевой ключ в os.environ на весь
# прогон pytest; вместе с LLM_BACKEND=openrouter, который течёт из соседнего теста,
# llm_local.generate переставал попадать в мок _raw_generate и УХОДИЛ В СЕТЬ — офлайн-инвариант
# рушился, а tests/test_synth_eval.py падал на пустом captured["prompt"]. Env правим только
# через monkeypatch: он откатывает.

def test_dotenv_loader_prefers_env_and_returns_only_bool(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "_SCRIPTS", str(tmp_path))   # настоящий .env недосягаем
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    assert P._load_key_from_dotenv() is True


def test_dotenv_loader_reads_key_from_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text('OPENROUTER_API_KEY="sk-fake-not-real"\n', encoding="utf-8")
    (tmp_path / "scripts").mkdir()   # ".." резолвится ОС — без реального каталога пути нет
    monkeypatch.setattr(P, "_SCRIPTS", str(tmp_path / "scripts"))
    assert P._load_key_from_dotenv() is True
    assert os.environ["OPENROUTER_API_KEY"] == "sk-fake-not-real"


def test_dotenv_loader_false_when_no_key_anywhere(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(P, "_SCRIPTS", str(tmp_path / "scripts"))
    assert P._load_key_from_dotenv() is False


def test_probe_never_prints_key_value():
    # Ключ не печатается: в модуле нет ни одного print с самим значением.
    src = open(P.__file__, encoding="utf-8").read()
    assert "OPENROUTER_API_KEY" in src
    assert not re.search(r"print\([^)]*getenv\(['\"]OPENROUTER_API_KEY", src)


# --- CLI ---------------------------------------------------------------------

def test_dry_run_exits_clean_without_network(capsys):
    assert P.main([]) == 0
    assert "--run" in capsys.readouterr().out
