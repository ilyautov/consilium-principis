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
        "decision": {"choice": None, "status": "defer"},
        "re_review_triggers": [],
        "provenance": dict(_EMPTY_PROVENANCE),
    }


def _tier_for_marker(marker):
    """Маркер → эмодзи-тир, копируя ровно то, что стоит в session. Неизвестный/отсутствующий
    маркер → None (не считается ни одним из трёх тиров, но текст допущения не теряется)."""
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
            # violation/None/незнакомое игнорируется, никогда не засчитывается как blue.
            if marker == "amber":
                marker_key = "yellow"
            else:
                marker_key = marker
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
    Fail-closed: любая проблема с импортом/структурой → []."""
    try:
        from session_render import _disagreement
    except Exception:
        return []
    try:
        d = _disagreement(session)
    except Exception:
        return []
    if not d:
        return []
    advisor = d.get("resolver") or ""
    out = []
    for side in d.get("sides", []):
        if side:
            out.append({"advisor": advisor, "point": str(side)})
    return out


def _decision(session):
    synthesis = session.get("synthesis") if isinstance(session.get("synthesis"), str) else None
    raw_decision = session.get("decision")
    status = None
    if isinstance(raw_decision, dict):
        status = raw_decision.get("status")
    elif isinstance(session.get("status"), str):
        status = session.get("status")
    if status not in _ALLOWED_STATUSES:
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


def build_record(session):
    """session (canon-объект заседания, session_render.py) → decision-record dict.

    {"question": str,
     "positions": [{"advisor": str, "stance": str,
                    "assumptions": [{"text": str, "tier": "🔵"|"🟢"|"🟡"|None}]}],
     "dissent": [{"advisor": str, "point": str}],
     "decision": {"choice": str|None, "status": "approve"|"approve_with_conditions"|
                  "defer"|"redesign"|"reject"},
     "re_review_triggers": [str, ...],
     "provenance": {"blue": int, "green": int, "yellow": int}}

    Zero LLM, zero network. Никогда не поднимает/не изобретает тир (см. модульный докстринг).
    """
    if not isinstance(session, dict):
        return _skeleton()

    question = session.get("question")
    positions, provenance = _positions_and_provenance(session.get("advisors"))
    dissent = _dissent(session)
    decision = _decision(session)
    re_review = _re_review_triggers(session)

    return {
        "question": str(question) if question else "",
        "positions": positions,
        "dissent": dissent,
        "decision": decision,
        "re_review_triggers": re_review,
        "provenance": provenance,
    }
