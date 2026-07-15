#!/usr/bin/env python3
"""Перевешивает ли русский язык INSTRUCTIONS одну строку Правила 7 («Подача: язык юзера»)?

Рантайм НЕ импортирует этот модуль — инструмент, как соседние пробы. Ноль правок контура.

ЗАЧЕМ. INSTRUCTIONS в scripts/mcp_server.py — ЕДИНСТВЕННЫЙ текст, который хост (Claude Code)
читает при initialize; по нему он ведёт себя у юзера. Он ~20к символов и ~80% кириллицы, а
требование «отвечай на языке юзера» — ОДНА строка Правила 7. Гипотеза владельца: правило есть →
англоязычный юзер получит английский ответ. Контр-гипотеза: язык инструкций — сильный прайор,
80% русского перевесят одну строку, англоязычный юзер получит русский или смешанный ответ, и это
тихо убивает дистрибуцию. Не проверялось НИ РАЗУ: весь догфуд русский.

КАЛИБРОВКА (без неё замер нечитаем — урок оплачен трижды за сессию: прибор врёт уверенным
числом). Две страты-контроля, обе обязаны отработать, иначе вывод по английской страте
АННУЛИРУЕТСЯ, а не толкуется:
  • контроль 1 (ru_with)  — русский вопрос + те же INSTRUCTIONS. Обязан дать РУССКИЙ ответ.
    Дал английский → модель игнорирует и правило, и язык вопроса; прибор ничего не мерит.
  • контроль 2 (en_bare)  — тот же английский вопрос БЕЗ INSTRUCTIONS (пустой контур). Обязан
    дать АНГЛИЙСКИЙ ответ — это базовый язык модели. Если и с INSTRUCTIONS, и без них ответ
    английский, INSTRUCTIONS ни при чём и эффекта нет; если БЕЗ них ответ русский — эффект
    вообще не наш, приписать его правилу нельзя.
Оба контроля прошли → и только тогда en_with читается как факт о Правиле 7.

ЧЕСТНАЯ ОГОВОРКА О ВЕРНОСТИ КАНАЛА. llm_local.generate шлёт ОДНО user-сообщение (system-роли в
фасаде нет), а настоящий хост получает INSTRUCTIONS как server instructions при initialize, т.е.
системным контекстом. Проба кладёт тот же текст префиксом в user-turn — ближайшее доступное
приближение, не тождество. Направление ошибки НЕ известно заранее, поэтому нулевой результат
здесь не доказывает нуля на настоящем хосте; положительный (ответ уехал в русский) — доказывает,
что прайор такой силы существует.

ПОРОГИ. Ответ «английский» при доле кириллицы < 10%: запас не нулевой намеренно — Правило 7 само
требует 🔵-цитату дословно в оригинале + перевод-глоссу, поэтому короткая русская цитата внутри
английского ответа ЗАКОННА и не должна опрокидывать категорию. «Русский» при > 50%: большинство
букв кириллицей = тело ответа русское. Между — «смешанный»: это САМОСТОЯТЕЛЬНАЯ категория
провала для дистрибуции (англоязычный юзер получил кашу), в успех НЕ округляется.

Приватность: вопросы нейтральные, слаги частных советников в код/результат не попадают.

Живой прогон: --run (нужен OPENROUTER_API_KEY). Офлайн-тесты бьют чистые функции.
"""
import argparse
import datetime
import json
import os
import re
import sys
from collections import Counter

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPTS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RESULTS_DIR = os.path.join(HERE, "results")
DEFAULT_MODELS = "openai/gpt-4.1,z-ai/glm-5.2"   # пара, отработавшая в Tier-2 догфуде
GEN_TEMPERATURE = 0.3
DEFAULT_N = 8
EXCERPT_CHARS = 400          # в результат идёт огрызок ответа — глазами проверить категорию
CALIB_SUPERMAJORITY = 0.75   # контроль засчитан, только если страта отработала уверенно

# Пороги категорий. Обоснование — в докстринге модуля (запас под 🔵-глоссу; «смешанный» = провал).
THRESH_EN = 0.10
THRESH_RU = 0.50

_CYR = re.compile(r"[А-Яа-яЁё]")
_LAT = re.compile(r"[A-Za-z]")

# Реалистичные обращения к совету советников, парные по смыслу. Нейтральные: ни одного имени и
# ни одного слага из приватных корпусов (их печатает doctor — наружу они не идут никогда).
_PAIRS = [
    ("pricing", "Should I raise prices for my SaaS?",
     "Стоит ли поднять цены на мой SaaS?"),
    ("cofounder", "My co-founder wants to leave the company. How should I handle it?",
     "Мой сооснователь хочет уйти из компании. Как мне поступить?"),
    ("funding", "Should I raise outside money or keep bootstrapping?",
     "Брать деньги инвесторов или продолжать расти на свои?"),
    ("raise", "A key engineer is demanding a large raise or he walks. Do I give in?",
     "Ключевой инженер требует большую прибавку, иначе уйдёт. Уступать?"),
    ("copycat", "A bigger competitor copied my product feature for feature. What now?",
     "Более крупный конкурент скопировал мой продукт фича в фичу. Что теперь?"),
    ("burnout", "I am burning out running this company. What should I change first?",
     "Я выгораю, управляя этой компанией. Что менять в первую очередь?"),
    ("firing", "Should I fire a loyal manager who is no longer good at the job?",
     "Увольнять ли лояльного менеджера, который больше не тянет работу?"),
    ("pivot", "Growth has been flat for eighteen months. Is it time to pivot?",
     "Роста нет восемнадцать месяцев. Пора делать пивот?"),
]


def load_instructions():
    """INSTRUCTIONS ИЗ ПРОДУКТОВОГО КОДА, не копией. Копия разошлась бы с продуктом, и проба
    замерила бы саму себя."""
    import mcp_server
    return mcp_server.INSTRUCTIONS


def cyrillic_share(text):
    """Доля кириллицы среди БУКВ. Ноль букв → None: доли не существует, и выдать тут 0.0
    значило бы соврать «английский» на ответе, где текста нет."""
    if not text:
        return None
    cyr, lat = len(_CYR.findall(text)), len(_LAT.findall(text))
    if cyr + lat == 0:
        return None
    return cyr / (cyr + lat)


def categorize(share):
    """Доля → english | mixed | russian | None. Пороги и их обоснование — в докстринге модуля."""
    if share is None:
        return None
    if share < THRESH_EN:
        return "english"
    if share > THRESH_RU:
        return "russian"
    return "mixed"


def build_battery(n=DEFAULT_N):
    return [{"id": pid, "en": en, "ru": ru} for pid, en, ru in _PAIRS[:n]]


def build_prompt(question, with_instructions):
    """Плечи различаются РОВНО наличием INSTRUCTIONS (тест стережёт). Ни слова инструкции от
    себя: любая наша приписка стала бы вторым прайором и смазала бы замер."""
    if not with_instructions:
        return question
    return f"{load_instructions()}\n\n{question}"


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


def run_stratum(battery, lang, with_instructions, model, call=None):
    """Страта = (язык вопроса × наличие INSTRUCTIONS). Упавший вызов → withheld, НЕ догадка:
    молчание модели нельзя засчитать ни в один язык."""
    call = call or _default_call
    rows = []
    for item in battery:
        prompt = build_prompt(item[lang], with_instructions)
        try:
            raw = call(prompt, model)
        except Exception:
            raw = None
        share = cyrillic_share(raw)
        rows.append({"id": item["id"], "withheld": raw is None, "share": share,
                     "category": categorize(share),
                     "excerpt": (raw or "")[:EXCERPT_CHARS]})
    return rows


def dominant(rows):
    """Преобладающая категория страты + её доля. Withheld отброшены — они не голосуют."""
    cats = [r["category"] for r in rows if r.get("category")]
    if not cats:
        return {"label": None, "share": None, "n": 0}
    label, cnt = Counter(cats).most_common(1)[0]
    return {"label": label, "share": cnt / len(cats), "n": len(cats)}


def mean_share(rows):
    vals = [r["share"] for r in rows if r.get("share") is not None]
    return sum(vals) / len(vals) if vals else None


def calibration_verdict(ru_with_rows, en_bare_rows):
    """Отработали ли ОБА контроля. Не отработали → «ПРИБОР СЛЕП», и вывод по en_with
    аннулируется. Это не формальность: слепой прибор выдаёт уверенное число ни о чём."""
    reasons = []
    ru_dom, bare_dom = dominant(ru_with_rows), dominant(en_bare_rows)

    def _fired(dom, want):
        return dom["label"] == want and dom["share"] >= CALIB_SUPERMAJORITY

    if not _fired(ru_dom, "russian"):
        reasons.append(
            f"контроль 1 (русский вопрос + INSTRUCTIONS) не отработал: ожидался русский ответ, "
            f"получено «{ru_dom['label']}» на {ru_dom['n']} замерах "
            f"(доля {ru_dom['share']}). Модель игнорирует и правило, и язык вопроса — "
            f"мерить нечем, вывод по английской страте аннулируется.")
    if not _fired(bare_dom, "english"):
        reasons.append(
            f"контроль 2 (английский вопрос БЕЗ INSTRUCTIONS) не отработал: ожидался английский "
            f"ответ, получено «{bare_dom['label']}» на {bare_dom['n']} замерах "
            f"(доля {bare_dom['share']}). Базовый язык модели не английский — приписать "
            f"эффект INSTRUCTIONS нельзя.")
    ok = not reasons
    return {"sensitive": ok, "label": "ПРИБОР ЧУВСТВИТЕЛЕН" if ok else "ПРИБОР СЛЕП",
            "reasons": reasons, "control_ru_with": ru_dom, "control_en_bare": bare_dom}


def rule7_verdict(en_with_rows, calib):
    """Вердикт словами. works: True | False | None (None = прибор слеп, факта нет)."""
    dom = dominant(en_with_rows)
    if not calib["sensitive"]:
        return {"works": None, "dominant": dom,
                "text": "ВЫВОД АННУЛИРОВАН: прибор слеп — " + " ".join(calib["reasons"])}
    share = dom["share"]
    if dom["label"] == "english" and share >= CALIB_SUPERMAJORITY:
        return {"works": True, "dominant": dom,
                "text": f"Правило 7 РАБОТАЕТ на английском пути: {share:.0%} ответов "
                        f"английские при русских INSTRUCTIONS. Переводить контур не требуется."}
    if dom["label"] == "russian":
        return {"works": False, "dominant": dom,
                "text": f"Правило 7 НЕ РАБОТАЕТ: {share:.0%} ответов на английский вопрос "
                        f"пришли по-русски. Язык INSTRUCTIONS перевесил строку правила — "
                        f"англоязычный юзер получает русский ответ."}
    return {"works": False, "dominant": dom,
            "text": f"Правило 7 держит НЕНАДЁЖНО: преобладает «{dom['label']}» "
                    f"({share:.0%}), уверенного английского нет. СМЕШАННЫЙ ответ — "
                    f"провал для дистрибуции, а не почти-успех."}


def run_model(battery, model, call=None):
    strata = {
        "en_with": run_stratum(battery, "en", True, model, call),    # ← главный замер
        "ru_with": run_stratum(battery, "ru", True, model, call),    # ← контроль 1
        "en_bare": run_stratum(battery, "en", False, model, call),   # ← контроль 2
    }
    calib = calibration_verdict(strata["ru_with"], strata["en_bare"])
    return {"model": model,
            "strata": {k: {"rows": v, "mean_cyrillic_share": mean_share(v),
                           "dominant": dominant(v),
                           "categories": dict(Counter(r["category"] for r in v))}
                       for k, v in strata.items()},
            "calibration": calib,
            "verdict": rule7_verdict(strata["en_with"], calib)}


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Перевешивает ли русский язык INSTRUCTIONS Правило 7 (изолировано)")
    p.add_argument("--run", action="store_true", help="живой прогон (нужен OPENROUTER_API_KEY)")
    p.add_argument("--models", default=DEFAULT_MODELS)
    p.add_argument("--n", type=int, default=DEFAULT_N, help="парных вопросов (макс 8)")
    p.add_argument("--out", default=os.path.join(RESULTS_DIR, "instructions-language.json"))
    a = p.parse_args(argv)
    bat = build_battery(a.n)
    instr = load_instructions()
    if not a.run:
        print(f"Сухой режим. INSTRUCTIONS: {len(instr)} символов, "
              f"{cyrillic_share(instr):.1%} кириллицы. Батарея: {len(bat)} парных вопросов "
              f"× 3 страты (en_with / ru_with=контроль1 / en_bare=контроль2). "
              f"Живой прогон: --run.")
        print("Без обоих контролей вывод по английской страте АННУЛИРУЕТСЯ — прибор слеп, "
              "а не «всё хорошо».")
        return 0
    if not _load_key_from_dotenv():
        print("НЕТ OPENROUTER_API_KEY (ни в env, ни в .env). Экспортируй ключ и повтори.",
              file=sys.stderr)
        return 2
    # Как во ВСЕХ соседних пробах: без этого llm_local уходит в ollama (её дефолт) и бьёт
    # 404 на api-именах моделей — вызовы молча уходят в withheld, прогон пустой.
    os.environ["LLM_BACKEND"] = "openrouter"
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "instructions_chars": len(instr),
           "instructions_cyrillic_share": cyrillic_share(instr),
           "thresholds": {"english_below": THRESH_EN, "russian_above": THRESH_RU,
                          "calibration_supermajority": CALIB_SUPERMAJORITY},
           "battery_n": len(bat), "models": []}
    for model in [m for m in a.models.split(",") if m]:
        print(f"\n=== {model} ===", flush=True)
        entry = run_model(bat, model)
        for name in ("en_with", "ru_with", "en_bare"):
            s = entry["strata"][name]
            ms = s["mean_cyrillic_share"]
            print(f"  {name:8s} кириллица {('%.1f%%' % (ms * 100)) if ms is not None else 'н/д':>6s}"
                  f"  {s['categories']}")
        print(f"  калибровка: {entry['calibration']['label']}")
        print(f"  вердикт: {entry['verdict']['text']}")
        out["models"].append(entry)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n→ {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
