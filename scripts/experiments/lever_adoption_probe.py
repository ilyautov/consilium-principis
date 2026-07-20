#!/usr/bin/env python3
"""Эксплуатируем ли градиент near-verbatim: три плеча + замер контаминации (слой 2).

Рантайм НЕ импортирует этот модуль — инструмент, как соседние пробы. Ноль правок контура.

ЗАЧЕМ. Замерено (d2b4ab3): near-verbatim-запросы достают нужный пассаж ВПЯТЕРО лучше
тематических. Открытый вопрос — можно ли этим ПОЛЬЗОВАТЬСЯ. Прецедент проекта злой:
анти-сикофантика (22fb587) — мягкий prompt-нудж дал ЧИСТЫЙ НОЛЬ, вывод был «рычаг =
детерминированный тул, НЕ текст». Пока эффект не измерен, «внедрено» — вера, а не факт.

ТРИ ПЛЕЧА, различаются РОВНО своим отличительным текстом (тест стережёт):
  • base   — хост формулирует запросы к cite как обычно;
  • lever  — плюс абзац LEVER_TEXT (то, что ушло в INSTRUCTIONS Rule 5, cfdb55a): «формулируй,
             как звучала бы сама цитата». Просит невозможного: чтобы так сформулировать, надо
             цитату уже знать;
  • hyde   — HyDE (Gao et al. 2022): модель СОЧИНЯЕТ псевдоцитату голосом советника, ретрив
             идёт по ней. Кодовая версия механизма, снимает курицу-яйцо.
Язык корпуса — во ВСЕХ плечах (уже валидированный лифт; иначе померим его, а не механизм).
Парно по вопросу, bootstrap-CI на дельте (DRY из antisycophancy_probe).

КОНФАУНД ЭРУДИЦИИ И КАК ОН СНЯТ (требование Ильи, 2026-07-15). Знаменитый якорь модель может
знать наизусть → «успех ретрива» окажется памятью, а не поиском. Труъ-неизвестного советника
не бывает: всё, что мы вправе шипить, — public domain, а он весь в обучающей выборке. Поэтому
контаминацию не гадаем по «знаменитый/безвестный», а МЕРЯЕМ поимённо закрытой книгой (без
корпуса) и стратифицируем эффект по факту: лифт на memorized = эрудиция, на fresh = механизм.
Знание — свойство не советника, а конкретного пассажа.

КАЛИБРОВКА ПРИБОРА. Замер контаминации сам может быть слеп: если модель в принципе не отвечает
дословными цитатами, закрытая книга всегда скажет «не зазубрено», и страта fresh окажется не
фактом, а молчанием модели. Поэтому MEMORIZATION_CONTROLS — заведомо зазубренные строки ВНЕ
наших корпусов (Гамлет, Мелвилл, Диккенс, Остин, Джефферсон). 0 срабатываний = прибор слеп и
кричит об этом; вывод по стратам аннулируется.

Живой прогон: --run (нужен OPENROUTER_API_KEY). Офлайн-тесты бьют чистые функции.
"""
import argparse
import datetime
import json
import os
import re
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, HERE)

from antisycophancy_probe import _bootstrap_ci, _mean, SEED, _safe_call  # noqa: E402
from tier_pool_probe import anchor_rank, blue_share, has_blue, load_golden, _norm  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")
DEFAULT_MODELS = "openai/gpt-4.1,z-ai/glm-5.2"   # пара, отработавшая в Tier-2 догфуде
GEN_TEMPERATURE = 0.3
MAX_QUERIES = 4
DEFAULT_K = 8
MIN_N = 8

# Рычаг — ДОСЛОВНО смысл того, что ушёл в INSTRUCTIONS Rule 5 (cfdb55a). Меняется там —
# меняется здесь, иначе A/B проверяет не то, что шипнуто.
LEVER_TEXT = (
    "Формулируй так, как ЗВУЧАЛА БЫ САМА ЦИТАТА, а не как тему: тематический запрос ловит "
    "того, кто пишет о предмете прямым текстом (комментатора), а советник говорит косвенно "
    "и метафорично — его достаёт запрос, похожий на его собственную речь."
)

DEFAULT_LANG = "English"        # язык шипнутых PD-корпусов; частные бывают другими

_BASE_PROMPT = """Ты — хост совета советников. Юзер задал вопрос советнику.
Твоя задача: сформулировать поисковые запросы к инструменту cite, который ищет ДОСЛОВНЫЕ
цитаты советника в корпусе его подлинных текстов.

Вопрос юзера: {question}

Запросы давай в ЯЗЫКЕ КОРПУСА ({lang}) — корпус на этом языке.
Можно 2-4 формулировки-перефразировки: находок больше.
{lever}
Ответь СТРОГО JSON, без пояснений: {{"queries": ["...", "..."]}}"""


def build_prompt(question, lever=False, lang=DEFAULT_LANG):
    return _BASE_PROMPT.format(question=question, lang=lang,
                               lever=(LEVER_TEXT + "\n") if lever else "")


# HyDE (Gao et al. 2022) — КОДОВАЯ версия механизма. Рычаг-текст провалился, потому что требовал
# от хоста невозможного: чтобы сформулировать «как звучала бы цитата», надо цитату уже знать
# (golden literal-вопросы звучат near-verbatim ровно потому, что gen_golden ВИДЕЛ пассаж).
# HyDE снимает курицу-яйцо: модель не вспоминает точный текст, а СОЧИНЯЕТ правдоподобную фразу
# в стиле советника — стилистическое сходство и тащит ретрив к подлиннику, а не к комментатору.
_HYDE_PROMPT = """Ты пишешь в стиле мыслителя по имени {advisor}.

Вопрос: {question}

Сочини 2-4 коротких высказывания НА ЯЗЫКЕ КОРПУСА ({lang}), как мог бы сказать {advisor} —
его голосом, его эпохой, его манерой (косвенно, через образ, без современной лексики).
НЕ пытайся вспомнить точную цитату и не ссылайся на источник: сочиняй правдоподобное.

Ответь СТРОГО JSON, без пояснений: {{"queries": ["...", "..."]}}"""

# Контаминация: может ли модель выдать пассаж ЗАКРЫТОЙ КНИГОЙ, без корпуса? Если да — на этом
# пункте «успех ретрива» может быть эрудицией, а не поиском. Меряем поимённо, а не гадаем
# «знаменитый/безвестный»: Илья прав — все наши PD-советники зазубрены обучающей выборкой.
_CLOSED_BOOK_PROMPT = """Ты знаешь тексты автора по имени {advisor}.

Вопрос: {question}

Приведи ДОСЛОВНУЮ цитату из его подлинных текстов, отвечающую на этот вопрос, на английском.
Если точной цитаты не помнишь — честно верни пустой список, НЕ сочиняй.

Ответь СТРОГО JSON, без пояснений: {{"queries": ["дословная цитата"]}}"""

# ТОЛЬКО public-domain советники — файл коммитится. Имена частных советников в код НЕ пишем
# (гард в тестах): они приезжают через env PROBE_ADVISOR_NAMES='{"slug": "Имя"}' — живут в
# команде Ильи, репозиторий о них не знает.
ADVISOR_NAMES = {"machiavelli": "Niccolò Machiavelli",
                 "marcus-aurelius": "Marcus Aurelius",
                 "sun-tzu": "Sun Tzu"}


def advisor_name(slug):
    try:
        env = json.loads(os.getenv("PROBE_ADVISOR_NAMES") or "{}")
    except Exception:
        env = {}
    return env.get(slug) or ADVISOR_NAMES.get(slug, slug)

# ПОЗИТИВНЫЙ КОНТРОЛЬ прибора контаминации. Без него замер невозможно истолковать: если модель
# в принципе не выдаёт дословных цитат (RLHF отучил, промпт душит, парсер ест) — закрытая книга
# всегда ответит «не зазубрено», и страта fresh окажется не фактом, а слепотой прибора.
# Строки заведомо зазубренные и ВНЕ наших корпусов: прибор проверяется независимо от предмета.
MEMORIZATION_CONTROLS = [
    {"advisor": "William Shakespeare", "anchor": "to be or not to be",
     "question": "Чем начинается самый известный монолог Гамлета о жизни и смерти?"},
    {"advisor": "Herman Melville", "anchor": "call me ishmael",
     "question": "Какими словами начинается роман Мелвилла о белом ките?"},
    {"advisor": "Charles Dickens", "anchor": "it was the best of times",
     "question": "Какими словами открывается роман Диккенса о Лондоне и Париже эпохи революции?"},
    {"advisor": "Jane Austen", "anchor": "a truth universally acknowledged",
     "question": "Какой фразой открывается роман Остин о мистере Дарси и семействе Беннет?"},
    {"advisor": "Thomas Jefferson", "anchor": "we hold these truths to be self-evident",
     "question": "С какой фразы начинается перечисление неотъемлемых прав в Декларации "
                 "независимости США?"},
]


ARMS = ("base", "lever", "hyde")


def build_hyde_prompt(question, advisor, lang=DEFAULT_LANG):
    return _HYDE_PROMPT.format(question=question, lang=lang, advisor=advisor_name(advisor))


def build_arm_prompt(item, arm):
    """Опечатка в имени плеча обязана падать, а не молча давать базу: два одинаковых плеча
    дадут «ноль», которого мы не мерили."""
    lang = item.get("lang", DEFAULT_LANG)
    if arm == "base":
        return build_prompt(item["question"], lever=False, lang=lang)
    if arm == "lever":
        return build_prompt(item["question"], lever=True, lang=lang)
    if arm == "hyde":
        return build_hyde_prompt(item["question"], item["advisor"], lang=lang)
    raise ValueError(f"неизвестное плечо: {arm!r} (есть {ARMS})")


def build_closed_book_prompt(question, advisor):
    return _CLOSED_BOOK_PROMPT.format(question=question, advisor=advisor_name(advisor))


def is_memorized(closed_book_queries, anchor):
    """Модель выдала якорь БЕЗ корпуса → пункт контаминирован эрудицией. Тот же hit-критерий,
    что везде: нормализованный anchor ⊂ нормализованного текста."""
    na = _norm(anchor)
    return bool(na) and any(na in _norm(q) for q in closed_book_queries or [])


def calibration_verdict(hits):
    """Чувствителен ли прибор контаминации. hits = [bool] по позитивным контролям.

    Ноль срабатываний на заведомо зазубренном = прибор слеп, и страта fresh недействительна:
    мы намеряли не «модель этого не знает», а «модель не отвечает цитатами». Молчать об этом
    нельзя — иначе слепота прибора выдаст себя за результат.
    """
    live = [h for h in hits if h is not None]
    n = len(live)
    if not n:
        return {"sensitive": None, "text": "КАЛИБРОВКИ НЕТ: контроли не отработали."}
    ok = sum(1 for h in live if h)
    if ok == 0:
        return {"sensitive": False,
                "text": f"ПРИБОР СЛЕП: 0/{n} заведомо зазубренных строк не воспроизведены. "
                        f"Страта fresh НЕДЕЙСТВИТЕЛЬНА — она меряет молчание модели, "
                        f"а не отсутствие памяти."}
    if ok * 2 > n:   # строгое большинство
        return {"sensitive": True,
                "text": f"ПРИБОР ЧУВСТВИТЕЛЕН: {ok}/{n} контролей воспроизведены дословно."}
    return {"sensitive": None,
            "text": f"ПРИБОР ЧАСТИЧНО ЧУВСТВИТЕЛЕН: {ok}/{n}. Вывод по стратам ослаблен: "
                    f"часть «не зазубрено» может быть промахом прибора."}


def parse_queries(raw):
    """Мусор/None → [] (withheld), не падение платного прогона.

    Целимся в МАССИВ queries, а не в объект целиком: glm-5.2 на длинных ответах закрывает
    массив, но теряет `}`. Строгий разбор `{...}` съедал 15 валидных ответов из 25 и отдавал
    их в withheld — плечо HyDE получало смещённую выборку и ложный вердикт «вредит».
    Хрупкость парсера превращается в выдумку про поведение модели.
    Толерантность строго ограничена: нет массива queries → [], прозу в запросы не производим.
    """
    if not raw or not isinstance(raw, str):
        return []
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    m = re.search(r'"queries"\s*:\s*(\[.*?\])', s, re.S)
    if not m:
        return []
    try:
        qs = json.loads(m.group(1))
    except Exception:
        return []
    if not isinstance(qs, list):
        return []
    out = []
    for q in qs:
        if isinstance(q, str) and q.strip():
            out.append(q.strip())
    return out[:MAX_QUERIES]


def pool_hits(queries, retrieve_fn, k=DEFAULT_K):
    """Мульти-запрос как в cite: объединить, дедуп по тексту (лучший скор), по убыванию."""
    best = {}
    for q in queries:
        for h in retrieve_fn(q, k) or []:
            key = _norm(h.get("text", ""))
            if not key:
                continue
            if key not in best or h.get("score", 0) > best[key].get("score", 0):
                best[key] = h
    pool = sorted(best.values(), key=lambda h: h.get("score", 0), reverse=True)
    return pool[:k]


def summarize_arm(rows, k=DEFAULT_K):
    """withheld НЕ считаем провалом рычага — иначе сеть двигает вывод в пользу нуля."""
    withheld = sum(1 for r in rows if r.get("withheld"))
    live = [r for r in rows if not r.get("withheld")]
    n = len(live)
    if not n:
        return {"n": 0, "withheld": withheld, "anchor_hit": None, "anchor_mrr": None, "k": k}
    ranks = [r["anchor_rank"] for r in live]
    return {"n": n, "withheld": withheld, "k": k,
            "anchor_hit": sum(1 for r in ranks if r is not None and r <= k) / n,
            "anchor_mrr": sum((1.0 / r) if (r is not None and r <= k) else 0.0
                              for r in ranks) / n,
            "blue_share_mean": _mean([r.get("blue_share") for r in live])}


def verdict(ci, n, arm="lever"):
    """Урок анти-сикофантики: CI, накрывающий 0, — это НОЛЬ, а не «тенденция к росту»."""
    if n < MIN_N:
        return {"adopted": None, "text": f"ВЕРДИКТА НЕТ: n={n} < {MIN_N}."}
    if ci is None:
        return {"adopted": None, "text": "ВЕРДИКТА НЕТ: CI не посчитан."}
    if ci["lo"] > 0:
        return {"adopted": True,
                "text": f"ЭФФЕКТ ЕСТЬ: Δ={ci['mean']:+.3f}, CI95 [{ci['lo']:+.3f}, "
                        f"{ci['hi']:+.3f}] исключает 0."}
    if ci["hi"] < 0:
        return {"adopted": False,
                "text": f"ПЛЕЧО ВРЕДИТ: Δ={ci['mean']:+.3f}, CI95 [{ci['lo']:+.3f}, "
                        f"{ci['hi']:+.3f}] ниже 0."}
    # Хвост про «мягкий нудж» — только для текстового рычага: HyDE не нудж, а другой вызов.
    tail = (" — как анти-сикофантика (22fb587). Мягкий текстовый нудж поведение не двигает."
            if arm == "lever" else ".")
    return {"adopted": False,
            "text": f"НОЛЬ (не отличим от нуля): Δ={ci['mean']:+.3f}, CI95 [{ci['lo']:+.3f}, "
                    f"{ci['hi']:+.3f}] накрывает 0{tail}"}


# ------------------------------------------------------------------ батарея

DEFAULT_ADVISORS = ("machiavelli", "marcus-aurelius")


def build_battery(slugs=DEFAULT_ADVISORS, lang=DEFAULT_LANG):
    """[{id, advisor, question, anchor, setting, lang}] из golden. Ручного retrieval-набора у
    частных советников нет — load_golden отдаёт [], батарея просто выходит из одних auto."""
    bat = []
    for slug in slugs:
        for r in load_golden(slug, "retrieval"):        # RU-вопрос, знаменитый якорь
            if r.get("q") and r.get("anchor"):
                bat.append({"id": f"{slug}:hand:{len(bat)}", "advisor": slug, "lang": lang,
                            "question": r["q"], "anchor": r["anchor"], "setting": "hand_ru"})
        for r in load_golden(slug, "auto"):             # вопрос в языке корпуса, БЕЗВЕСТНЫЙ якорь
            if r.get("difficulty") == "abstract" and r.get("q") and r.get("anchor"):
                bat.append({"id": f"{slug}:auto:{len(bat)}", "advisor": slug, "lang": lang,
                            "question": r["q"], "anchor": r["anchor"],
                            "setting": "auto_abstract"})
    return bat


def _load_key_from_dotenv():
    """OPENROUTER_API_KEY из .env, НЕ печатая значение. Env приоритетнее. llm_local читает
    окружение, а ключ живёт в .env (gitignored) → без этого моста api_available()=False."""
    if os.getenv("OPENROUTER_API_KEY"):
        return True
    envp = os.path.join(_SCRIPTS, "..", ".env")
    if not os.path.isfile(envp):
        return False
    with open(envp, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("OPENROUTER_API_KEY="):
                os.environ["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                return True
    return False


def _default_call(prompt, model):
    import llm_local
    return llm_local.generate(prompt, model=model, temperature=GEN_TEMPERATURE)


def run_arm(battery, arm, model, call=None, k=DEFAULT_K):
    import eval as _eval
    call = call or _default_call
    rows = []
    for item in battery:
        adv = os.path.join(_SCRIPTS, "..", "advisors", item["advisor"])
        raw = _safe_call(lambda p: call(p, model), build_arm_prompt(item, arm))
        qs = parse_queries(raw)
        if not qs:
            rows.append({"id": item["id"], "setting": item["setting"], "anchor_rank": None,
                         "withheld": True, "queries": []})
            continue
        pool = pool_hits(qs, lambda q, kk: _eval.retrieve(q, adv, top_k=kk), k=k)
        rows.append({"id": item["id"], "setting": item["setting"], "queries": qs,
                     "anchor_rank": anchor_rank(pool, item["anchor"]),
                     "blue_share": blue_share(pool), "has_blue": has_blue(pool)})
    return rows


def run_closed_book(battery, model, call=None):
    """{id: True|False|None} — знает ли модель ЭТОТ пассаж наизусть, без корпуса.
    None = вызов не состоялся: страту не гадаем, пункт выбывает."""
    call = call or _default_call
    memo = {}
    for item in battery:
        raw = _safe_call(lambda p: call(p, model),
                         build_closed_book_prompt(item["question"], item["advisor"]))
        if raw is None:
            memo[item["id"]] = None
            continue
        memo[item["id"]] = is_memorized(parse_queries(raw), item["anchor"])
    return memo


def _hit(r, k):
    return None if r.get("withheld") else (
        1.0 if (r["anchor_rank"] is not None and r["anchor_rank"] <= k) else 0.0)


def paired_ci(base_rows, lever_rows, k=DEFAULT_K):
    b = {r["id"]: _hit(r, k) for r in base_rows}
    t = {r["id"]: _hit(r, k) for r in lever_rows}
    deltas = [t[i] - b[i] for i in b if b.get(i) is not None and t.get(i) is not None]
    ci = _bootstrap_ci(deltas)
    if ci is None:
        return None, len(deltas)
    lo, hi = ci if isinstance(ci, (tuple, list)) else (ci["lo"], ci["hi"])
    return {"lo": lo, "hi": hi, "mean": _mean(deltas)}, len(deltas)


def run_controls(model, call=None):
    """Позитивный контроль: ловит ли закрытая книга заведомо зазубренное. → ([bool|None], verdict)"""
    call = call or _default_call
    hits = []
    for c in MEMORIZATION_CONTROLS:
        raw = _safe_call(lambda p: call(p, model),
                         build_closed_book_prompt(c["question"], c["advisor"]))
        hits.append(None if raw is None else is_memorized(parse_queries(raw), c["anchor"]))
    return hits, calibration_verdict(hits)


def stratify(base_rows, treat_rows, memo, k=DEFAULT_K, arm="lever"):
    """Расщепить эффект плеча по ИЗМЕРЕННОЙ контаминации.

    Требование Ильи: не дать эрудиции обучающей выборки подделать результат. «Неизвестного»
    PD-советника не существует, зато существует незазубренный ПАССАЖ — вот его и берём за
    честную страту. Лифт только на memorized = мы померили память модели, не механизм.
    """
    out = {}
    for name, want in (("memorized", True), ("fresh", False)):
        ids = {i for i, m in memo.items() if m is want}
        ci, n = paired_ci([r for r in base_rows if r["id"] in ids],
                          [r for r in treat_rows if r["id"] in ids], k)
        out[name] = {"ci": ci, "n_paired": n, "verdict": verdict(ci, n, arm)}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="A/B адопции рычага near-verbatim (изолировано)")
    p.add_argument("--run", action="store_true", help="живой прогон (нужен OPENROUTER_API_KEY)")
    p.add_argument("--models", default=DEFAULT_MODELS)
    p.add_argument("--top-k", type=int, default=DEFAULT_K)
    p.add_argument("--advisors", default=",".join(DEFAULT_ADVISORS),
                   help="слаги через запятую (частные — только локально, наружу не идут)")
    p.add_argument("--lang", default=DEFAULT_LANG, help="язык корпуса, напр. Russian")
    p.add_argument("--out", default=None,
                   help="путь результата. ДЕФОЛТ ПИШЕТ В КОММИТИМУЮ results/ — для частных "
                        "советников уводи вывод за пределы репозитория")
    a = p.parse_args(argv)
    slugs = [s for s in a.advisors.split(",") if s]
    bat = build_battery(slugs, a.lang)
    if not a.run:
        from collections import Counter
        print(f"Сухой режим. Батарея: {len(bat)} вопросов "
              f"{dict(Counter(i['setting'] for i in bat))}. Живой прогон: --run.")
        print("Меряет АДОПЦИЮ: следует ли хост подсказке. Прецедент — анти-сикофантика "
              "дала чистый ноль на мягком нудже.")
        return 0
    if not _load_key_from_dotenv():
        print("НЕТ OPENROUTER_API_KEY (ни в env, ни в .env). Экспортируй ключ и повтори.",
              file=sys.stderr)
        return 2
    # Как во ВСЕХ соседних пробах: без этого llm_local уходит в ollama (её дефолт) и бьёт
    # 404 на api-именах моделей — вызовы молча уходят в withheld, прогон пустой.
    os.environ["LLM_BACKEND"] = "openrouter"
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "top_k": a.top_k, "seed": SEED, "battery_n": len(bat), "models": []}
    for model in [m for m in a.models.split(",") if m]:
        print(f"\n=== {model} ===", flush=True)
        ctrl_hits, calib = run_controls(model)
        print(f"  калибровка: {calib['text']}")
        memo = run_closed_book(bat, model=model)
        known = sum(1 for v in memo.values() if v is True)
        measured = sum(1 for v in memo.values() if v is not None)
        print(f"  контаминация (закрытая книга): зазубрено {known}/{measured} пунктов")
        arms = {arm: run_arm(bat, arm, model=model, k=a.top_k) for arm in ARMS}
        entry = {"model": model, "memorized": known, "memorization_measured": measured,
                 "memo": memo, "calibration": {"hits": ctrl_hits, "verdict": calib},
                 "arms": {arm: summarize_arm(rows, a.top_k)
                          for arm, rows in arms.items()},
                 "vs_base": {}}
        for arm in ("lever", "hyde"):
            ci, n = paired_ci(arms["base"], arms[arm], a.top_k)
            entry["vs_base"][arm] = {
                "ci": ci, "n_paired": n, "verdict": verdict(ci, n, arm),
                "by_memorization": stratify(arms["base"], arms[arm], memo, a.top_k, arm),
                "by_setting": {}}
            for setting in ("hand_ru", "auto_abstract"):
                bs = [r for r in arms["base"] if r["setting"] == setting]
                ts = [r for r in arms[arm] if r["setting"] == setting]
                sci, sn = paired_ci(bs, ts, a.top_k)
                entry["vs_base"][arm]["by_setting"][setting] = {
                    "ci": sci, "n_paired": sn, "verdict": verdict(sci, sn, arm)}
        out["models"].append(entry)
        for arm in ARMS:
            s = entry["arms"][arm]
            print(f"  {arm:<6}: hit {s['anchor_hit']} MRR {s['anchor_mrr']} "
                  f"(withheld {s['withheld']})")
        for arm in ("lever", "hyde"):
            blk = entry["vs_base"][arm]
            print(f"  [{arm} vs base] {blk['verdict']['text']}")
            for strat in ("memorized", "fresh"):
                print(f"    ({strat}) {blk['by_memorization'][strat]['verdict']['text']}")
            for setting in ("hand_ru", "auto_abstract"):
                print(f"    [{setting}] {blk['by_setting'][setting]['verdict']['text']}")
    path = a.out or os.path.join(RESULTS_DIR,
                                 f"lever-adoption-{datetime.date.today().isoformat()}.json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n→ {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
