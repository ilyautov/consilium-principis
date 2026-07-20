#!/usr/bin/env python3
"""Calibrated Consult — анти-оверрелайанс ИНСТРУМЕНТ (спека 2026-07-18-calibrated-consult-design).

Делает оверрелайанс ЧЕЛОВЕКА видимым (ров бьёт ложь МОДЕЛИ, не оверрелайанс ЧЕЛОВЕКА —
arXiv 2607.13562). Цикл: open фиксирует ПРИОР (твоя позиция+уверенность ДО совета) → совет →
close фиксирует ПОСТЕРИОР и считает ЗЕРКАЛО (сдвиг + инфляция уверенности) → resolve кладёт
исход → калибровка. НЕ заявляет «снижает оверрелайанс» (недоказуемо оффлайн) — только видит.

Дисциплина (как decision_card): fail-closed, RU-ошибки аккумулируются (не первая), ноль
LLM/сети, числа через тот же _is_number. Реюз decision_card (ULID, prediction/outcome гейты)
и prediction_calibration (Brier) — без дублирования.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decision_map import _is_number, _nonempty_str
from decision_card import (_ulid, _CROCKFORD, _parse_date, validate_prediction,
                           validate_outcome)

SCHEMA_VERSION = "1.0.0"
KIND_CONSULT = "calibrated_consult"
_ID_PREFIX = "cc_"


def new_consult_id():
    """Стабильный ключ: cc_ + ULID (сортируется по времени). Реюз decision_card._ulid."""
    return _ID_PREFIX + _ulid()


def _valid_confidence(x):
    """Конечное число в [0,1] (не bool — bool пролез бы как 0/1)."""
    return _is_number(x) and not isinstance(x, bool) and 0.0 <= x <= 1.0


def _validate_prior(prior, errors, label="приор"):
    """Гейты одной стороны (prior/posterior): call непустой, confidence∈[0,1], abstain bool."""
    if not isinstance(prior, dict):
        errors.append("Сторона «%s» должна быть объектом {call, confidence, abstain}." % label)
        return
    if not _nonempty_str(prior.get("call")):
        errors.append("У «%s» пустая позиция (call) — зафиксируй СВОЙ ответ словами." % label)
    if not _valid_confidence(prior.get("confidence")):
        errors.append("У «%s» уверенность (confidence) — конечное число 0..1; сейчас: %r."
                      % (label, prior.get("confidence")))
    if not isinstance(prior.get("abstain"), bool):
        errors.append("У «%s» воздержание (abstain) — true|false (сказал бы «не знаю»?); "
                      "сейчас: %r." % (label, prior.get("abstain")))


def validate_consult(consult):
    """Fail-closed валидация записи консульта → список RU-ошибок ([] = валидна)."""
    if not isinstance(consult, dict):
        return ["Calibrated Consult должен быть JSON-объектом — получено: %s."
                % type(consult).__name__]
    errors = []
    if not _nonempty_str(consult.get("schema_version")):
        errors.append("У консульта нет версии схемы (schema_version).")
    cid = consult.get("id")
    if not _nonempty_str(cid) or not (cid.startswith(_ID_PREFIX)
                                      and cid[len(_ID_PREFIX):].isalnum()):
        errors.append("У консульта нет валидного id вида cc_<буквы/цифры> — сейчас: %r." % (cid,))
    if _parse_date(consult.get("created")) is None:
        errors.append("У консульта нет валидной даты создания (created, ISO YYYY-MM-DD).")
    if consult.get("kind") != KIND_CONSULT:
        errors.append("У консульта поле kind должно быть \"calibrated_consult\" — сейчас: %r."
                      % (consult.get("kind"),))
    if not _nonempty_str(consult.get("question")):
        errors.append("У консульта нет вопроса (question) — что несёшь совету.")
    _validate_prior(consult.get("prior"), errors, "приор")
    posterior = consult.get("posterior")
    if posterior is not None:
        _validate_prior(posterior, errors, "постериор")
        if isinstance(posterior, dict) and not isinstance(posterior.get("followed_council"), bool):
            errors.append("У постериора followed_council — true|false (принял ли позицию совета).")
    prediction = consult.get("prediction")
    if prediction is not None:
        validate_prediction(prediction, errors)
    outcome = consult.get("outcome")
    if outcome is not None:
        validate_outcome(outcome, prediction if isinstance(prediction, dict) else {},
                         created=consult.get("created"), errors=errors)
    return errors


import time


def build_consult(question, prior_call, prior_confidence, prior_abstain=False,
                  created=None, consult_id=None):
    """Чистый конструктор записи (без валидации — её делает handler через validate_consult).
    created=None → сегодня (локальное время). id=None → новый cc_ULID."""
    if created is None:
        created = time.strftime("%Y-%m-%d")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": consult_id or new_consult_id(),
        "created": created,
        "kind": KIND_CONSULT,
        "question": question,
        "prior": {"call": prior_call, "confidence": prior_confidence,
                  "abstain": bool(prior_abstain)},
        "posterior": None,
        "mirror": None,
        "prediction": None,
        "outcome": None,
        "decision_card_ref": None,
    }


def _norm_call(s):
    """Нормализация позиции для сравнения сдвига: lower + схлопнуть пробелы. Не показывается."""
    return " ".join(str(s or "").lower().split())


def compute_mirror(prior, posterior):
    """Зеркало на close: сдвиг позиции + инфляция уверенности + подавление воздержания.
    НЕ выносит вердикт «оверрелайанс» (сдвиг может быть честной коррекцией) — только факт."""
    delta = float(posterior.get("confidence", 0.0)) - float(prior.get("confidence", 0.0))
    return {
        "confidence_delta": delta,
        "shifted": _norm_call(prior.get("call")) != _norm_call(posterior.get("call")),
        "abstention_dropped": bool(prior.get("abstain")) and not bool(posterior.get("abstain")),
    }


def close_consult(consult, posterior_call, posterior_confidence, posterior_abstain,
                  followed_council, prediction=None):
    """Проставить posterior+mirror(+prediction) в КОПИЮ записи, fail-closed.

    Невалидный постериор/прогноз или уже закрытый консульт → ValueError с RU-текстом,
    никакой частичной записи (зеркало decision_card.close_card)."""
    if not isinstance(consult, dict):
        raise ValueError("Консульт для закрытия должен быть объектом.")
    if consult.get("posterior") is not None:
        raise ValueError("Консульт уже закрыт (posterior заполнен) — повторно не закрываем.")
    if not isinstance(consult.get("prior"), dict):
        raise ValueError("У консульта нет приора (prior) — зеркало не с чем считать.")
    posterior = {"call": posterior_call, "confidence": posterior_confidence,
                 "abstain": bool(posterior_abstain), "followed_council": bool(followed_council)}
    errors = []
    _validate_prior(posterior, errors, "постериор")
    if prediction is not None:
        validate_prediction(prediction, errors)
    if errors:
        raise ValueError("Закрытие не проходит гейты (fail-closed):\n- " + "\n- ".join(errors))
    closed = dict(consult)
    closed["posterior"] = posterior
    closed["mirror"] = compute_mirror(consult.get("prior"), posterior)
    if prediction is not None:
        closed["prediction"] = dict(prediction)
    return closed


def resolve_consult(consult, outcome):
    """Проставить outcome в КОПИЮ (fail-closed), провалидировав по прогнозу — зеркало
    decision_card.close_card. Без prediction резолвить нечего → ValueError."""
    if not isinstance(consult, dict):
        raise ValueError("Консульт для резолва должен быть объектом.")
    prediction = consult.get("prediction")
    if not isinstance(prediction, dict):
        raise ValueError("У консульта нет прогноза (prediction) — резолвить исход не с чем.")
    errs = validate_outcome(outcome, prediction, created=consult.get("created"))
    if errs:
        raise ValueError("Исход не проходит гейты (fail-closed):\n- " + "\n- ".join(errs))
    resolved = dict(consult)
    resolved["outcome"] = dict(outcome)
    return resolved


import prediction_calibration as _pc


def _is_closed(c):
    return isinstance(c, dict) and isinstance(c.get("posterior"), dict) \
        and isinstance(c.get("mirror"), dict)


def overreliance_journal(consults, min_n=_pc.MIN_TRUSTWORTHY_N):
    """Сводка оси оверрелайанса (реюз prediction_calibration.brier — БЕЗ дублирования).

    Немедленные сигналы (нужен лишь mirror, без исхода):
      • confidence_inflation = mean(mirror.confidence_delta) по закрытым (arXiv: уверенность
        почти удваивалась);
      • abstention_suppressed = count(mirror.abstention_dropped) — ядро находки arXiv.
    Отложенный сигнал (нужен исход): bad-follow как ПАРТИЦИЯ калибровки — Brier по
    resolved-консультам с followed_council=true против false. Хуже у followed → оверрелайанс.
    (Литеральное «приор набрал бы лучше» из спеки §4.2 требует прогноза на стороне ПРИОРА,
    которого v1 не хранит — YAGNI; партиция реализует ту же интенцию.)"""
    closed = [c for c in (consults or []) if _is_closed(c)]
    n = len(closed)
    inflation = (math.fsum(c["mirror"]["confidence_delta"] for c in closed) / n) if n else None
    suppressed = sum(1 for c in closed if c["mirror"].get("abstention_dropped"))
    followed = [c for c in closed if c["posterior"].get("followed_council")]
    independent = [c for c in closed if not c["posterior"].get("followed_council")]
    return {
        "n_closed": n,
        "trustworthy": n >= min_n,
        "confidence_inflation": inflation,
        "abstention_suppressed": suppressed,
        # реюз чистой математики: brier() читает записи с prediction+outcome (у нас они top-level)
        "followed": _pc.brier(followed),
        "independent": _pc.brier(independent),
    }
