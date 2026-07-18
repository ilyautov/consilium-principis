"""decision_record.py — протокол заседания (board minutes) как канонический ВЫХОД совета.

Перенос Diligent Smart Minutes + red-team decision-record (arXiv 2607.01913) на форму
Consilium: детерминированная агрегация УЖЕ проведённого заседания, НОЛЬ LLM, ноль сети.

МОАТ-ИНВАРИАНТ (не ослаблять): тиры верности (🔵/🟢/🟡) в записи текут ТОЛЬКО из маркеров,
уже проставленных в session opinions (маркер ставит гейт — fidelity_check/render_session
ДО этого модуля). build_record копирует маркер как есть. Он НИКОГДА не:
  - поднимает 🟡/🟢 до 🔵,
  - изобретает маркер там, где его нет,
  - считает "violation"/None/незнакомый маркер как один из трёх тиров.
Если source-сессия вся 🟡 — запись вся 🟡. Это тестируется отдельно (test_decision_record.py,
MOAT-раздел) и не должно меняться будущими правками производительности/удобства.

Defensive-контракт: session может быть None / не-dict / с дырами (хост шлёт что попало) —
build_record никогда не кидает исключение, только возвращает честный (по возможности пустой)
skeleton.
"""

_MARKER_TO_TIER = {"blue": "🔵", "green": "🟢", "yellow": "🟡", "amber": "🟡"}

_ALLOWED_STATUSES = {"approve", "approve_with_conditions", "defer", "redesign", "reject"}

_EMPTY_PROVENANCE = {"blue": 0, "green": 0, "yellow": 0}


def _skeleton():
    return {
        "question": "",
        "positions": [],
        "dissent": [],
        "dissent_resolver": None,
        "decision": {"choice": None, "status": "defer"},
        "re_review_triggers": [],
        "provenance": dict(_EMPTY_PROVENANCE),
    }


def _tier_for_marker(marker):
    """Маркер → эмодзи-тир, копируя ровно то, что стоит в session. Неизвестный/отсутствующий
    маркер → None (не считается ни одним из трёх тиров, но текст допущения не теряется).
    Не-str маркер (dict/list — хост прислал мусор) обрабатывается как неизвестный → None,
    НИКОГДА не поднимается до тира (моат)."""
    if not isinstance(marker, str):
        return None
    if marker == "amber":
        marker = "yellow"
    return _MARKER_TO_TIER.get(marker)


def _positions_and_provenance(advisors):
    positions = []
    provenance = dict(_EMPTY_PROVENANCE)
    if not isinstance(advisors, list):
        return positions, provenance
    for a in advisors:
        if not isinstance(a, dict):
            continue
        name = a.get("name")
        opinions = a.get("opinions")
        if not isinstance(opinions, list):
            opinions = []
        assumptions = []
        stance_parts = []
        for op in opinions:
            if not isinstance(op, dict):
                continue
            argument = op.get("argument")
            marker = op.get("marker")
            tier = _tier_for_marker(marker)
            # provenance считает ТОЛЬКО реальные тир-маркеры источника (blue/green/yellow) —
            # violation/None/незнакомое/не-str-мусор игнорируется, никогда не засчитывается
            # как blue. Не-str маркер (dict/list) нельзя использовать как ключ → пропускаем.
            if isinstance(marker, str):
                marker_key = "yellow" if marker == "amber" else marker
                if marker_key in provenance:
                    provenance[marker_key] += 1
            if argument:
                assumptions.append({"text": str(argument), "tier": tier})
                stance_parts.append(str(argument))
        if not name and not assumptions:
            continue
        positions.append({
            "advisor": str(name) if name else "",
            "stance": stance_parts[0] if stance_parts else "",
            "assumptions": assumptions,
        })
    return positions, provenance


def _dissent(session):
    """Извлекает несогласие из _disagreement(session) (session_render), если доступно.
    Возвращает (dissent_list, resolver_or_None).

    Блок disagreement НЕ несёт имён советников (schema: {axis, sides, resolver}); resolver —
    это КАК снимается расхождение (действие/проверка), НЕ человек. Поэтому каждая сторона
    становится точкой диссента с advisor="" (честно «без атрибуции»), а resolver выносится
    отдельным полем dissent_resolver — не подмешивается в advisor (иначе фабрикуем советника).
    Fail-closed: любая проблема с импортом/структурой → ([], None)."""
    try:
        from session_render import _disagreement
    except Exception:
        return [], None
    try:
        d = _disagreement(session)
    except Exception:
        return [], None
    if not d:
        return [], None
    resolver = d.get("resolver")
    resolver = resolver if isinstance(resolver, str) and resolver else None
    out = []
    for side in d.get("sides", []):
        if side:
            out.append({"advisor": "", "point": str(side)})
    return out, resolver


def _decision(session):
    synthesis = session.get("synthesis") if isinstance(session.get("synthesis"), str) else None
    raw_decision = session.get("decision")
    status = None
    if isinstance(raw_decision, dict):
        status = raw_decision.get("status")
    elif isinstance(session.get("status"), str):
        status = session.get("status")
    # Не-str status (dict/list — хост прислал мусор) нельзя проверять на членство в set →
    # честно откатываемся к "defer" (не крашим set-membership на unhashable).
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        status = "defer"
    choice = synthesis if synthesis else None
    if not synthesis:
        status = "defer"
    return {"choice": choice, "status": status}


def _re_review_triggers(session):
    triggers = session.get("re_review_triggers")
    if isinstance(triggers, list):
        return [str(t) for t in triggers if t]
    if isinstance(triggers, str) and triggers:
        return [triggers]
    return []


def build_record(session, card_id=None):
    """session (canon-объект заседания, session_render.py) → decision-record dict.

    card_id (decision-lifecycle §3.4, аддитивно): если задан — сшивает протокол с
    Decision Card общим UUID (ключ `card_id`). Без него форма skeleton'а байт-в-байт
    прежняя (моат-инвариант тиров не затрагивается — card_id не влияет на маркеры).

    {"question": str,
     "positions": [{"advisor": str, "stance": str,
                    "assumptions": [{"text": str, "tier": "🔵"|"🟢"|"🟡"|None}]}],
     "dissent": [{"advisor": str, "point": str}],   # advisor="" — блок несогласия без имён
     "dissent_resolver": str|None,                  # КАК снимается расхождение (не советник)
     "decision": {"choice": str|None, "status": "approve"|"approve_with_conditions"|
                  "defer"|"redesign"|"reject"},
     "re_review_triggers": [str, ...],
     "provenance": {"blue": int, "green": int, "yellow": int}}

    Zero LLM, zero network. Никогда не поднимает/не изобретает тир (см. модульный докстринг).
    """
    if not isinstance(session, dict):
        rec = _skeleton()
        if card_id is not None:
            rec["card_id"] = str(card_id)
        return rec

    question = session.get("question")
    positions, provenance = _positions_and_provenance(session.get("advisors"))
    dissent, dissent_resolver = _dissent(session)
    decision = _decision(session)
    re_review = _re_review_triggers(session)

    record = {
        "question": str(question) if question else "",
        "positions": positions,
        "dissent": dissent,
        "dissent_resolver": dissent_resolver,
        "decision": decision,
        "re_review_triggers": re_review,
        "provenance": provenance,
    }
    if card_id is not None:                 # аддитивно: ключ появляется ТОЛЬКО при сшивании
        record["card_id"] = str(card_id)
    return record
