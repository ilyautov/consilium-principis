#!/usr/bin/env python3
"""Шасси-онбординг: создать Принцепс из ответов + подсказать «что собрать дальше».

Пробел #3 (шасси): сборка доски была developer-facing (руками). Это даёт юзеру, находящемуся
в Claude, собрать всё разговором — скилл задаёт вопросы, эти функции скаффолдят и ведут.
  • scaffold_principis(answers) → markdown principis.md (round-trip через load_principis);
    ВЕКТОР не фиксируем, если не дан — пробел держим живым (совет допрашивает), см. спор про
    вектор-как-зеркало.
  • next_step(preflight) → один приоритетный шаг по состоянию доски (онбординг за руку).
"""
VALID_MODES = ("rigor", "support")
VALID_DEPTH = ("plain", "expert")


def scaffold_principis(answers):
    """Структурированные ответы юзера → текст principis.md. interface_mode fail-safe к rigor.
    depth: plain (чистый ответ на языке юзера, без чисел/разбора — дефолт для большинства) |
    expert (полная машинерия: вероятности, robustness, тиры). language: язык ответов
    ('auto' = подстраиваться под язык реплики юзера)."""
    mode = answers.get("interface_mode", "rigor")
    if mode not in VALID_MODES:
        mode = "rigor"
    depth = answers.get("depth", "plain")
    if depth not in VALID_DEPTH:
        depth = "plain"
    language = (answers.get("language") or "auto").strip()
    who = (answers.get("who") or "—").strip()
    vector = (answers.get("vector") or "").strip()
    temperament = (answers.get("temperament") or "—").strip()
    not_known = (answers.get("not_known") or "—").strip()
    vec = vector or "ПРОБЕЛ — совет допрашивает (вектор держим живым, не фиксируем как цель)"
    return (
        f"---\ninterface_mode: {mode}\ndepth: {depth}\nlanguage: {language}\n"
        f"owner: principis\nstatus: draft\n---\n"
        f"\n## Кто ты\n{who}\n"
        f"\n## Вектор (Олимп — куда идёшь)\n{vec}\n"
        f"\n## Интерфейс-нужда\n{mode}\n"
        f"\n## Подача\nЯзык: {language} · Глубина: {depth} "
        f"(plain — чистый ответ; expert — с вероятностями и разбором)\n"
        f"\n## Темперамент\n{temperament}\n"
        f"\n## Журнал решений\n"
        f"_(пусто — первое консеквенциальное решение запишется сюда; ИСХОД ⏳ дописывается по факту)_\n"
        f"\n## Что совет НЕ знает\n{not_known}\n"
    )


def next_step(pf):
    """Приоритетная следующая сборка по preflight. {action, why} — что и зачем делать."""
    if not pf["principis"]["ok"]:
        return {"action": "principis",
                "why": "без модели тебя совет — разовый оракул; собери Принцепс первым"}
    advisors = pf.get("advisors", [])
    if not any(a.get("has_corpus") for a in advisors):
        return {"action": "add-advisor",
                "why": "нет ни одного грунтованного советника — добавь корпус (его слова = 🔵)"}
    grounded = [a for a in advisors if a.get("has_corpus")]
    no_blue = [a for a in grounded if not a.get("blue_eligible")]
    if no_blue:
        return {"action": "fix-tiers",
                "why": f"{no_blue[0]['name']}: корпус есть, но нет P1/P2 — 🔵 невозможен, проверь манифест тиров"}
    no_kernels = [a for a in grounded if not a.get("has_kernels")]
    if no_kernels:
        return {"action": "build-kernels",
                "why": f"{no_kernels[0]['name']}: нет кернелов (метод советника) — собери из корпуса"}
    return {"action": "ready",
            "why": "доска готова к созыву; для петли U1 закрывай висящие ИСХОДЫ (pending_outcomes)"}
