#!/usr/bin/env python3
"""Вердикт совета — детерминированная механика поверх форума (идея — MIT-проект roast-room).

Зачем. Синтез-прозой хост может «сгладить» несогласие: пять голосов спорили, а вывод звучит
как общий кивок. Здесь ПОСЛЕ форума каждый советник сдаёт scorecard (оценки вариантов 0..10,
вес своей линзы для ЭТОГО вопроса, уверенность, риск разорения, дверь one-way/two-way,
что изменит его позицию, вопрос юзеру перед подписью), а метку вердикта считает КОД:
взвешенное среднее → полоса → поправки-потолки (риск разорения, необратимость при расколе),
сигнал единодушия, перевод в ЖДАТЬ. Поправки — код: хост не может их «забыть».

Дисциплина модуля (тот же принцип, что decision_map.validate_map / decision_card):
  • fail-closed: validate_scorecard аккумулирует ВСЕ ошибки RU-строками (не первую) — хост
    доносит их до юзера как вопросы совета, а не как стектрейс;
  • ноль LLM, ноль сети — чистые функции от распарсенных данных;
  • числа — тем же _is_number, что карта (конечные, не bool, не inf/nan);
  • статус-кво — литеральный "status_quo": true РОВНО на одном варианте (как в карте).

Почему так (решения, принятые при имплементации):
  • вес = релевантность линзы (1..3, хост объясняет строкой) × множитель трек-рекорда из
    петли исхода. Множитель зажат в [0.5, 1.5]: трек-рекорд — это 3-10 исходов ОДНОГО юзера,
    малое N; без зажима пара неудач заглушила бы линзу целиком, а совет ценен именно тем, что
    неудобная линза звучит. Трек может ослабить/усилить голос, но не выключить его.
  • ничья по баллу → статус-кво (консервативно: из равных лучше обратимое «не делать»), флаг tie.
  • спред (разброс оценок на рекомендованном варианте) снижает уверенность совета: 7.0 при
    разбросе 1 и 7.0 при разбросе 6 — разные ответы, среднее этого не видит.
  • единодушие НЕ меняет метку, а поднимает тревогу: согласие пяти линз на одном вопросе —
    чаще признак того, что сильнейшую альтернативу никто не аргументировал (эхо-камера).
"""
import datetime
import math
import os
import sys
from decimal import ROUND_HALF_UP, Decimal
from html import escape as _html_escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decision_map import _is_number, _nonempty_str  # те же числовые/строковые гейты

# ── константы схемы ─────────────────────────────────────────────────────────
GO = "GO"
GO_WITH_CONDITIONS = "GO_WITH_CONDITIONS"
RESHAPE = "RESHAPE"
DONT = "DONT"
WAIT = "WAIT"

# порядок для потолков: больше = «смелее»; WAIT вне шкалы (отдельное решение «не сейчас»)
_RANK = {GO: 3, GO_WITH_CONDITIONS: 2, RESHAPE: 1, DONT: 0}

LABELS_RU = {GO: "ИДТИ", GO_WITH_CONDITIONS: "ИДТИ С УСЛОВИЯМИ", RESHAPE: "ПЕРЕДЕЛАТЬ",
             DONT: "НЕ ДЕЛАТЬ", WAIT: "ЖДАТЬ"}
LABELS_EN = {GO: "GO", GO_WITH_CONDITIONS: "GO WITH CONDITIONS", RESHAPE: "RESHAPE",
             DONT: "DON'T DO IT", WAIT: "WAIT"}

RUIN_RISKS = {"none", "possible", "likely"}
DOORS = {"one-way", "two-way"}
CRUX_KINDS = ("fact", "numbers", "values")

SCORE_MIN, SCORE_MAX = 0, 10
TRACK_MIN, TRACK_MAX = 0.5, 1.5
_TRACK_NEUTRAL_SCORE = 0.5      # Laplace-нейтраль advisor_calibration: score 0.5 → множитель 1.0

# полосы по баллу рекомендованного варианта (после округления до 0.1 — то, что видит юзер)
BAND_GO = 7.5
BAND_GWC = 6.0
BAND_RESHAPE = 4.5

ONE_WAY_SPREAD = 4              # необратимо + разброс ≥4 → не выше ИДТИ С УСЛОВИЯМИ
CONFIDENCE_SPREAD_PENALTY = 5   # разброс ≥5 → уверенность совета −1
UNANIMITY_WINDOW = 1            # все оценки на общем фаворите в пределах 1 балла → тревога

SINGLE_VOICE_ERROR = "совет из одного голоса — это консультация, не вердикт"


def _e(x):
    """Экранирование для md: Cowork рендерит .md как rich-HTML (как в session_render.render_md),
    поэтому <, >, & гасим; кавычки оставляем — в тексте они не опасны и читаемы."""
    return _html_escape(str(x), quote=False)


def label_text(code, lang="ru"):
    """Код метки → подпись на языке подачи (ru по умолчанию, en при lang='en')."""
    return (LABELS_EN if lang == "en" else LABELS_RU).get(code, str(code))


def _lang(lang):
    if lang in ("ru", "en"):
        return lang
    return "en" if (os.getenv("CONSILIUM_LANG") or "").strip().lower() == "en" else "ru"


def _round1(x):
    """Округление до 0.1 по-школьному (half-up), не банковское round(): 6.45 → 6.5."""
    return float(Decimal(repr(float(x))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _round_int(x):
    return int(Decimal(repr(float(x))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fmt(x):
    """Число для математической строки: целое — без точки, иначе до 2 знаков без хвостовых нулей."""
    x = float(x)
    if x.is_integer():
        return str(int(x))
    return ("%.2f" % x).rstrip("0").rstrip(".")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# ── валидация ───────────────────────────────────────────────────────────────

def _validate_options(card, errors):
    options = card.get("options")
    if not isinstance(options, list) or len(options) < 2:
        errors.append("Нужно минимум два варианта (options), включая статус-кво «оставить как "
                      "есть» — без альтернативы вердикту не с чем сравнивать.")
        options = options if isinstance(options, list) else []
    ids, sq = [], 0
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            errors.append("Вариант #%d должен быть объектом {id, label, status_quo}." % (i + 1))
            continue
        oid = opt.get("id")
        if not _nonempty_str(oid):
            errors.append("У варианта #%d нет id." % (i + 1))
        elif oid in ids:
            errors.append("Id варианта «%s» повторяется — id должны быть уникальны." % oid)
        else:
            ids.append(oid)
        if not _nonempty_str(opt.get("label")):
            errors.append("У варианта #%d нет подписи (label) — юзер должен видеть, за что "
                          "голосует совет." % (i + 1))
        if opt.get("status_quo") is True:
            sq += 1
        elif "status_quo" in opt and opt.get("status_quo") is not False:
            errors.append("Флаг статус-кво у варианта #%d должен быть литеральным true/false — "
                          "строки не принимаются (fail-closed)." % (i + 1))
    if options and sq != 1:
        errors.append("Ровно один вариант должен нести флаг статус-кво (\"status_quo\": true) — "
                      "сейчас таких: %d. Совет обязан сравнить с «оставить как есть»." % sq)
    return ids


def _validate_seat(seat, idx, option_ids, errors):
    """Гейты одного места совета; возвращает имя (или None)."""
    if not isinstance(seat, dict):
        errors.append("Место совета #%d должно быть объектом." % (idx + 1))
        return None
    name = seat.get("name")
    if not _nonempty_str(name):
        errors.append("У места совета #%d нет имени (name)." % (idx + 1))
        name, tag = None, "#%d" % (idx + 1)
    else:
        tag = "«%s»" % name

    w = seat.get("weight")
    if not _is_int(w) or not (1 <= w <= 3):
        errors.append("Вес линзы %s (weight) — целое 1, 2 или 3 (насколько линза релевантна "
                      "ЭТОМУ вопросу); сейчас: %r." % (tag, w))
    if not _nonempty_str(seat.get("weight_reason")):
        errors.append("У %s нет обоснования веса (weight_reason) — одной строкой, почему "
                      "его линза весит столько на этом вопросе." % tag)

    scores = seat.get("scores")
    if not isinstance(scores, dict):
        errors.append("У %s нет оценок вариантов (scores: {id: 0..10})." % tag)
    else:
        for oid in option_ids:
            if oid not in scores:
                errors.append("%s не оценил вариант «%s» — каждый советник оценивает КАЖДЫЙ "
                              "вариант." % (tag, oid))
            else:
                v = scores[oid]
                if not _is_number(v) or not (SCORE_MIN <= v <= SCORE_MAX):
                    errors.append("Оценка %s по варианту «%s» должна быть конечным числом от 0 "
                                  "до 10 — сейчас: %r." % (tag, oid, v))
        for k in scores:
            if k not in option_ids:
                errors.append("%s оценил неизвестный вариант «%s» — такого id нет в options."
                              % (tag, k))

    if "pillar_score" in seat and seat.get("pillar_score") is not None:
        p = seat["pillar_score"]
        if not _is_number(p) or not (SCORE_MIN <= p <= SCORE_MAX):
            errors.append("Оценка по своей линзе (pillar_score) у %s — число от 0 до 10; "
                          "сейчас: %r." % (tag, p))

    c = seat.get("confidence")
    if not _is_int(c) or not (1 <= c <= 5):
        errors.append("Уверенность %s (confidence) — целое от 1 до 5; сейчас: %r." % (tag, c))

    if seat.get("ruin_risk") not in RUIN_RISKS:
        errors.append("Риск разорения у %s (ruin_risk) — none, possible или likely; сейчас: %r."
                      % (tag, seat.get("ruin_risk")))
    if "ruin_on" in seat and seat.get("ruin_on") is not None and seat.get("ruin_on") not in option_ids:
        errors.append("ruin_on у %s ссылается на неизвестный вариант %r." % (tag, seat.get("ruin_on")))
    if seat.get("door") not in DOORS:
        errors.append("Дверь у %s (door) — one-way (необратимо) или two-way (обратимо); "
                      "сейчас: %r." % (tag, seat.get("door")))
    if not _nonempty_str(seat.get("change_my_mind")):
        errors.append("%s не назвал, что изменит его позицию (change_my_mind) — конкретный "
                      "факт или число. Позиция без опровержителя — догма, не совет." % tag)
    if not _nonempty_str(seat.get("question_for_user")):
        errors.append("%s не задал вопрос юзеру перед подписью (question_for_user)." % tag)
    return name


def _validate_seat_ref(ref, seat_names, where, errors):
    if not _nonempty_str(ref):
        errors.append("%s: не указано место совета (seat)." % where)
    elif ref not in seat_names:
        errors.append("%s ссылается на советника «%s», которого нет среди мест совета."
                      % (where, ref))


def _validate_cruxes(card, seat_names, errors):
    cruxes = card.get("cruxes")
    if cruxes is None:
        return
    if not isinstance(cruxes, list):
        errors.append("cruxes — список развилок [{question, kind, sides}].")
        return
    for i, cx in enumerate(cruxes):
        where = "Развилка #%d" % (i + 1)
        if not isinstance(cx, dict):
            errors.append("%s должна быть объектом." % where)
            continue
        if not _nonempty_str(cx.get("question")):
            errors.append("%s без вопроса (question)." % where)
        if cx.get("kind") not in CRUX_KINDS:
            errors.append("%s: вид (kind) — fact, numbers или values; сейчас: %r."
                          % (where, cx.get("kind")))
        sides = cx.get("sides")
        if not isinstance(sides, list) or not sides:
            errors.append("%s без сторон (sides: [{position, seats}])." % where)
            continue
        for j, sd in enumerate(sides):
            sw = "%s, сторона #%d" % (where, j + 1)
            if not isinstance(sd, dict):
                errors.append("%s должна быть объектом." % sw)
                continue
            if not _nonempty_str(sd.get("position")):
                errors.append("%s без позиции (position)." % sw)
            seats = sd.get("seats")
            if not isinstance(seats, list) or not seats:
                errors.append("%s: не названы советники (seats)." % sw)
                continue
            for s in seats:
                _validate_seat_ref(s, seat_names, sw, errors)


def _validate_minority(card, seat_names, errors):
    mino = card.get("minority")
    if mino is None:
        return
    if not isinstance(mino, list):
        errors.append("minority — список [{seat, claim, right_if}].")
        return
    for i, m in enumerate(mino):
        where = "Мнение меньшинства #%d" % (i + 1)
        if not isinstance(m, dict):
            errors.append("%s должно быть объектом." % where)
            continue
        _validate_seat_ref(m.get("seat"), seat_names, where, errors)
        if not _nonempty_str(m.get("claim")):
            errors.append("%s без тезиса (claim)." % where)
        if not _nonempty_str(m.get("right_if")):
            errors.append("%s без условия правоты (right_if) — при каком факте меньшинство "
                          "окажется право? Без него особое мнение не проверить." % where)


def _validate_mitigations(card, seat_names, errors):
    mits = card.get("ruin_mitigations")
    if mits is None:
        return
    if not isinstance(mits, list):
        errors.append("ruin_mitigations — список [{seat, mitigation, endorsed}].")
        return
    for i, m in enumerate(mits):
        where = "Страховка от разорения #%d" % (i + 1)
        if not isinstance(m, dict):
            errors.append("%s должна быть объектом." % where)
            continue
        _validate_seat_ref(m.get("seat"), seat_names, where, errors)
        if not _nonempty_str(m.get("mitigation")):
            errors.append("%s без описания (mitigation)." % where)
        if not isinstance(m.get("endorsed"), bool):
            errors.append("%s: endorsed — литеральный true/false (одобрил ли страховку САМ "
                          "советник, поднявший риск)." % where)


def _validate_lists(card, errors):
    ct = card.get("cheapest_test")
    if ct is not None and not isinstance(ct, str):
        errors.append("cheapest_test — строка (самый дешёвый тест до необратимого шага).")
    kc = card.get("kill_criteria")
    if kc is not None:
        if not isinstance(kc, list) or not all(_nonempty_str(x) for x in kc):
            errors.append("kill_criteria — список непустых проверяемых строк (когда остановиться).")
    steps = card.get("steps")
    if steps is not None:
        if not isinstance(steps, list):
            errors.append("steps — список [{when, action}].")
        else:
            for i, st in enumerate(steps):
                if not (isinstance(st, dict) and _nonempty_str(st.get("when"))
                        and _nonempty_str(st.get("action"))):
                    errors.append("Шаг #%d — объект с непустыми when (когда) и action (что)."
                                  % (i + 1))
    wait = card.get("wait")
    if wait is not None:
        if not isinstance(wait, dict):
            errors.append("wait — объект {trigger, date, if_fails}.")
            return
        if not _nonempty_str(wait.get("trigger")):
            errors.append("У ЖДАТЬ нет триггера (trigger) — чего именно ждём?")
        d = wait.get("date")
        try:
            ok = isinstance(d, str) and bool(datetime.date.fromisoformat(d))
        except ValueError:
            ok = False
        if not ok:
            errors.append("У ЖДАТЬ дата (date) — ISO YYYY-MM-DD; сейчас: %r. Ожидание без даты "
                          "— это откладывание." % (d,))
        if not _nonempty_str(wait.get("if_fails")):
            errors.append("У ЖДАТЬ нет плана на случай, если триггер не сработал (if_fails).")


def validate_scorecard(card):
    """Fail-closed валидация scorecard → список RU-ошибок ([] = валиден). Ошибки
    аккумулируются (все разом): хост задаёт юзеру/советникам все вопросы за один заход."""
    if not isinstance(card, dict):
        return ["Scorecard вердикта должен быть JSON-объектом — получено: %s."
                % type(card).__name__]
    errors = []
    option_ids = _validate_options(card, errors)

    seats = card.get("seats")
    seat_names = []
    if not isinstance(seats, list):
        errors.append("Нет мест совета (seats): " + SINGLE_VOICE_ERROR + ".")
        seats = []
    elif len(seats) < 2:
        errors.append(SINGLE_VOICE_ERROR[0].upper() + SINGLE_VOICE_ERROR[1:] +
                      ": нужно минимум два места (seats).")
    for i, seat in enumerate(seats):
        name = _validate_seat(seat, i, option_ids, errors)
        if name is not None:
            if name in seat_names:
                errors.append("Имя советника «%s» повторяется — у каждого места одно имя." % name)
            else:
                seat_names.append(name)

    _validate_cruxes(card, seat_names, errors)
    _validate_minority(card, seat_names, errors)
    _validate_mitigations(card, seat_names, errors)
    _validate_lists(card, errors)
    return errors


# ── трек-рекорд → множители ─────────────────────────────────────────────────

def _track_multipliers(track_weights, seat_names):
    """Выход петли исхода → {seat: множитель ∈ [0.5, 1.5]}, плюс несопоставленные имена.

    Принимаемые формы (чтобы хост мог передать выход advisor_weights как есть):
      • {"scores": {name: {"score": p, ...}}, "weights": {...}} — выход тула advisor_weights;
        берём score (Laplace-доля одобренных хороших исходов): 0.5 нейтраль → ×1.0;
      • {"weights": {name: share}} без scores — нормированные доли (сумма 1): ×share·N;
      • {name: {"score": p}} — то же, что scores;
      • {name: float} — множитель напрямую.
    Имена сверяются без учёта регистра/пробелов по краям. Не-число → ValueError (fail-closed)."""
    if track_weights is None:
        return {}, []
    if not isinstance(track_weights, dict):
        raise ValueError("track_weights — объект {советник: множитель} или выход advisor_weights.")
    raw = {}
    if isinstance(track_weights.get("scores"), dict):
        for name, sc in track_weights["scores"].items():
            p = sc.get("score") if isinstance(sc, dict) else None
            if not _is_number(p):
                raise ValueError("track_weights.scores[%r].score — конечное число." % name)
            raw[name] = p / _TRACK_NEUTRAL_SCORE
    elif isinstance(track_weights.get("weights"), dict):
        ws = track_weights["weights"]
        for name, share in ws.items():
            if not _is_number(share):
                raise ValueError("track_weights.weights[%r] — конечное число." % name)
            raw[name] = share * len(ws)
    else:
        for name, v in track_weights.items():
            if isinstance(v, dict):
                p = v.get("score")
                if not _is_number(p):
                    raise ValueError("track_weights[%r].score — конечное число." % name)
                raw[name] = p / _TRACK_NEUTRAL_SCORE
            elif _is_number(v):
                raw[name] = v
            else:
                raise ValueError("track_weights[%r] — конечное число (множитель)." % name)
    norm = {str(k).strip().lower(): v for k, v in raw.items()}
    out = {}
    for s in seat_names:
        key = s.strip().lower()
        if key in norm:
            out[s] = min(TRACK_MAX, max(TRACK_MIN, float(norm[key])))
    seat_keys = {s.strip().lower() for s in seat_names}
    unmatched = [k for k in raw if str(k).strip().lower() not in seat_keys]
    return out, unmatched


# ── расчёт ──────────────────────────────────────────────────────────────────

def _cap(label, ceiling):
    return ceiling if _RANK[label] > _RANK[ceiling] else label


def _band(score):
    if score >= BAND_GO:
        return GO
    if score >= BAND_GWC:
        return GO_WITH_CONDITIONS
    if score >= BAND_RESHAPE:
        return RESHAPE
    return DONT


def _seat_tops(seat, option_ids):
    """Варианты с максимальной оценкой у места (ничья → несколько)."""
    best = max(seat["scores"][o] for o in option_ids)
    return [o for o in option_ids if seat["scores"][o] == best]


def _names(xs):
    return ", ".join(xs)


def compute_verdict(card, track_weights=None):
    """Scorecard → вердикт (dict). Невалидный вход → ValueError со всеми ошибками через '; '.

    Метку считает только код: полоса по взвешенному баллу рекомендованного варианта, затем
    поправки по порядку (ruin_cap → one_way_cap → unanimity → wait); каждая сработавшая
    поправка пишется в overrides с RU-причиной — хост показывает их, а не пересказывает."""
    errors = validate_scorecard(card)
    if errors:
        raise ValueError("; ".join(errors))

    options = card["options"]
    option_ids = [o["id"] for o in options]
    opt_by_id = {o["id"]: o for o in options}
    sq_id = next(o["id"] for o in options if o.get("status_quo") is True)
    seats = card["seats"]
    names = [s["name"] for s in seats]

    mults, unmatched = _track_multipliers(track_weights, names)
    weights_source = "relevance×track" if mults else "relevance"
    eff = {s["name"]: s["weight"] * mults.get(s["name"], 1.0) for s in seats}
    total_w = sum(eff.values())

    # баллы вариантов + математическая строка (эффективные веса)
    scores = []
    for oid in option_ids:
        raw = sum(eff[s["name"]] * s["scores"][oid] for s in seats) / total_w
        sc = _round1(raw)
        terms = " + ".join("%s×%s" % (_fmt(eff[s["name"]]), _fmt(s["scores"][oid])) for s in seats)
        scores.append({"id": oid, "label": opt_by_id[oid]["label"],
                       "status_quo": oid == sq_id, "score": sc, "raw": raw,
                       "math": "%s (%s) / %s = %.1f" % (oid, terms, _fmt(total_w), sc)})

    top = max(x["score"] for x in scores)
    tied = [x["id"] for x in scores if x["score"] == top]
    tie = len(tied) > 1
    rec_id = sq_id if (tie and sq_id in tied) else tied[0]
    rec = next(x for x in scores if x["id"] == rec_id)

    rec_seat_scores = [s["scores"][rec_id] for s in seats]
    spread = max(rec_seat_scores) - min(rec_seat_scores)
    avg_conf = sum(s["confidence"] for s in seats) / len(seats)
    council_conf = _round_int(avg_conf * 2) - (1 if spread >= CONFIDENCE_SPREAD_PENALTY else 0)
    council_conf = max(1, min(10, council_conf))

    rec_label = opt_by_id[rec_id]["label"]
    if rec_id == sq_id:
        label = DONT
        base_reason = ("Лучший вариант — не делать / оставить как есть: статус-кво «%s» набрал "
                       "%.1f — больше любого действия%s." %
                       (rec_label, rec["score"], " (ничья решена в пользу статус-кво)" if tie else ""))
    else:
        label = _band(rec["score"])
        base_reason = ("Вариант %s «%s» набрал %.1f → полоса %s (≥7.5 ИДТИ · 6.0–7.4 ИДТИ С "
                       "УСЛОВИЯМИ · 4.5–5.9 ПЕРЕДЕЛАТЬ · <4.5 НЕ ДЕЛАТЬ)."
                       % (rec_id, rec_label, rec["score"], label_text(label)))
    base_label = label
    overrides, missing, notes = [], [], []

    # 1. ruin_cap — риск разорения без одобренной самим советником страховки
    endorsed = {m["seat"] for m in (card.get("ruin_mitigations") or []) if m.get("endorsed") is True}
    ruin_seats, mitigated = [], []
    for s in seats:
        if s["ruin_risk"] != "likely":
            continue
        targets = [s["ruin_on"]] if s.get("ruin_on") else _seat_tops(s, option_ids)
        if rec_id not in targets:
            continue
        (mitigated if s["name"] in endorsed else ruin_seats).append(s["name"])
    if ruin_seats:
        before = label
        label = _cap(label, RESHAPE)
        overrides.append({
            "rule": "ruin_cap", "from": before, "to": label, "seats": ruin_seats,
            "effect": "потолок %s" % label_text(RESHAPE),
            "reason": ("%s видит вероятное необратимое разорение на варианте %s, и страховки, "
                       "одобренной ими самими, нет — вердикт не выше ПЕРЕДЕЛАТЬ."
                       % (_names(ruin_seats), rec_id))})

    # 2. one_way_cap — необратимая дверь при расколе совета
    one_way_n = sum(1 for s in seats if s["door"] == "one-way")
    one_way = one_way_n >= len(seats) - one_way_n           # ничья голосов → one-way (консервативно)
    cheapest = card.get("cheapest_test")
    cheapest = cheapest.strip() if isinstance(cheapest, str) and cheapest.strip() else None
    if one_way and spread >= ONE_WAY_SPREAD:
        before = label
        label = _cap(label, GO_WITH_CONDITIONS)
        if not cheapest:
            missing.append("cheapest_test")
        overrides.append({
            "rule": "one_way_cap", "from": before, "to": label, "spread": spread,
            "effect": "потолок %s + обязателен дешёвый тест" % label_text(GO_WITH_CONDITIONS),
            "reason": ("Шаг необратим (one-way у %d из %d мест), а разброс оценок на %s = %s — "
                       "до необратимого шага нужен самый дешёвый тест%s."
                       % (one_way_n, len(seats), rec_id, _fmt(spread),
                          "" if cheapest else "; его пока нет")) })

    # 3. unanimity — тревога эхо-камеры (метку НЕ меняет)
    seat_tops = [_seat_tops(s, option_ids) for s in seats]
    unanimity = (all(len(t) == 1 for t in seat_tops)
                 and len({t[0] for t in seat_tops}) == 1
                 and seat_tops[0][0] == rec_id
                 and spread <= UNANIMITY_WINDOW)
    unanimity_instruction = None
    alt_id = None
    if unanimity:
        alts = sorted((x for x in scores if x["id"] != rec_id), key=lambda x: -x["raw"])
        alt_id = alts[0]["id"] if alts else None
        # линза «под наибольшим риском» = тот, чья ОЦЕНКА альтернативы ближе всего к фавориту
        at_risk = sorted(seats, key=lambda s: s["scores"][rec_id] - s["scores"][alt_id])[:2]
        unanimity_instruction = (
            "Все места (%d) ставят %s на первое место с разбросом ≤%d. Назови сильнейшую "
            "неаргументированную альтернативу (%s «%s») отдельной развилкой и дай %s аргументировать "
            "её в полную силу, прежде чем юзер подпишет. Метка не меняется."
            % (len(seats), rec_id, UNANIMITY_WINDOW, alt_id, opt_by_id[alt_id]["label"],
               _names(s["name"] for s in at_risk)))
        if len(seats) < 3:
            unanimity_instruction += " Совет из двух мест — малое N: единодушие двоих мало что значит."
        overrides.append({"rule": "unanimity", "from": label, "to": label,
                          "alternative": alt_id, "seats": [s["name"] for s in at_risk],
                          "effect": "метка без изменений, тревога эхо-камеры",
                          "reason": unanimity_instruction})

    # 4. wait — хост предложил ЖДАТЬ, и после потолков вердикт «идти»
    wait = card.get("wait")
    wait_out = None
    if wait is not None:
        if label in (GO, GO_WITH_CONDITIONS):
            before = label
            label = WAIT
            wait_out = {"trigger": wait["trigger"], "date": wait["date"], "if_fails": wait["if_fails"]}
            overrides.append({"rule": "wait", "from": before, "to": WAIT,
                              "effect": "метка ЖДАТЬ до %s" % wait["date"],
                              "reason": ("Совет готов идти, но ждёт триггер «%s» до %s; не "
                                         "сработал — %s." % (wait["trigger"], wait["date"],
                                                             wait["if_fails"]))})
        else:
            notes.append("ЖДАТЬ не применено: после поправок вердикт %s — ждать нечего, вариант "
                         "сначала нужно переделать или отложить." % label_text(label))

    pillar_fixes = [{"seat": s["name"], "pillar_score": s["pillar_score"]}
                    for s in seats
                    if _is_number(s.get("pillar_score")) and s["pillar_score"] <= 4]

    kill = list(card.get("kill_criteria") or [])
    steps = [{"when": st["when"], "action": st["action"]} for st in (card.get("steps") or [])]
    if label in (GO, GO_WITH_CONDITIONS, WAIT):
        if not kill:
            missing.append("kill_criteria")
        if not steps:
            missing.append("steps")

    cruxes = {k: [] for k in CRUX_KINDS}
    for cx in card.get("cruxes") or []:
        cruxes[cx["kind"]].append({"question": cx["question"],
                                   "sides": [{"position": sd["position"], "seats": list(sd["seats"])}
                                             for sd in cx["sides"]]})

    if rec_id == sq_id:
        call = "Лучший вариант — не делать / оставить как есть (%s «%s»)." % (rec_id, rec_label)
    else:
        call = "Рекомендация совета: %s «%s» — %s." % (rec_id, rec_label, label_text(label))

    return {
        "label": label,
        "label_ru": label_text(label, "ru"),
        "label_en": label_text(label, "en"),
        "base_label": base_label,
        "base_reason": base_reason,
        "call": call,
        "recommended": {"id": rec_id, "label": rec_label, "status_quo": rec_id == sq_id,
                        "score": rec["score"]},
        "tie": tie,
        "tied": tied if tie else [],
        "scores": scores,
        "spread": spread,
        "avg_confidence": avg_conf,
        "council_confidence": council_conf,
        "weights_source": weights_source,
        "weights": {s["name"]: {"relevance": s["weight"], "track": mults.get(s["name"], 1.0),
                                "effective": eff[s["name"]], "reason": s["weight_reason"]}
                    for s in seats},
        "track_unmatched": unmatched,
        "door": "one-way" if one_way else "two-way",
        "overrides": overrides,
        "ruin_mitigated": mitigated,
        "unanimity_alarm": unanimity,
        "unanimity_instruction": unanimity_instruction,
        "wait": wait_out,
        "pillar_fixes": pillar_fixes,
        "cheapest_test": cheapest,
        "kill_criteria": kill,
        "steps": steps,
        "missing": missing,
        "complete": not missing,
        "cruxes": cruxes,
        "minority": [{"seat": m["seat"], "claim": m["claim"], "right_if": m["right_if"]}
                     for m in (card.get("minority") or [])],
        "falsifiers": {s["name"]: s["change_my_mind"] for s in seats},
        "questions": {s["name"]: s["question_for_user"] for s in seats},
        "notes": notes,
    }


# ── подача ──────────────────────────────────────────────────────────────────
# verdict_view — нормализованные СТРОКИ (без экранирования) для любого surface; рендеры
# (md здесь, widget/html в session_render) экранируют сами. Толерантен к кривому dict от хоста:
# без валидной метки → None (блок не рендерится, рендер не падает).

_T = {
    "ru": {
        "head": "Вердикт совета", "scores": "Оценки", "sq": "статус-кво",
        "conf": "уверенность совета %s/10 · разброс %s",
        "minority": "%s: %s; права, если %s",
        "kill": "Остановиться, если", "steps": "Шаги", "test": "Дешёвый тест",
        "ask": "Перед подписью", "missing": "Не хватает", "pillar": "Нужен именованный фикс "
        "(линза ≤4 даже при ИДТИ)", "wait": "Ждём «%s» до %s; не сработало: %s",
        "math": "Математика", "weights": "Веса (%s)", "falsif": "Что изменит позицию",
        "cruxes": "Развилки", "unanim": "Тревога единодушия",
        "spread_hint": "Разброс %s на %s: тот же балл при согласии и при расколе — разные ответы.",
        "tie": "Ничья %s: выбран статус-кво или первый вариант (консервативно).",
        "kinds": {"fact": "факт", "numbers": "числа", "values": "ценности"},
        "missing_names": {"cheapest_test": "дешёвый тест", "kill_criteria": "критерии остановки",
                          "steps": "датированные шаги"},
    },
    "en": {
        "head": "Council verdict", "scores": "Scores", "sq": "status quo",
        "conf": "council confidence %s/10 · spread %s",
        "minority": "%s: %s; right if %s",
        "kill": "Stop if", "steps": "Steps", "test": "Cheapest test",
        "ask": "Before you sign", "missing": "Missing", "pillar": "Needs a named fix "
        "(lens at 4 or below, even on GO)", "wait": "Waiting for \"%s\" until %s; if it fails: %s",
        "math": "Math", "weights": "Weights (%s)", "falsif": "What would change their mind",
        "cruxes": "Cruxes", "unanim": "Unanimity alarm",
        "spread_hint": "Spread %s on %s: the same score from agreement and from a split are different answers.",
        "tie": "Tie %s: status quo or first option chosen (conservative).",
        "kinds": {"fact": "fact", "numbers": "numbers", "values": "values"},
        "missing_names": {"cheapest_test": "cheapest test", "kill_criteria": "kill criteria",
                          "steps": "dated steps"},
    },
}

_RULE_EN = {
    "ruin_cap": "Ruin cap: %s flag likely irreversible ruin on %s with no mitigation they endorse; capped at %s.",
    "one_way_cap": "One-way cap: irreversible step with spread %s; capped at %s, cheapest test required.",
    "unanimity": "Unanimity alarm: argue %s at full strength before signing (label unchanged).",
    "wait": "Wait: %s until %s.",
}


def _override_line(o, rec_id, lang):
    rule = o.get("rule")
    if lang == "ru":
        if rule == "unanimity":
            return "Тревога единодушия: аргументировать %s в полную силу (метка не меняется)." \
                % o.get("alternative")
        return str(o.get("reason") or o.get("effect") or rule)
    if rule == "ruin_cap":
        return _RULE_EN[rule] % (", ".join(o.get("seats") or []), rec_id, label_text(o.get("to"), "en"))
    if rule == "one_way_cap":
        return _RULE_EN[rule] % (_fmt(o.get("spread", 0)), label_text(o.get("to"), "en"))
    if rule == "unanimity":
        return _RULE_EN[rule] % o.get("alternative")
    if rule == "wait":
        return "Wait: label set to WAIT."
    return str(rule)


def verdict_view(result, lang=None):
    """Результат compute_verdict → плоские строки для подачи ({...} или None на кривом входе)."""
    if not isinstance(result, dict) or result.get("label") not in LABELS_RU:
        return None
    lang = _lang(lang)
    t = _T[lang]
    rec = result.get("recommended") if isinstance(result.get("recommended"), dict) else {}
    rec_id = str(rec.get("id", ""))
    sc_parts = []
    for x in result.get("scores") or []:
        if not isinstance(x, dict):
            continue
        sq = " (%s)" % t["sq"] if x.get("status_quo") else ""
        try:
            sc_parts.append("%s %.1f%s" % (x.get("id"), float(x.get("score")), sq))
        except (TypeError, ValueError):
            continue
    if lang == "ru":
        headline = str(result.get("call") or "")
    elif rec.get("status_quo"):
        headline = "Best option: don't act, keep things as they are (%s \"%s\")." % (rec_id, rec.get("label", ""))
    else:
        headline = "Council recommends %s \"%s\": %s." % (rec_id, rec.get("label", ""),
                                                          label_text(result["label"], "en"))
    try:
        spread = _fmt(result.get("spread", 0))
    except (TypeError, ValueError):
        spread = "?"
    view = {
        "label": label_text(result["label"], lang),
        "code": result["label"],
        "headline": headline,
        "scores_line": "%s: %s" % (t["scores"], " · ".join(sc_parts)) if sc_parts else "",
        "conf_line": t["conf"] % (result.get("council_confidence", "?"), spread),
        "overrides": [_override_line(o, rec_id, lang) for o in (result.get("overrides") or [])
                      if isinstance(o, dict)],
        "minority": [t["minority"] % (m.get("seat", ""), m.get("claim", ""), m.get("right_if", ""))
                     for m in (result.get("minority") or []) if isinstance(m, dict)],
        "kill": [str(k) for k in (result.get("kill_criteria") or [])],
        "steps": ["%s: %s" % (s.get("when", ""), s.get("action", ""))
                  for s in (result.get("steps") or []) if isinstance(s, dict)],
        "test": str(result["cheapest_test"]) if result.get("cheapest_test") else "",
        "wait": "",
        "pillar": [str(p.get("seat", "")) for p in (result.get("pillar_fixes") or [])
                   if isinstance(p, dict)],
        "questions": ["%s: %s" % (k, v) for k, v in (result.get("questions") or {}).items()]
        if isinstance(result.get("questions"), dict) else [],
        "missing": [t["missing_names"].get(m, str(m)) for m in (result.get("missing") or [])],
        "t": t,
    }
    w = result.get("wait")
    if isinstance(w, dict):
        view["wait"] = t["wait"] % (w.get("trigger", ""), w.get("date", ""), w.get("if_fails", ""))
    # expert
    view["math"] = [str(x.get("math")) for x in (result.get("scores") or [])
                    if isinstance(x, dict) and x.get("math")]
    ws = result.get("weights") if isinstance(result.get("weights"), dict) else {}
    view["weights"] = (t["weights"] % result.get("weights_source", "relevance")) + ": " + " · ".join(
        "%s %s" % (k, _fmt(v.get("effective", 0))) for k, v in ws.items() if isinstance(v, dict)) \
        if ws else ""
    view["spread_hint"] = t["spread_hint"] % (spread, rec_id)
    view["tie"] = (t["tie"] % "/".join(result.get("tied") or [])) if result.get("tie") else ""
    view["falsifiers"] = ["%s: %s" % (k, v) for k, v in (result.get("falsifiers") or {}).items()] \
        if isinstance(result.get("falsifiers"), dict) else []
    cx = result.get("cruxes") if isinstance(result.get("cruxes"), dict) else {}
    view["cruxes"] = ["[%s] %s" % (t["kinds"].get(k, k), c.get("question", ""))
                      for k in CRUX_KINDS for c in (cx.get(k) or []) if isinstance(c, dict)]
    view["unanimity"] = str(result.get("unanimity_instruction") or "") if lang == "ru" else (
        "Every seat ranks %s first within 1 point. Name the strongest unargued alternative as a "
        "crux and have the most exposed lenses argue it at full strength." % rec_id
        if result.get("unanimity_alarm") else "")
    return view


def render_verdict_md(result, lang="ru", depth="plain"):
    """Компактный markdown-блок вердикта. plain — метка, рекомендация, оценки, поправки,
    меньшинство, остановка, шаги, вопросы перед подписью; expert — плюс математика, веса,
    подсказка о разбросе, опровержители, развилки. Всё экранировано (Cowork рендерит md как
    HTML). Кривой вход → пустая строка (рендер заседания не падает)."""
    v = verdict_view(result, lang)
    if v is None:
        return ""
    t = v["t"]
    out = ["### %s: %s" % (t["head"], _e(v["label"])), "", "**%s**" % _e(v["headline"])]
    if v["scores_line"]:
        out.append(_e(v["scores_line"]) + " · " + _e(v["conf_line"]))
    out += ["- " + _e(x) for x in v["overrides"]]
    if v["wait"]:
        out.append("- " + _e(v["wait"]))
    if v["pillar"]:
        out.append("- %s: %s" % (t["pillar"], _e(", ".join(v["pillar"]))))
    if v["minority"]:
        out += ["- " + _e(x) for x in v["minority"]]
    if v["test"]:
        out.append("- %s: %s" % (t["test"], _e(v["test"])))
    if v["kill"]:
        out.append("- %s: %s" % (t["kill"], _e("; ".join(v["kill"]))))
    if v["steps"]:
        out.append("- %s: %s" % (t["steps"], _e("; ".join(v["steps"]))))
    if v["missing"]:
        out.append("- **%s:** %s" % (t["missing"], _e(", ".join(v["missing"]))))
    if v["questions"]:
        out.append("- %s: %s" % (t["ask"], _e(" | ".join(v["questions"]))))
    if depth == "expert":
        out += ["", "%s:" % t["math"]] + ["- `%s`" % _e(m) for m in v["math"]]
        if v["weights"]:
            out.append("- " + _e(v["weights"]))
        out.append("- " + _e(v["spread_hint"]))
        if v["tie"]:
            out.append("- " + _e(v["tie"]))
        if v["unanimity"]:
            out.append("- %s: %s" % (t["unanim"], _e(v["unanimity"])))
        if v["falsifiers"]:
            out.append("- %s: %s" % (t["falsif"], _e(" | ".join(v["falsifiers"]))))
        if v["cruxes"]:
            out.append("- %s: %s" % (t["cruxes"], _e(" | ".join(v["cruxes"]))))
    return "\n".join(out)
