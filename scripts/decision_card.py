#!/usr/bin/env python3
"""Decision Card — единственный персистентный узел жизненного цикла решения.

Спека: docs/superpowers/specs/2026-07-18-decision-lifecycle-proposal.md (§2).

Три сущности (карта решения / протокол заседания / петля исхода) раньше держались на
совпадении заголовков и парсинге прозы. Card сшивает их UUID'ом (dc_…): несёт версию
схемы, владельца, дату ревью, ссылки на map/session/situation, выбранный вариант,
допущения, критерий успеха, prediction contract (числа — из mc_run, ХРАНЯТСЯ ЧИСЛАМИ,
не RU-строкой) и, при закрытии, outcome (occurred/actual в тех же единицах).

Дисциплина модуля (тот же принцип, что decision_map.validate_map):
  • fail-closed: validate_card аккумулирует ВСЕ ошибки RU-строками (не первую) — host
    доносит их до юзера как вопросы совета, не как стектрейс;
  • ноль LLM, ноль сети — чистые функции от распарсенных данных;
  • числа проверяются тем же _is_number, что карта (конечные, не bool, не inf/nan).

Развилки спеки (§4), принятые при имплементации:
  • A1 — Card = отдельный decisions/*.card.json (карта неизменна, чистое разделение).
  • C1 — reversibility несёт Card (не decision_map, чтобы не менять validate_map);
    поле опциональное, валидируется по значению one-way|two-way, если задано.
  • D  — prediction contract двувариантен (event ИЛИ metric); build_prediction_from_mc
    по умолчанию строит metric, когда у ставки есть единицы (интервал информативнее
    бинарного Brier при N=1), иначе event.
"""
import datetime
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decision_map import _is_number, _nonempty_str  # те же числовые/строковые гейты

# ── константы схемы ─────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0.0"
KIND_CARD = "decision_card"

PRED_EVENT = "event"
PRED_METRIC = "metric"
PRED_KINDS = {PRED_EVENT, PRED_METRIC}

DIRECTION_MAX = "max"
DIRECTION_MIN = "min"
DIRECTIONS = {DIRECTION_MAX, DIRECTION_MIN}

REVERSIBILITY = {"one-way", "two-way"}

_ID_PREFIX = "dc_"
# Crockford base32 (без I L O U — не путаются при чтении); алфавит ULID.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid():
    """26-символьный ULID: 48-бит мс-таймстамп (старшие 10 симв.) + 80-бит случайность
    (младшие 16). Лексикографически сортируется по времени создания. Stdlib, без зависимостей.
    Только 0-9A-Z → проходит и isalnum(), и ^[A-Za-z0-9]+$."""
    ts = int(time.time() * 1000) & ((1 << 48) - 1)
    val = (ts << 80) | secrets.randbits(80)                 # 128 бит
    return "".join(_CROCKFORD[(val >> (5 * (25 - i))) & 0x1F] for i in range(26))


def new_card_id():
    """Стабильный ключ сшивания: dc_ + ULID (stdlib, без внешних зависимостей).

    Открытый вопрос спеки §8.1 (ULID vs uuid4) решён владельцем в пользу ULID: id
    лексикографически сортируется по времени создания (удобно для листингов/журналов),
    формат по-прежнему матчит ^dc_[A-Za-z0-9]+$ → старые dc_<hex>-карты остаются валидны."""
    return _ID_PREFIX + _ulid()


def _parse_date(v):
    """ISO-дата 'YYYY-MM-DD' → datetime.date | None (кривой вход → None, не исключение)."""
    if not isinstance(v, str):
        return None
    try:
        return datetime.date.fromisoformat(v)
    except ValueError:
        return None


# ── prediction contract (§2.2) ──────────────────────────────────────────────

def validate_prediction(pred, errors=None):
    """Гейты прогноза (fail-closed). errors=None → вернуть свой список; иначе дописать в чужой."""
    own = errors is None
    errors = [] if own else errors
    if not isinstance(pred, dict):
        errors.append("Прогноз (prediction) должен быть объектом — совет объявляет, ЧТО меряем.")
        return errors if own else None

    kind = pred.get("kind")
    if kind not in PRED_KINDS:
        errors.append("У прогноза вид (kind) должен быть event (вероятность события) или "
                      "metric (числовой интервал p10/p50/p90) — сейчас: %r." % (kind,))
    if not _nonempty_str(pred.get("statement")):
        errors.append("У прогноза нет формулировки (statement) — юзер визирует ИМЕННО её "
                      "(что считаем «сработало»).")
    hd = pred.get("horizon_days")
    if not isinstance(hd, int) or isinstance(hd, bool) or hd <= 0:
        errors.append("Горизонт прогноза (horizon_days) — целое число дней > 0; сейчас: %r." % (hd,))

    if kind == PRED_EVENT:
        prob = pred.get("probability")
        if not _is_number(prob) or not (0.0 <= prob <= 1.0):
            errors.append("У события вероятность (probability) должна быть конечным числом "
                          "от 0 до 1 — сейчас: %r." % (prob,))
    elif kind == PRED_METRIC:
        p10, p50, p90 = pred.get("p10"), pred.get("p50"), pred.get("p90")
        if not (_is_number(p10) and _is_number(p50) and _is_number(p90)):
            errors.append("У величины нужны конечные числовые перцентили p10/p50/p90 — "
                          "сейчас: p10=%r, p50=%r, p90=%r." % (p10, p50, p90))
        elif not (p10 <= p50 <= p90):
            errors.append("У величины нарушен порядок перцентилей p10 <= p50 <= p90 "
                          "(p10=%s, p50=%s, p90=%s)." % (p10, p50, p90))
        if not _nonempty_str(pred.get("unit")):
            errors.append("У величины не заданы единицы (unit) — без них факт не сопоставить "
                          "с прогнозом (числовой разрыв §1.2).")
        if pred.get("direction") not in DIRECTIONS:
            errors.append("У величины направление (direction) должно быть max или min — "
                          "сейчас: %r." % (pred.get("direction"),))

    ro = pred.get("resolves_on")
    if ro is not None and _parse_date(ro) is None:
        errors.append("Дата разрешения прогноза (resolves_on) должна быть ISO-датой "
                      "YYYY-MM-DD — сейчас: %r." % (ro,))
    return errors if own else None


# ── outcome (§2.3) ──────────────────────────────────────────────────────────

def validate_outcome(outcome, prediction, created=None, errors=None):
    """Гейты исхода при закрытии: occurred(bool) для event / actual(число) для metric,
    в тех же единицах; resolved_on >= created; endorsed bool|null."""
    own = errors is None
    errors = [] if own else errors
    if not isinstance(outcome, dict):
        errors.append("Исход (outcome) должен быть объектом с фактом закрытия.")
        return errors if own else None

    ro = _parse_date(outcome.get("resolved_on"))
    if ro is None:
        errors.append("У исхода нет валидной даты закрытия (resolved_on, ISO YYYY-MM-DD).")
    elif created is not None:
        cd = _parse_date(created)
        if cd is not None and ro < cd:
            errors.append("Дата закрытия исхода (resolved_on) раньше даты создания карты — "
                          "исход не может лечь до решения.")

    kind = prediction.get("kind") if isinstance(prediction, dict) else None
    if kind == PRED_EVENT:
        if not isinstance(outcome.get("occurred"), bool):
            errors.append("У события в исходе нужен occurred: true|false (случилось ли) — "
                          "сейчас: %r." % (outcome.get("occurred"),))
    elif kind == PRED_METRIC:
        if not _is_number(outcome.get("actual")):
            errors.append("У величины в исходе нужно фактическое число actual в тех же "
                          "единицах, что прогноз — сейчас: %r." % (outcome.get("actual"),))

    endorsed = outcome.get("endorsed")
    if endorsed is not None and not isinstance(endorsed, bool):
        errors.append("Поле endorsed (одобрил ли юзер исход задним числом) — true|false|null.")
    return errors if own else None


# ── Card (§2.1) ─────────────────────────────────────────────────────────────

def validate_card(card, map=None):
    """Fail-closed валидация Card → список RU-ошибок ([] = валидна). Ошибки аккумулируются.

    map (опц.) — decision_map: если задан, chosen_option обязан быть id одного из
    map.options ЛИБО None (явный defer). Без map проверяется лишь тип chosen_option.
    """
    if not isinstance(card, dict):
        return ["Decision Card должна быть JSON-объектом — получено: %s." % type(card).__name__]

    errors = []

    if not _nonempty_str(card.get("schema_version")):
        errors.append("У Card нет версии схемы (schema_version) — она читается при загрузке.")

    cid = card.get("id")
    if not _nonempty_str(cid) or not (cid.startswith(_ID_PREFIX)
                                      and cid[len(_ID_PREFIX):].isalnum()):
        errors.append("У Card нет валидного id вида dc_<буквы/цифры> (стабильный ключ "
                      "сшивания) — сейчас: %r." % (cid,))

    if _parse_date(card.get("created")) is None:
        errors.append("У Card нет валидной даты создания (created, ISO YYYY-MM-DD).")

    if card.get("kind") != KIND_CARD:
        errors.append("У Card поле kind должно быть \"decision_card\" — сейчас: %r."
                      % (card.get("kind"),))

    if not _nonempty_str(card.get("owner")):
        errors.append("У Card нет владельца решения (owner) — по умолчанию \"self\".")

    # chosen_option: None = явный defer; иначе непустая строка (и из options, если есть map)
    chosen = card.get("chosen_option")
    if chosen is not None:
        if not _nonempty_str(chosen):
            errors.append("Выбранный вариант (chosen_option) — либо id из вариантов карты, "
                          "либо null (явный defer); пустая строка не принимается (fail-closed).")
        elif isinstance(map, dict):
            opt_ids = {o.get("id") for o in map.get("options", []) if isinstance(o, dict)}
            if chosen not in opt_ids:
                errors.append("Выбранный вариант «%s» не найден среди вариантов карты — "
                              "chosen_option должен быть id из map.options." % chosen)

    # review_date: валидная ISO-дата, не раньше created
    rd = _parse_date(card.get("review_date"))
    if rd is None:
        errors.append("У Card нет валидной даты ревью (review_date, ISO YYYY-MM-DD) — "
                      "когда вернуться и закрыть исход.")
    else:
        cd = _parse_date(card.get("created"))
        if cd is not None and rd < cd:
            errors.append("Дата ревью (review_date) раньше даты создания — ревью не может "
                          "быть в прошлом относительно решения.")

    rev = card.get("reversibility")
    if rev is not None and rev not in REVERSIBILITY:
        errors.append("Обратимость (reversibility) — one-way или two-way, если задана; "
                      "сейчас: %r." % (rev,))

    links = card.get("links")
    if links is not None and not isinstance(links, dict):
        errors.append("Ссылки (links) должны быть объектом {map_path, session_id, situation_ref}.")

    prediction = card.get("prediction")
    validate_prediction(prediction, errors)

    outcome = card.get("outcome")
    if outcome is not None:
        validate_outcome(outcome, prediction if isinstance(prediction, dict) else {},
                         created=card.get("created"), errors=errors)

    return errors


# ── построение прогноза из mc_run (§2.2, закрывает числовой разрыв §1.2) ──────

def build_prediction_from_mc(map, mc_result, chosen, form=None, horizon_days=None,
                             created=None, statement=None, pred_id=None):
    """Числа прогноза берутся ПРЯМО из mc_run (mc_run.py:181-186) и хранятся ЧИСЛАМИ.

    form: "event" | "metric" | None. None → metric, когда у stakes есть единицы (D-развилка:
    интервал информативнее бинарного Brier при N=1), иначе event.
      • event  — probability ← p_best[chosen] («выбранный вариант окажется лучшим»);
      • metric — p10/p50/p90 ← options[chosen].{p10,median,p90}; unit ← stakes.metric;
        direction ← stakes.direction.
    resolves_on выводится из created + horizon_days, если created — ISO-дата. Fail-closed:
    неизвестный вариант / кривой mc_result → ValueError; horizon_days обязателен
    (целое > 0) — иначе билдер вернул бы прогноз, который отвергает validate_prediction.
    """
    if not isinstance(mc_result, dict) or "p_best" not in mc_result or "options" not in mc_result:
        raise ValueError("mc_result не похож на результат mc_run (нет p_best/options).")
    if chosen not in mc_result["p_best"] or chosen not in mc_result["options"]:
        raise ValueError("Вариант «%s» отсутствует в результате расчёта — прогноз не собрать."
                         % (chosen,))
    if not isinstance(horizon_days, int) or isinstance(horizon_days, bool) or horizon_days <= 0:
        raise ValueError("Горизонт прогноза (horizon_days) обязателен — целое число дней > 0; "
                         "без горизонта прогноз неразрешим и не пройдёт validate_prediction.")

    stakes = map.get("stakes", {}) if isinstance(map, dict) else {}
    unit = stakes.get("metric")
    if form is None:
        form = PRED_METRIC if _nonempty_str(unit) else PRED_EVENT
    if form not in PRED_KINDS:
        raise ValueError("Неизвестная форма прогноза «%s» (event|metric)." % (form,))

    pid = pred_id or ("pred_%s" % chosen)
    resolves_on = None
    cd = _parse_date(created)
    if cd is not None and isinstance(horizon_days, int) and not isinstance(horizon_days, bool):
        resolves_on = (cd + datetime.timedelta(days=horizon_days)).isoformat()

    if form == PRED_EVENT:
        pred = {"id": pid, "kind": PRED_EVENT,
                "statement": statement or ("вариант «%s» окажется лучшим" % chosen),
                "probability": mc_result["p_best"][chosen],
                "horizon_days": horizon_days}
    else:
        o = mc_result["options"][chosen]
        pred = {"id": pid, "kind": PRED_METRIC,
                "statement": statement or ("исход варианта «%s» (%s)" % (chosen, unit or "метрика")),
                "unit": unit,
                "p10": o["p10"], "p50": o["median"], "p90": o["p90"],
                "direction": stakes.get("direction", DIRECTION_MAX),
                "horizon_days": horizon_days}
    if resolves_on is not None:
        pred["resolves_on"] = resolves_on
    return pred


# ── закрытие Card (open → closed, fail-closed) ───────────────────────────────

def close_card(card, outcome):
    """Проставить outcome в КОПИЮ Card (исходная не мутируется), провалидировав по прогнозу.

    Fail-closed: невалидный исход (occurred не bool / actual не число / чужие единицы /
    дата раньше created) → ValueError с RU-текстом, никакой частичной записи."""
    if not isinstance(card, dict):
        raise ValueError("Card для закрытия должна быть объектом.")
    prediction = card.get("prediction")
    errs = validate_outcome(outcome, prediction if isinstance(prediction, dict) else {},
                            created=card.get("created"))
    if errs:
        raise ValueError("Исход не проходит гейты (fail-closed):\n- " + "\n- ".join(errs))
    closed = dict(card)
    closed["outcome"] = dict(outcome)
    return closed
