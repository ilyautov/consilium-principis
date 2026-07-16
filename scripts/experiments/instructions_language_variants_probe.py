#!/usr/bin/env python3
"""Чинит ли ТЕКСТОВЫЙ рычаг языковой прайор INSTRUCTIONS — и не ломает ли при этом русский путь?

Рантайм НЕ импортирует этот модуль — инструмент, как соседние пробы. Ноль правок контура:
варианты собираются ПАТЧЕМ поверх текста, взятого из scripts/mcp_server.py, продукт не меняется.

ЧТО УЖЕ ЗАМЕРЕНО (instructions_language_probe, results/instructions-language-2026-07-16.json).
INSTRUCTIONS — 20134 символа, 79.7% кириллицы; Правило 7 говорит «Подача: язык юзера» ОДНОЙ
строкой. Оно НЕ работает: английский вопрос → 75% русских ответов (gpt-4.1) и 57% (glm-5.2) при
чистой калибровке. Диагноз: модель не отличает язык ПРАВИЛ от языка ОТВЕТА — 20к кириллицы
читаются как заказ на русский вывод. Эта проба меряет, спасает ли дешёвая текстовая правка.

ПОЧЕМУ ОБЕ СТОРОНЫ. Правило 7 двустороннее. Плечо обязано (а) починить английский путь И
(б) НЕ сломать русский — это ежедневный путь владельца. Плечо, которое чинит EN ценой RU, —
ПРОВАЛ, а не победа, поэтому ru_with меряется на КАЖДОМ плече, а не только на baseline.
Односторонний замер («EN починился!») здесь — самый вероятный способ соврать себе.

ПЛЕЧИ
  baseline           INSTRUCTIONS как есть. Обязано воспроизвести ~75%/~57% русского; не
                     воспроизвелось — замер нестабилен и остальные плечи читать нельзя.
  ru_top             русский блок «язык ответа» в самое начало (до Правила 0).
  en_top             тот же блок по-английски.
  en_top_plus_rule7  en_top + замена самой строки Правила 7 на английскую формулировку.
  en_bottom          (наш пятый) тот же en_top-блок, но в КОНЕЦ INSTRUCTIONS. Обоснование:
                     остальные плечи меняют ЯЗЫК и ФОРМУЛИРОВКУ, но все — в одной позиции
                     (начало 20к текста). Позиция — отдельная переменная: у длинного контекста
                     начало и конец весят по-разному, и провал en_top не отличить от провала
                     «блок утонул в 20к». Плечо ничего не стоит сверх прогона, деплоится так же
                     (конец INSTRUCTIONS доступен на настоящем хосте), и разделяет две гипотезы:
                     «текст не помогает» против «текст не дочитан».

КАЛИБРОВКА. Наследуется из базовой пробы: контроль en_bare (английский вопрос БЕЗ INSTRUCTIONS,
обязан дать английский — это потолок и базовый язык модели) + контроль ru_with на baseline
(обязан дать русский). Не отработали — вывод по ВСЕМ плечам аннулируется, а не толкуется.

ЧЕСТНАЯ ОГОВОРКА О ВЕРНОСТИ КАНАЛА (та же, что в базовой пробе). llm_local.generate шлёт ОДНО
user-сообщение, а настоящий хост получает INSTRUCTIONS системным контекстом при initialize.
Проба кладёт текст префиксом в user-turn — ближайшее доступное приближение, не тождество.

WITHHELD НА ВИДУ + ПОЛ ВЫБОРКИ. Несостоявшийся замер → withheld, НЕ догадка; считается по «нет
доли» (упавший вызов И пустой ответ — пустой не роняет вызов, но из знаменателя выпадает так же).
Withheld печатается и кладётся в вердикт по каждому плечу. Сверх того — MIN_MEASURED: доля
считается по выжившим, поэтому 7 потерь + 1 английский дали бы «share 1.0, плечо работает» по
ОДНОМУ ответу. В этой сессии тихо выброшенные ответы уже давали уверенный ЛОЖНЫЙ вердикт, так что
оба гарда тут не паранойя, а оплаченный урок.

Приватность: вопросы нейтральные, слаги частных советников в код/тесты/результат не попадают.

Живой прогон: --run (нужен OPENROUTER_API_KEY). Офлайн-тесты бьют чистые функции.
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_SCRIPTS, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Метрика, пороги, батарея и калибровка — из базовой пробы, не копией: разойдутся копии —
# и два замера станут несравнимыми, а именно сравнение с baseline тут и есть предмет.
from instructions_language_probe import (  # noqa: E402
    CALIB_SUPERMAJORITY, DEFAULT_MODELS, DEFAULT_N, EXCERPT_CHARS, GEN_TEMPERATURE,
    THRESH_EN, THRESH_RU, _default_call, _load_key_from_dotenv, build_battery,
    calibration_verdict, categorize, cyrillic_share, dominant, load_instructions, mean_share,
    run_stratum,
)

RESULTS_DIR = os.path.join(HERE, "results")

# --- тексты плечей. Формулировки заданы владельцем дословно; не переписывать «чтобы лучше
# звучало»: тогда замер поедет по неизвестной причине, и результат нечего будет к чему приписать.

RU_TOP_BLOCK = (
    "ЯЗЫК ОТВЕТА (перекрывает оформление, но не Правило 0). Отвечай на языке ВОПРОСА юзера.\n"
    "Вопрос по-английски → весь ответ по-английски: заголовки, лейблы тиров, служебные подписи.\n"
    "ЭТИ ПРАВИЛА НАПИСАНЫ ПО-РУССКИ — это язык ПРАВИЛ, а не язык твоего ответа."
)

EN_TOP_BLOCK = (
    "RESPONSE LANGUAGE (overrides formatting; never overrides Rule 0). Answer in the language of the\n"
    "USER'S QUESTION. English question -> the entire answer in English: headings, tier labels, service\n"
    "lines. THESE INSTRUCTIONS ARE WRITTEN IN RUSSIAN - that is the language of the RULES, not the\n"
    "language of your answer."
)

# Якорь ищем ПО ТЕКСТУ, а не по номеру строки: INSTRUCTIONS растут, номер уедет молча.
RULE7_ANCHOR = "Подача: язык юзера"
RULE7_EN_RULE = (
    "Delivery: ANSWER IN THE LANGUAGE OF THE USER'S QUESTION - an English question means the ENTIRE "
    "answer in English (headings, tier labels and service lines included)"
)

ARMS = ("baseline", "ru_top", "en_top", "en_top_plus_rule7", "en_bottom")

# Пол выборки. dominant() считает долю по ВЫЖИВШИМ ответам, поэтому 7 упавших вызовов + 1
# английский = «english, share 1.0» и плечо объявляется рабочим по ОДНОМУ ответу. Доля без
# знаменателя — не число. 6 из 8: терпим пару потерь, но не вердикт по огрызку.
MIN_MEASURED = 6


def _patch_rule7(text):
    """Замена строки Правила 7 на английскую формулировку того же смысла. Якорь обязан быть
    РОВНО один: ноль — плечо молча выродилось бы в en_top и мы приписали бы его результат правке,
    которой не было; два — неизвестно, какой из них несущий."""
    n = text.count(RULE7_ANCHOR)
    if n != 1:
        raise ValueError(
            f"якорь Правила 7 «{RULE7_ANCHOR}» найден {n} раз, ожидался ровно 1. Текст правила "
            f"уехал — плечо en_top_plus_rule7 не собрать честно, чиню якорь, а не глушу ошибку.")
    return text.replace(RULE7_ANCHOR, RULE7_EN_RULE, 1)


def apply_variant(text, arm):
    """Патч поверх ДАННОГО текста. Чистая функция: тестируется без продукта, а на живых
    INSTRUCTIONS её премисы стережёт отдельный тест."""
    if arm == "baseline":
        return text
    if arm == "ru_top":
        return f"{RU_TOP_BLOCK}\n\n{text}"
    if arm == "en_top":
        return f"{EN_TOP_BLOCK}\n\n{text}"
    if arm == "en_bottom":
        return f"{text}\n\n{EN_TOP_BLOCK}"
    if arm == "en_top_plus_rule7":
        return f"{EN_TOP_BLOCK}\n\n{_patch_rule7(text)}"
    raise ValueError(f"неизвестное плечо «{arm}»; известные: {', '.join(ARMS)}")


def build_variants():
    """Все плечи из ЖИВЫХ INSTRUCTIONS продукта, не из копии."""
    base = load_instructions()
    return {arm: apply_variant(base, arm) for arm in ARMS}


def build_variant_prompt(instructions_text, question):
    """Плечи различаются РОВНО патчем INSTRUCTIONS. Ни слова от себя: любая наша приписка стала бы
    третьим прайором и смазала бы контраст между плечами."""
    return f"{instructions_text}\n\n{question}"


def withheld_count(rows):
    """Сколько замеров НЕ состоялось. Критерий — category is None (нет доли), а НЕ «вызов упал»:
    пустой ответ («» от контент-фильтра или квирка провайдера) вызов не роняет, доли не даёт и
    так же выпадает из знаменателя dominant(). Считать только упавшие = напечатать «withheld=0»
    над цифрой, посчитанной по огрызку выборки. Этот дефект уже давал ложный вердикт."""
    return sum(1 for r in rows if r.get("category") is None)


def _stratum_summary(rows):
    return {"rows": rows, "mean_cyrillic_share": mean_share(rows), "dominant": dominant(rows),
            "categories": dict(Counter(r["category"] for r in rows)),
            "withheld": withheld_count(rows)}


def _run_stratum_with_text(battery, lang, instructions_text, model, call):
    """Как run_stratum базовой пробы, но с ЗАДАННЫМ текстом инструкций (у базовой он всегда
    продуктовый). Упавший вызов → withheld, не догадка."""
    call = call or _default_call
    rows = []
    for item in battery:
        try:
            raw = call(build_variant_prompt(instructions_text, item[lang]), model)
        except Exception:
            raw = None
        share = cyrillic_share(raw)
        rows.append({"id": item["id"], "withheld": raw is None, "share": share,
                     "category": categorize(share), "excerpt": (raw or "")[:EXCERPT_CHARS]})
    return rows


def run_arm(battery, arm, instructions_text, model, call=None):
    """Плечо = ОБЕ страты. ru_with тут не декорация: без неё плечо, чинящее EN ценой русского,
    выглядело бы победой."""
    strata = {"en_with": _run_stratum_with_text(battery, "en", instructions_text, model, call),
              "ru_with": _run_stratum_with_text(battery, "ru", instructions_text, model, call)}
    return {"arm": arm, "instructions_chars": len(instructions_text),
            "instructions_cyrillic_share": cyrillic_share(instructions_text),
            "strata": {k: _stratum_summary(v) for k, v in strata.items()}}


def _fired(dom, want):
    """Страта отработала: нужная категория, супербольшинство И достаточный знаменатель."""
    return (dom["label"] == want and (dom["share"] or 0) >= CALIB_SUPERMAJORITY
            and dom["n"] >= MIN_MEASURED)


def calibration_with_floor(ru_with_rows, en_bare_rows):
    """Калибровка базовой пробы + пол выборки. Без пола прибор объявляет себя чувствительным по
    двум выжившим ответам и разблокирует вердикты по ВСЕМ плечам сразу — одна тонкая страта
    отравляет весь замер."""
    calib = calibration_verdict(ru_with_rows, en_bare_rows)
    thin = []
    for label, rows in (("контроль 1 (ru_with на baseline)", ru_with_rows),
                        ("контроль 2 (en_bare)", en_bare_rows)):
        n = dominant(rows)["n"]
        if n < MIN_MEASURED:
            thin.append(f"{label}: измерено {n} из {len(rows)} (нужно ≥{MIN_MEASURED}) — "
                        f"калибровать по огрызку выборки нельзя, прибор считается слепым.")
    if thin:
        return dict(calib, sensitive=False, label="ПРИБОР СЛЕП", reasons=calib["reasons"] + thin)
    return calib


def arm_verdict(en_rows, ru_rows, calib):
    """Двусторонний вердикт словами. works=True только если EN починен И RU цел.
    works=None — прибор слеп, факта нет."""
    en_dom, ru_dom = dominant(en_rows), dominant(ru_rows)
    wh = {"en_with": withheld_count(en_rows), "ru_with": withheld_count(ru_rows)}
    base = {"dominant_en": en_dom, "dominant_ru": ru_dom, "withheld": wh}
    if not calib["sensitive"]:
        return dict(base, works=None, fixes_en=None, keeps_ru=None,
                    text="ВЫВОД АННУЛИРОВАН: прибор слеп — " + " ".join(calib["reasons"]))
    fixes_en, keeps_ru = _fired(en_dom, "english"), _fired(ru_dom, "russian")
    en_s = f"«{en_dom['label']}» {en_dom['share']:.0%}" if en_dom["share"] is not None else "н/д"
    ru_s = f"«{ru_dom['label']}» {ru_dom['share']:.0%}" if ru_dom["share"] is not None else "н/д"
    if fixes_en and keeps_ru:
        text = (f"РАБОТАЕТ: английский вопрос даёт {en_s}, русский путь ЦЕЛ ({ru_s}). "
                f"Кандидат чинит EN и не ломает RU.")
    elif fixes_en and not keeps_ru:
        text = (f"СЛОМАЛ РУССКИЙ ПУТЬ: английский починен ({en_s}), но русский вопрос теперь даёт "
                f"{ru_s} вместо уверенного русского. Это ПРОВАЛ, а не победа: сломан ежедневный "
                f"путь владельца.")
    elif not fixes_en and keeps_ru:
        text = (f"НЕ РАБОТАЕТ: русский путь цел ({ru_s}), но английский вопрос по-прежнему даёт "
                f"{en_s} — уверенного английского нет. Смесь в успех не округляем.")
    else:
        text = (f"НЕ РАБОТАЕТ И СЛОМАЛ РУССКИЙ: английский {en_s}, русский {ru_s}. Хуже baseline "
                f"по обеим сторонам.")
    if wh["en_with"] or wh["ru_with"]:
        text += (f" ⚠ WITHHELD: en_with={wh['en_with']}, ru_with={wh['ru_with']} — вызовы упали, "
                 f"доли считаны по остатку; при большом withheld вердикт ненадёжен.")
    return dict(base, works=bool(fixes_en and keeps_ru), fixes_en=fixes_en, keeps_ru=keeps_ru,
                text=text)


def summarize_arms(arms):
    """Прямой ответ на вопрос владельца: есть ли плечо, которое чинит EN и НЕ ломает RU."""
    winners = [name for name, a in arms.items() if a["verdict"].get("works") is True]
    broke_ru = [name for name, a in arms.items()
                if a["verdict"].get("fixes_en") and a["verdict"].get("keeps_ru") is False]
    annulled = [name for name, a in arms.items() if a["verdict"].get("works") is None]
    # Слепой прибор ≠ «правка не помогла». Без этой ветки отсутствие замера печаталось бы как
    # уверенный отрицательный вывод — ровно тот жанр вранья, против которого построена проба.
    if annulled and len(annulled) == len(arms):
        return {"winners": [], "broke_ru": [], "annulled": annulled,
                "text": "ВЫВОД ПО ВСЕМ ПЛЕЧАМ АННУЛИРОВАН: прибор слеп (калибровка не "
                        "отработала). Это НЕ отрицательный результат, а ОТСУТСТВИЕ замера: "
                        "плечи не читаются, нужен повторный прогон."}
    if winners:
        text = f"ЕСТЬ кандидат, чинящий английский путь без потери русского: {', '.join(winners)}."
    else:
        text = ("НЕТ ни одного плеча, которое чинит английский путь и сохраняет русский. "
                "Дешёвая текстовая правка провалилась.")
        if broke_ru:
            text += f" Плечи, купившие EN ценой русского (это провал): {', '.join(broke_ru)}."
    if annulled:
        text += (f" ⚠ Плечи без вердикта (замер не состоялся, в вывод НЕ идут): "
                 f"{', '.join(annulled)}.")
    return {"winners": winners, "broke_ru": broke_ru, "annulled": annulled, "text": text}


def run_model(battery, model, variants, call=None):
    # Контроль-потолок: английский вопрос БЕЗ INSTRUCTIONS. Один на модель — от плеча не зависит.
    en_bare = run_stratum(battery, "en", False, model, call)
    arms = {}
    for arm in ARMS:
        print(f"  -- плечо {arm}", flush=True)
        arms[arm] = run_arm(battery, arm, variants[arm], model, call)
    # Калибровка на baseline: он же и контроль 1 (русский вопрос + непатченные INSTRUCTIONS).
    calib = calibration_with_floor(arms["baseline"]["strata"]["ru_with"]["rows"], en_bare)
    for arm in ARMS:
        s = arms[arm]["strata"]
        arms[arm]["verdict"] = arm_verdict(s["en_with"]["rows"], s["ru_with"]["rows"], calib)
    return {"model": model, "control_en_bare": _stratum_summary(en_bare), "calibration": calib,
            "arms": arms, "summary": summarize_arms(arms)}


def _dump(payload, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def recompute_model(entry):
    """Пересчёт вердиктов из СОХРАНЁННОГО сырья текущей логикой, без сети. Сырьё стоит сотни
    живых вызовов, логика вердикта — ноль. Когда правила ужесточаются (пол выборки, учёт
    withheld), честный ход — пересчитать сохранённые строки, а не платить за сеть заново и не
    оставлять в файле вердикт, вынесенный по правилам, которые мы уже признали дырявыми."""
    bare_rows = entry["control_en_bare"]["rows"]
    entry["control_en_bare"] = _stratum_summary(bare_rows)
    for arm in entry["arms"].values():
        for name, s in arm["strata"].items():
            arm["strata"][name] = _stratum_summary(s["rows"])
    calib = calibration_with_floor(entry["arms"]["baseline"]["strata"]["ru_with"]["rows"], bare_rows)
    entry["calibration"] = calib
    for arm in entry["arms"].values():
        s = arm["strata"]
        arm["verdict"] = arm_verdict(s["en_with"]["rows"], s["ru_with"]["rows"], calib)
    entry["summary"] = summarize_arms(entry["arms"])
    return entry


def _print_model(entry):
    bare = entry["control_en_bare"]
    bm = bare["mean_cyrillic_share"]
    print(f"  контроль en_bare (потолок): кириллица "
          f"{('%.1f%%' % (bm * 100)) if bm is not None else 'н/д'} {bare['categories']} "
          f"withheld={bare['withheld']}")
    print(f"  калибровка: {entry['calibration']['label']}")
    for arm, a in entry["arms"].items():
        print(f"  [{arm}]")
        for name in ("en_with", "ru_with"):
            s = a["strata"][name]
            ms = s["mean_cyrillic_share"]
            print(f"    {name:8s} кириллица "
                  f"{('%.1f%%' % (ms * 100)) if ms is not None else 'н/д':>6s}  "
                  f"{s['categories']}  withheld={s['withheld']}")
        print(f"    вердикт: {a['verdict']['text']}")
    print(f"  ИТОГ по модели: {entry['summary']['text']}")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Плечи против языкового прайора INSTRUCTIONS (изолировано, ноль правок контура)")
    p.add_argument("--run", action="store_true", help="живой прогон (нужен OPENROUTER_API_KEY)")
    p.add_argument("--models", default=DEFAULT_MODELS)
    p.add_argument("--n", type=int, default=DEFAULT_N, help="парных вопросов (макс 8)")
    p.add_argument("--out", default=os.path.join(RESULTS_DIR, "instructions-language-variants.json"))
    p.add_argument("--recompute", metavar="PATH",
                   help="пересчитать вердикты из сохранённого сырья текущей логикой (без сети)")
    a = p.parse_args(argv)
    if a.recompute:
        with open(a.recompute, encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data["models"]:
            print(f"\n=== {entry['model']} ===")
            _print_model(recompute_model(entry))
        data["recomputed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        data["min_measured"] = MIN_MEASURED
        _dump(data, a.recompute)
        print(f"\n→ {a.recompute}")
        return 0
    bat = build_battery(a.n)
    variants = build_variants()
    if not a.run:
        base_len = len(variants["baseline"])
        print(f"Сухой режим. Батарея: {len(bat)} парных вопросов × 2 страты × {len(ARMS)} плечей "
              f"+ контроль en_bare.")
        for arm in ARMS:
            t = variants[arm]
            print(f"  {arm:18s} {len(t):6d} симв. ({len(t) - base_len:+5d}), "
                  f"кириллица {cyrillic_share(t):.1%}")
        print("Меряются ОБЕ стороны: плечо, чинящее EN ценой RU, — провал, а не победа.")
        print("Живой прогон: --run.")
        return 0
    if not _load_key_from_dotenv():
        print("НЕТ OPENROUTER_API_KEY (ни в env, ни в .env). Экспортируй ключ и повтори.",
              file=sys.stderr)
        return 2
    # Без этого llm_local уходит в ollama (её дефолт) и бьёт 404 на api-именах моделей — вызовы
    # молча уезжают в withheld, прогон пустой, а вердикт при этом печатается уверенным.
    os.environ["LLM_BACKEND"] = "openrouter"
    out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "baseline_instructions_chars": len(variants["baseline"]),
           "baseline_instructions_cyrillic_share": cyrillic_share(variants["baseline"]),
           "thresholds": {"english_below": THRESH_EN, "russian_above": THRESH_RU,
                          "calibration_supermajority": CALIB_SUPERMAJORITY,
                          "min_measured": MIN_MEASURED},
           "temperature": GEN_TEMPERATURE, "battery_n": len(bat), "arms": list(ARMS), "models": []}
    for model in [m for m in a.models.split(",") if m]:
        print(f"\n=== {model} ===", flush=True)
        entry = run_model(bat, model, variants)
        _print_model(entry)
        out["models"].append(entry)
        # Пишем ПОСЛЕ КАЖДОЙ модели, а не в конце: прогон стоит сотни живых вызовов и десятки
        # минут, и один обрыв на последней модели уже стёр здесь полностью отработавшую первую.
        _dump(out, a.out)
    print(f"\n→ {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
