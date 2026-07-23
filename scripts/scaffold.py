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
VALID_CONTEXT = ("ask", "allow", "deny")


def scaffold_principis(answers):
    """Структурированные ответы юзера → текст principis.md. interface_mode fail-safe к rigor.
    depth: plain (чистый ответ на языке юзера, без чисел/разбора — дефолт) | expert (полная машинерия).
    language: язык ответов ('auto' = под язык реплики). context_expansion: ГЛОБАЛЬНОЕ согласие на
    подтягивание контекста СВЕРХ корпусов советника + заданного вопроса (память, другие проекты,
    внешние источники): ask (дефолт — спросить) | allow | deny. Non-capture: молча не вплетаем."""
    mode = answers.get("interface_mode", "rigor")
    if mode not in VALID_MODES:
        mode = "rigor"
    depth = answers.get("depth", "plain")
    if depth not in VALID_DEPTH:
        depth = "plain"
    context_expansion = answers.get("context_expansion", "ask")
    if context_expansion not in VALID_CONTEXT:
        context_expansion = "ask"
    language = (answers.get("language") or "auto").strip()
    who = (answers.get("who") or "—").strip()
    vector = (answers.get("vector") or "").strip()
    temperament = (answers.get("temperament") or "—").strip()
    not_known = (answers.get("not_known") or "—").strip()
    vec = vector or "ПРОБЕЛ — совет допрашивает (вектор держим живым, не фиксируем как цель)"
    return (
        f"---\ninterface_mode: {mode}\ndepth: {depth}\nlanguage: {language}\n"
        f"context_expansion: {context_expansion}\nowner: principis\nstatus: draft\n---\n"
        f"\n## Кто ты\n{who}\n"
        f"\n## Вектор (Олимп — куда идёшь)\n{vec}\n"
        f"\n## Интерфейс-нужда\n{mode}\n"
        f"\n## Подача\nЯзык: {language} · Глубина: {depth} "
        f"(plain — чистый ответ; expert — с вероятностями и разбором)\n"
        f"\n## Согласие на контекст\n{context_expansion} — можно ли подтягивать контекст СВЕРХ "
        f"корпусов советника и заданного вопроса (твоя память, другие проекты, внешнее). "
        f"ask = спросить перед этим · allow = можно молча · deny = строго в рамках вопроса+корпусов.\n"
        f"\n## Темперамент\n{temperament}\n"
        f"\n## Журнал решений\n"
        f"_(пусто — первое консеквенциальное решение запишется сюда; ИСХОД ⏳ дописывается по факту)_\n"
        f"\n## Что совет НЕ знает\n{not_known}\n"
    )


def scaffold_persona(name, lenses=None, domains=None):
    """ВАЛИДНЫЙ канонический скелет persona.md для нового советника — единый шаблон (F2).

    Состав повторяет собранного советника (frontmatter + Конституция / Как спорит / Чего не
    делает+never_quote / Quote bank 🔵 / Где challenge), чтобы scaffold = advisors/README =
    docs/onboarding-recipe (без рассинхрона). Читается тем же parse_frontmatter_list/load_advisor.

    lenses/domains по умолчанию ПУСТЫ: seed не знает их за юзера, а пустые списки заставляют
    diversity_check вернуть честный insufficient_data с подсказкой заполнить, вместо ложного
    score. Формат списков — `key: [a, b]` (в скобках), как ждёт parse_frontmatter_list.
    consent_status/role_framing — нарратив голоса/лицензии (код их не парсит, но они ведут
    автора и хост; role_framing в 3-м лице снижает sycophancy, arXiv 2505.23840)."""
    def _fmt(xs):
        return "[" + ", ".join(x for x in (xs or []) if x) + "]"
    nm = (name or "—").strip() or "—"
    return (
        f"---\nname: {nm}\naliases: [{nm}]\ndomains: {_fmt(domains)}\nlenses: {_fmt(lenses)}\n"
        f"consent_status: <public-domain | лицензия — заполни, чем правомерно грунтуешь>\n"
        f"role_framing: {nm} — независимый мыслитель, не ассистент. Инстанцируй в 3-м лице: держит "
        f"свою линзу и скорее оспорит замысел, чем поддакнет; угодить пользователю не его цель.\n---\n"
        f"\n# {nm}\n"
        f"\n<!-- Стартовый persona.md (записан scaffold). Заполни секции — и советник заработает в полную силу. -->\n"
        f"\n## Метаданные разнообразия (обязательно)\n"
        f"Впиши во фронтматер выше:\n"
        f"  · lenses  — линзы/методы, через которые фигура думает (напр.: [инверсия, memento-mori])\n"
        f"  · domains — области, где её совет весомее (напр.: [стратегия, этика])\n"
        f"Без них diversity_check судить состав не может (эхо-камера vs разнообразие).\n"
        f"\n## Конституция (от 1-го лица, ядро голоса)\n"
        f"_(во что фигура верит и как держит себя — оставлено для заполнения)_\n"
        f"\n## Как спорит (риторика)\n"
        f"_(манера рассуждения: какими ходами, вопросами, приёмами — оставлено для заполнения)_\n"
        f"\n## Чего не делает (never_do)\n"
        f"_(чего фигура точно НЕ советует)_\n"
        f"never_quote: _(явно перечисли известные ФЕЙК-цитаты этой фигуры — защита рва от коллажей)_\n"
        f"\n## Quote bank (🔵)\n"
        f"_(дословные цитаты из PD-корпуса — контур проверит их на 🔵; источник и тиры в `sources/manifest.json`)_\n"
        f"\n## Где challenge-ит\n"
        f"_(под какую задачу пользователя эта фигура даёт контр-голос)_\n"
    )


def next_step(pf):
    """Приоритетная следующая сборка по preflight. {action, why, say} — что/зачем (why: техн. лог)
    и `say`: то же человеческим языком для не-технического юзера (хост показывает ЕГО, не why)."""
    if not pf["principis"]["ok"]:
        return {"action": "principis",
                "why": "без модели тебя совет — разовый оракул; собери Принцепс первым",
                "say": "Давай сначала настрою совет под тебя — пара вопросов, и он будет советовать "
                       "именно тебе, а не вообще."}
    advisors = pf.get("advisors", [])
    if not any(a.get("has_corpus") for a in advisors):
        return {"action": "add-advisor",
                "why": "нет ни одного грунтованного советника — добавь корпус (его слова = 🔵)",
                "say": "Пока в совете нет ни одного советника с текстами. Кого позовём — и где взять "
                       "его слова (вставишь текст / дашь ссылку)?"}
    grounded = [a for a in advisors if a.get("has_corpus")]
    no_blue = [a for a in grounded if not a.get("blue_eligible")]
    if no_blue:
        return {"action": "fix-tiers",
                "why": f"{no_blue[0]['name']}: корпус есть, но нет P1/P2 — 🔵 невозможен, проверь манифест тиров",
                "say": f"Советник «{no_blue[0]['name']}» почти готов — докручиваю за тебя, секунду."}
    no_kernels = [a for a in grounded if not a.get("has_kernels")]
    if no_kernels:
        return {"action": "build-kernels",
                "why": f"{no_kernels[0]['name']}: нет кернелов (метод советника) — собери из корпуса",
                "say": f"Советник «{no_kernels[0]['name']}» почти готов — собираю его подход, секунду."}
    return {"action": "ready",
            "why": "доска готова к созыву; для петли U1 закрывай висящие ИСХОДЫ (pending_outcomes)",
            "say": "Совет готов — спрашивай что угодно, я соберу нужных советников."}
