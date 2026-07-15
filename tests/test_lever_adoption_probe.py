"""A/B на АДОПЦИЮ рычага near-verbatim — офлайн-тесты чистых функций.

Зачем. Слой 2 доказан наполовину: измерено, что near-verbatim-запросы достают ВПЯТЕРО лучше
(d2b4ab3), НО не измерено, станет ли хост следовать подсказке. Прецедент проекта злой:
анти-сикофантика (22fb587) — мягкий prompt-нудж дал ЧИСТЫЙ НОЛЬ (bootstrap-CI включал 0 по
всем 3 осям, n=24), вывод был «рычаг = детерминированный тул, НЕ текст». Пока адопция не
измерена, «внедрено» — вера, а не факт.

Дизайн. Плечи отличаются РОВНО одним абзацем (рычаг). Модель по вопросу юзера формулирует
запросы к cite; мы их прогоняем через ретрив и меряем, доехал ли ИЗВЕСТНЫЙ якорь. Парно по
вопросу → bootstrap-CI на дельте (DRY из antisycophancy_probe).

Конфаунд, который обязан быть снят. Знаменитые якоря («safer to be feared than loved») модель
знает НАИЗУСТЬ → на них рычаг «сформулируй как цитата» победит за счёт эрудиции, а не за счёт
подсказки. Поэтому два сеттинга: hand_ru (знаменитые, RU-вопрос) и auto_abstract (безвестные
заголовки глав Discourses — не вспомнить). Расхождение между сеттингами = мера конфаунда.

Требование Ильи (2026-07-15): «нужны тесты на неизвестных советников, чтобы не было попыток
фальсификации через эрудицию обучающей выборки». Труъ-неизвестного PD-советника не бывает — весь
Gutenberg в обучающей выборке. Поэтому контаминацию не гадаем по «знаменитый/безвестный», а
МЕРЯЕМ поимённо: закрытая книга (без корпуса) — выдаёт модель якорь или нет. Дальше эффект
плеча стратифицируем по измеренному факту. Знание — не бинарное свойство советника, а свойство
конкретного пассажа.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts", "experiments"))

import lever_adoption_probe as P  # noqa: E402


# --- плечи различаются ТОЛЬКО рычагом ---

def test_arms_differ_only_by_the_lever():
    base = P.build_prompt("Как удержать власть?", lever=False)
    lever = P.build_prompt("Как удержать власть?", lever=True)
    assert base != lever
    assert P.LEVER_TEXT in lever and P.LEVER_TEXT not in base
    # Удалив строку рычага (вместе с её переводом строки) из плеча B, обязаны получить РОВНО
    # плечо A — иначе плечи различаются чем-то ещё, и мы померим не рычаг.
    assert lever.replace(P.LEVER_TEXT + "\n", "") == base


def test_both_arms_ask_for_corpus_language():
    """Язык корпуса — уже валидированный лифт, он в ОБОИХ плечах: иначе померим его, не рычаг."""
    for lever in (False, True):
        assert "english" in P.build_prompt("q", lever=lever).lower()


def test_prompt_never_leaks_the_anchor():
    """Утечка якоря в промпт = модель его перепишет, и замер станет тавтологией."""
    p = P.build_prompt("Что надёжнее — чтобы боялись или любили?", lever=True)
    assert "safer to be feared" not in p.lower()


# --- третье плечо: HyDE ---

ITEM = {"id": "x", "advisor": "machiavelli", "setting": "hand_ru",
        "question": "Что надёжнее — чтобы боялись или любили?", "anchor": "safer to be feared"}


def test_build_arm_prompt_dispatches_all_three_arms():
    prompts = {arm: P.build_arm_prompt(ITEM, arm) for arm in P.ARMS}
    assert len(set(prompts.values())) == 3, "плечи обязаны различаться"
    assert P.LEVER_TEXT in prompts["lever"] and P.LEVER_TEXT not in prompts["base"]


def test_unknown_arm_raises_not_silently_falls_back_to_base():
    """Опечатка в имени плеча обязана падать: молчаливый фолбэк на базу = два одинаковых
    плеча и «ноль» в отчёте, которого на самом деле не мерили."""
    try:
        P.build_arm_prompt(ITEM, "levr")
    except ValueError:
        return
    raise AssertionError("неизвестное плечо обязано бросать ValueError")


def test_hyde_asks_to_invent_never_to_recall():
    """Суть HyDE: сочинить правдоподобное, а НЕ вспомнить точное. Иначе это опять эрудиция."""
    p = P.build_hyde_prompt(ITEM["question"], "machiavelli").lower()
    assert "сочини" in p
    assert "не пытайся вспомнить" in p


def test_hyde_names_the_advisor_not_the_slug():
    assert "Machiavelli" in P.build_hyde_prompt("q", "machiavelli")


def test_hyde_prompt_never_leaks_the_anchor():
    p = P.build_hyde_prompt(ITEM["question"], "machiavelli")
    assert "safer to be feared" not in p.lower()


def test_all_arms_ask_for_english():
    """Язык корпуса валидирован ранее и обязан быть во ВСЕХ плечах: иначе HyDE выиграет за
    счёт языка, а не за счёт стиля."""
    for arm in P.ARMS:
        assert "english" in P.build_arm_prompt(ITEM, arm).lower()


# --- контаминация: меряем, а не гадаем ---

def test_closed_book_prompt_permits_honest_empty():
    """Если модель обязана что-то выдать — она сочинит, и мы намеряем контаминацию там, где
    её нет. Пустой ответ должен быть разрешён явно."""
    p = P.build_closed_book_prompt("q", "machiavelli").lower()
    assert "пустой список" in p and "не сочиняй" in p


def test_closed_book_prompt_never_leaks_the_anchor():
    """Главный тест контаминации: подсунешь якорь — модель его повторит, и ВСЁ окажется
    «зазубренным». Замер обязан идти вслепую."""
    p = P.build_closed_book_prompt(ITEM["question"], "machiavelli")
    assert "safer to be feared" not in p.lower()


def test_is_memorized_true_when_model_reproduces_anchor_without_corpus():
    assert P.is_memorized(["It is much safer to be feared than loved."],
                          "safer to be feared") is True


def test_is_memorized_false_when_model_confabulates_plausible_prose():
    assert P.is_memorized(["A prince must rule by strength and awe."],
                          "safer to be feared") is False


def test_is_memorized_false_on_empty_or_none():
    assert P.is_memorized([], "safer to be feared") is False
    assert P.is_memorized(None, "safer to be feared") is False


# --- язык корпуса и приватные советники ---

def test_corpus_language_is_parameterized_in_every_arm():
    """Корпус бывает не английский (частные советники — русские). Захардкоженный English
    заставит хост искать по-английски в русском корпусе — померим язык, а не механизм."""
    for arm in P.ARMS:
        p = P.build_arm_prompt({**ITEM, "lang": "Russian"}, arm)
        assert "Russian" in p and "English" not in p


def test_corpus_language_defaults_to_english():
    assert "English" in P.build_arm_prompt(ITEM, "base")


def test_advisor_names_can_come_from_env_without_touching_the_repo(monkeypatch):
    """ПРИВАТНОСТЬ: имена частных советников НЕ должны попадать в код — файл коммитится.
    Мост через env: имя живёт в команде, репозиторий о нём не знает."""
    monkeypatch.setenv("PROBE_ADVISOR_NAMES", '{"private-slug": "Настоящее Имя"}')
    assert "Настоящее Имя" in P.build_hyde_prompt("q", "private-slug")


def test_repo_never_hardcodes_private_advisor_names():
    """Регресс-гард: словарь имён в коде обязан содержать ТОЛЬКО public-domain советников."""
    assert set(P.ADVISOR_NAMES) == {"machiavelli", "marcus-aurelius", "sun-tzu"}


def test_controls_live_outside_our_corpora():
    """Прибор обязан проверяться на текстах, которых нет в наших корпусах: иначе позитивный
    контроль меряет тот же предмет, что и замер, и ничего не доказывает."""
    slugs = set(P.ADVISOR_NAMES) | set(P.ADVISOR_NAMES.values())
    for c in P.MEMORIZATION_CONTROLS:
        assert c["advisor"] not in slugs


def test_control_prompts_never_leak_their_anchor():
    """Тот же закон, что и для замера: подсунешь строку — модель её повторит, и прибор
    покажет 100% чувствительность, которой нет."""
    for c in P.MEMORIZATION_CONTROLS:
        p = P.build_closed_book_prompt(c["question"], c["advisor"]).lower()
        assert c["anchor"].lower() not in p


def test_calibration_flags_blind_instrument_when_nothing_recalled():
    """Ноль срабатываний на заведомо зазубренном = прибор слеп. Тогда ВСЕ «fresh» — мусор,
    и страты трактовать нельзя. Это обязано кричать, а не молчать."""
    v = P.calibration_verdict([False, False, False, False, False])
    assert v["sensitive"] is False
    assert "слеп" in v["text"].lower()


def test_calibration_confirms_instrument_when_most_recalled():
    v = P.calibration_verdict([True, True, True, True, False])
    assert v["sensitive"] is True


def test_calibration_is_undecided_on_partial_recall():
    """Половина — не приговор и не индульгенция: прибор частично чувствителен, вывод
    ослаблен, но не аннулирован."""
    assert P.calibration_verdict([True, False, False, False])["sensitive"] is None


def test_stratify_splits_effect_by_measured_memorization():
    """Ради этого всё и делалось: лифт на зазубренных пунктах — эрудиция, на незазубренных —
    механизм. Смешивать их в одно число = скрыть конфаунд."""
    base = [{"id": "a", "anchor_rank": None}, {"id": "b", "anchor_rank": None},
            {"id": "c", "anchor_rank": None}, {"id": "d", "anchor_rank": None}]
    treat = [{"id": "a", "anchor_rank": 1}, {"id": "b", "anchor_rank": 1},
             {"id": "c", "anchor_rank": None}, {"id": "d", "anchor_rank": None}]
    memo = {"a": True, "b": True, "c": False, "d": False}
    s = P.stratify(base, treat, memo, k=8)
    assert s["memorized"]["ci"]["mean"] == 1.0, "весь лифт сел на зазубренные"
    assert s["fresh"]["ci"]["mean"] == 0.0, "на незазубренных механизма нет"


def test_stratify_drops_items_with_unmeasured_memorization():
    """Закрытая книга упала (withheld) → memo[id] is None → пункт не приписываем ни к одной
    страте: иначе сеть решает, что считать эрудицией."""
    base = [{"id": "a", "anchor_rank": None}, {"id": "b", "anchor_rank": None}]
    treat = [{"id": "a", "anchor_rank": 1}, {"id": "b", "anchor_rank": 1}]
    s = P.stratify(base, treat, {"a": True, "b": None}, k=8)
    assert s["memorized"]["n_paired"] == 1 and s["fresh"]["n_paired"] == 0


# --- парсинг ответа модели ---

def test_parse_queries_from_json():
    assert P.parse_queries('{"queries": ["a", "b"]}') == ["a", "b"]


def test_parse_queries_tolerates_fenced_json():
    assert P.parse_queries('```json\n{"queries": ["a"]}\n```') == ["a"]


def test_parse_queries_returns_empty_on_garbage_not_crash():
    """Модель вернула мусор → withheld, а не падение платного прогона."""
    assert P.parse_queries("извини, не могу") == []
    assert P.parse_queries(None) == []


def test_parse_queries_drops_empties_and_caps():
    out = P.parse_queries('{"queries": ["a", "", "  ", "b", "c", "d", "e"]}')
    assert "" not in out and len(out) <= P.MAX_QUERIES


# --- пул как в cite: мульти-запрос, дедуп по тексту, по убыванию скора ---

def test_pool_dedups_and_sorts_like_cite():
    hits = {"q1": [{"text": "A", "score": 0.5, "tier": "P1"},
                   {"text": "B", "score": 0.9, "tier": "S1"}],
            "q2": [{"text": "A", "score": 0.7, "tier": "P1"}]}
    pool = P.pool_hits(["q1", "q2"], lambda q, k: hits[q], k=8)
    assert [h["text"] for h in pool] == ["B", "A"]
    assert len(pool) == 2, "дубль по тексту обязан схлопнуться, как в cite"


def test_pool_keeps_best_score_for_duplicate():
    hits = {"q1": [{"text": "A", "score": 0.5, "tier": "P1"}],
            "q2": [{"text": "A", "score": 0.7, "tier": "P1"}]}
    assert P.pool_hits(["q1", "q2"], lambda q, k: hits[q], k=8)[0]["score"] == 0.7


def test_empty_queries_give_empty_pool_not_crash():
    assert P.pool_hits([], lambda q, k: [], k=8) == []


# --- сводка и вердикт ---

def test_summarize_arm_reports_hit_rate_and_mrr():
    rows = [{"id": "1", "anchor_rank": 1}, {"id": "2", "anchor_rank": None},
            {"id": "3", "anchor_rank": 2}]
    s = P.summarize_arm(rows, k=8)
    assert s["n"] == 3 and abs(s["anchor_hit"] - 2 / 3) < 1e-9
    assert abs(s["anchor_mrr"] - (1 + 0 + 0.5) / 3) < 1e-9


def test_verdict_calls_zero_when_ci_spans_zero():
    """Урок анти-сикофантики: CI, накрывающий 0, — это НОЛЬ, а не «тенденция к росту»."""
    v = P.verdict({"lo": -0.12, "hi": 0.20, "mean": 0.04}, n=24)
    assert v["adopted"] is False
    assert "ноль" in v["text"].lower() or "не отличим" in v["text"].lower()


def test_verdict_confirms_only_when_ci_excludes_zero():
    v = P.verdict({"lo": 0.05, "hi": 0.31, "mean": 0.18}, n=24)
    assert v["adopted"] is True


def test_verdict_refuses_on_tiny_n():
    assert P.verdict({"lo": 0.1, "hi": 0.9, "mean": 0.5}, n=3)["adopted"] is None


def test_withheld_rows_are_excluded_not_counted_as_failure():
    """Упавший вызов ≠ «рычаг не сработал». Иначе сеть портит вывод в пользу нуля."""
    rows = [{"id": "1", "anchor_rank": 1}, {"id": "2", "anchor_rank": None, "withheld": True}]
    s = P.summarize_arm(rows, k=8)
    assert s["n"] == 1 and s["withheld"] == 1
