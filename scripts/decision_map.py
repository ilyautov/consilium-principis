#!/usr/bin/env python3
"""Карта решения — схема и гейты честности («Principis-расчёт», спека §§1-2).

Сервер — единственный владелец схемы. `validate_map` — fail-closed гейт (тот же
принцип, что no-manifest→A): расчёт (mc_run) отказывается запускаться, пока карта
не проходит ВСЕ гейты. Ошибки — человеческие RU-строки: хост доносит их до юзера
как вопросы совета, а не как стектрейс.

Гейты (спека §2):
  • каждая uncertainty имеет `confirmed_by_user: true` — все числа юзерские;
  • continuous: КОНЕЧНЫЕ числовые min <= mode <= max; event: prob в [0,1]
    (inf/nan — отказ: non-finite магнитуда отравила бы расчёт, review I1);
  • kind только continuous|event (YAGNI: других видов в v1 нет);
  • stakes (metric + direction max|min) и horizon присутствуют;
  • >= 2 options, среди них статус-кво;
  • формула на каждый вариант, парсится безопасным AST (safe_expr), только
    известные id величин — неизвестный id → отказ, не ноль;
  • у каждой формулы есть словесная версия — юзер визировал ИМЕННО её.

Отступления от плоского примера спеки (утверждены при имплементации Ф1):
  • model — per-option объекты {"expr": "...", "words": "..."} вместо плоской
    строки + общего "_описание": словесная версия визируется НА КАЖДУЮ формулу,
    а не одна на всех. Плоская строка отвергается.
  • статус-кво — явный флаг `"status_quo": true` РОВНО на одном варианте
    (не угадывание по имени; два статус-кво — дефект моделирования).
  • дополнительные структурные гейты (следствия fail-closed, в §2 не выписаны):
    uncertainties непусты; id величин и вариантов уникальны и непусты; ключи
    model взаимно-однозначны с id вариантов (лишний ключ — рассинхрон карты);
    confirmed_by_user и status_quo — ТОЛЬКО литеральный true (никакой коэрсии
    строк — «"true"» не подтверждение); bool не считается числом.
  • `elicited` НЕ гейтится кодом: честность цитаты — host-тир (спека §8),
    правило уровня INSTRUCTIONS (Ф2), аудит-механика — кандидат в Ф5+.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from safe_expr import SafeExprError, compile_expr

# ── константы схемы ─────────────────────────────────────────────────────────
KIND_CONTINUOUS = "continuous"
KIND_EVENT = "event"
KINDS = {KIND_CONTINUOUS, KIND_EVENT}

DIRECTION_MAX = "max"
DIRECTION_MIN = "min"
DIRECTIONS = {DIRECTION_MAX, DIRECTION_MIN}

# Ключи модели: формула + словесная версия (юзер визирует именно words)
MODEL_EXPR_KEY = "expr"
MODEL_WORDS_KEY = "words"


def _is_number(v):
    """Число модели: КОНЕЧНЫЙ int/float, НЕ bool (bool — подкласс int, но True — не
    величина). inf/nan и int крупнее float-диапазона отвергаются (review I1):
    non-finite магнитуда в min/mode/max/prob отравила бы «📐 расчёт» — гейт обязан
    донести это вопросом совета, а не глубинный runtime стектрейсом."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    try:
        return math.isfinite(v)
    except OverflowError:
        return False


def _nonempty_str(v):
    return isinstance(v, str) and bool(v.strip())


def _validate_uncertainty(u, idx, errors):
    """Гейты одной величины; возвращает id (или None), чтобы собрать множество имён."""
    label = "величина #%d" % (idx + 1)
    if not isinstance(u, dict):
        errors.append("Каждая величина в uncertainties должна быть объектом — %s не объект." % label)
        return None
    uid = u.get("id")
    if not _nonempty_str(uid):
        errors.append("У величины #%d нет id — совету нужно дать ей имя." % (idx + 1))
        uid = None
    else:
        label = "«%s»" % uid

    if u.get("confirmed_by_user") is not True:
        errors.append(
            "Величина %s не подтверждена юзером (confirmed_by_user) — совет должен "
            "переспросить диапазон и зафиксировать ответ; без подтверждения не считаем." % label)

    kind = u.get("kind")
    if kind not in KINDS:
        errors.append(
            "У величины %s вид «%s» — поддерживаются только continuous "
            "(диапазон min/mode/max) и event (вероятность prob)." % (label, kind))
        return uid

    if kind == KIND_EVENT:
        prob = u.get("prob")
        if not _is_number(prob) or not (0.0 <= prob <= 1.0):
            errors.append(
                "У события %s вероятность prob должна быть конечным числом от 0 до 1 — "
                "сейчас: %r." % (label, prob))
    else:  # continuous
        lo, mode, hi = u.get("min"), u.get("mode"), u.get("max")
        if not (_is_number(lo) and _is_number(mode) and _is_number(hi)):
            errors.append(
                "У величины %s нужны конечные числовые min/mode/max (худший "
                "реалистичный / типичный / лучший) — сейчас: min=%r, mode=%r, max=%r."
                % (label, lo, mode, hi))
        elif not (lo <= mode <= hi):
            errors.append(
                "У величины %s нарушен порядок min <= mode <= max "
                "(min=%s, mode=%s, max=%s) — переспросите тройку у юзера."
                % (label, lo, mode, hi))
    return uid


def _validate_options(m, errors):
    """Гейты вариантов; возвращает список валидных id вариантов."""
    options = m.get("options")
    if not isinstance(options, list) or len(options) < 2:
        errors.append(
            "Нужно минимум два варианта (options), включая статус-кво «ничего не "
            "делать» — совет обязан его выбить.")
        options = options if isinstance(options, list) else []

    ids, status_quo_count = [], 0
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            errors.append("Вариант #%d должен быть объектом с id." % (i + 1))
            continue
        oid = opt.get("id")
        if not _nonempty_str(oid):
            errors.append("У варианта #%d нет id." % (i + 1))
        elif oid in ids:
            errors.append("Id варианта «%s» повторяется — id должны быть уникальны." % oid)
        else:
            ids.append(oid)
        if opt.get("status_quo") is True:
            status_quo_count += 1
        elif "status_quo" in opt and opt.get("status_quo") is not False:
            errors.append(
                "Флаг статус-кво у варианта #%d должен быть литеральным true — "
                "строки не принимаются (fail-closed)." % (i + 1))
    if options and status_quo_count != 1:
        errors.append(
            "Ровно один вариант должен нести флаг статус-кво (\"status_quo\": true) — "
            "сейчас таких: %d. Совет обязан выбить вариант «ничего не делать»."
            % status_quo_count)
    return ids


def _validate_model(m, option_ids, uncertainty_ids, errors):
    """Формула на каждый вариант: {"expr", "words"}, expr парсится, id известны."""
    model = m.get("model")
    if not isinstance(model, dict):
        errors.append(
            "Нет модели (model): на каждый вариант нужна формула — совет предлагает "
            "её словами и выражением, юзер визирует.")
        return

    for oid in option_ids:
        if oid not in model:
            errors.append("У варианта «%s» нет формулы в model — без неё вариант не посчитать." % oid)
    for key in model:
        if key not in option_ids:
            errors.append(
                "Ключ модели «%s» не соответствует ни одному варианту — уберите его "
                "или добавьте вариант (рассинхрон карты)." % key)

    for oid in option_ids:
        entry = model.get(oid)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            errors.append(
                "Формула варианта «%s» должна быть объектом {\"expr\": ..., \"words\": ...} — "
                "выражение плюс словесная версия, которую визировал юзер." % oid)
            continue
        expr = entry.get(MODEL_EXPR_KEY)
        try:
            compile_expr(expr, uncertainty_ids)
        except SafeExprError as e:
            errors.append("Формула варианта «%s» не проходит: %s" % (oid, e))
        if not _nonempty_str(entry.get(MODEL_WORDS_KEY)):
            errors.append(
                "У формулы варианта «%s» нет словесной версии (words) — юзер визирует "
                "ИМЕННО её, без неё не считаем." % oid)


def validate_map(m):
    """Fail-closed валидация карты решения → список RU-ошибок ([] = карта валидна).

    Ошибки аккумулируются (все разом, не первая) — хост задаёт юзеру
    все вопросы совета за один заход.
    """
    if not isinstance(m, dict):
        return ["Карта решения должна быть JSON-объектом — получено: %s."
                % type(m).__name__]

    errors = []

    # величины: непустой список, каждый гейт, уникальные id
    uncertainties = m.get("uncertainties")
    uncertainty_ids = set()
    if not isinstance(uncertainties, list) or not uncertainties:
        errors.append(
            "В карте нет ни одной величины (uncertainties) — расчёту нечего "
            "сэмплировать; совет должен выбить хотя бы одну тройкой "
            "«худший/типичный/лучший» или вероятностью события.")
    else:
        for i, u in enumerate(uncertainties):
            uid = _validate_uncertainty(u, i, errors)
            if uid is not None:
                if uid in uncertainty_ids:
                    errors.append("Id величины «%s» повторяется — id должны быть уникальны." % uid)
                uncertainty_ids.add(uid)

    # варианты и статус-кво
    option_ids = _validate_options(m, errors)

    # stakes + horizon
    stakes = m.get("stakes")
    if not isinstance(stakes, dict):
        errors.append(
            "Нет ставок (stakes): чем меряем исход (metric) и куда лучше "
            "(direction: max|min) — без этого сравнение вариантов не имеет смысла.")
    else:
        if not _nonempty_str(stakes.get("metric")):
            errors.append("В stakes не задана метрика (metric) — в чём меряем исход?")
        if stakes.get("direction") not in DIRECTIONS:
            errors.append(
                "В stakes направление (direction) должно быть max или min — "
                "сейчас: %r." % stakes.get("direction"))
    if not _nonempty_str(m.get("horizon")):
        errors.append("Не задан горизонт (horizon) — на каком сроке оцениваем исход?")

    # модель: формулы + словесные версии
    _validate_model(m, option_ids, uncertainty_ids, errors)

    return errors
