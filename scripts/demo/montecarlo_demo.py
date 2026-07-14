#!/usr/bin/env python3
"""Демо B: «посчитано, а не на глаз» — считаемый вопрос через Monte Carlo.

Другая поверхность рва: на вопрос «X или Y» совет не спорит афоризмами, а прогоняет
ТВОЮ модель 10 000 раз (детерминированно, сид 2026) и отдаёт распределение исхода,
P(лучший) и главный рычаг. Числа тянутся из живого run_calculation на каждом прогоне,
не хардкод; при пропаже расчёта скрипт падает. Честная плашка в кадре: это не истина,
это твоя модель, прогнанная много раз.

Запуск:  python3 scripts/demo/montecarlo_demo.py [--en] [--no-prompt] [--no-anim] [--check]
Ноль техношума: внутренние id величин заменены человеческими подписями (Rule 1/10).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _HERE)

import _harness

# Карта решения фаундера (форма из спеки §1). Встроена целиком → результат воспроизводим.
_MAP = {
    "question": "Выпустить публично сейчас или подождать?",
    "options": [
        {"id": "ship_public", "name": "Выпустить публично", "description": "…", "reversibility": "one-way"},
        {"id": "status_quo", "name": "Подождать", "description": "…", "reversibility": "two-way", "status_quo": True},
    ],
    "uncertainties": [
        {"id": "traction_prob", "kind": "event", "prob": 0.3, "confirmed_by_user": True, "elicited": "…"},
        {"id": "hours_to_ship", "kind": "continuous", "unit": "часы", "min": 20, "mode": 40, "max": 90,
         "confirmed_by_user": True, "elicited": "…"},
        {"id": "upside_hours", "kind": "continuous", "unit": "часы", "min": 50, "mode": 150, "max": 400,
         "confirmed_by_user": True, "elicited": "…"},
    ],
    "stakes": {"metric": "ценность в часах", "direction": "max"},
    "horizon": "3 месяца",
    "model": {
        "ship_public": {"expr": "traction_prob * upside_hours - hours_to_ship", "words": "…"},
        "status_quo": {"expr": "0", "words": "…"},
    },
}
# Человеческие подписи внутренних id (в кадре не показываем сырой id).
_LEVER = {"ru": {"traction_prob": "вероятность трекшена", "upside_hours": "выигрыш в часах",
                 "hours_to_ship": "часы на релиз"},
          "en": {"traction_prob": "the odds of traction", "upside_hours": "the upside in hours",
                 "hours_to_ship": "the hours to ship"}}


def run():
    """Гоняет живой расчёт. Возвращает (res, p_ship_pct, spark, top_lever_id).

    Fail-closed: нет p_best/histogram/tornado → SystemExit (демо на живых числах, не хардкод)."""
    os.chdir(_ROOT)
    from mcp_server import dispatch
    import calc_render
    res = dispatch("run_calculation", {"map": _MAP})
    if not (isinstance(res, dict) and res.get("p_best") and res.get("histogram") and res.get("tornado")):
        raise SystemExit("run_calculation не отдал расчёт — демо недостоверно.")
    p_ship = res["p_best"]["ship_public"]
    spark = calc_render._spark(res["histogram"]["counts"]["ship_public"])
    top = res["tornado"][0]["id"]
    return res, round(p_ship * 100), spark, top


_LANG = {
    "ru": {
        "prompt": "$ consilium calc «выпустить публично сейчас или подождать?»",
        "intro": "Совет не спорит на глаз. По ТВОЕЙ модели он считает:",
        "runs": "  %s прогонов Monte Carlo (сид %d, воспроизводимо)",
        "opt": "Выпустить публично:",
        "pbest": "  P(выгоднее, чем подождать) = %d%%",
        "lever": "  главный рычаг: %s, не часы на релиз",
        "honest": "Это не истина. Это твоя модель, прогнанная %s раз.",
        "cta": "Считаемый вопрос: числами, не афоризмом.",
    },
    "en": {
        "prompt": "$ consilium calc «ship publicly now, or wait?»",
        "intro": "The council does not vibe it. It runs YOUR model:",
        "runs": "  %s Monte Carlo runs (seed %d, reproducible)",
        "opt": "Ship publicly:",
        "pbest": "  P(better than waiting) = %d%%",
        "lever": "  the biggest lever: %s, not the hours to ship",
        "honest": "Not the truth. Just your model, run %s times.",
        "cta": "A countable question, answered in numbers, not aphorisms.",
    },
}


def transcript(include_prompt=True, lang="ru"):
    res, p_ship, spark, top = run()               # валидирует до отрисовки
    s = _LANG[lang]
    n, seed = res["label"]["n"], res["label"]["seed"]
    n_str = format(n, ",").replace(",", " ")     # 10000 → «10 000» (тонкий пробел)
    lever = _LEVER[lang].get(top, top)
    lines = []
    if include_prompt:
        lines.append(("prompt", s["prompt"]))
    lines += [
        ("blank", ""),
        ("dim", s["intro"]),
        ("dim", s["runs"] % (n_str, seed)),
        ("blank", ""),
        ("label", s["opt"]),
        ("bar", "  " + spark),
        ("num", s["pbest"] % p_ship),
        ("dim", s["lever"] % lever),
        ("blank", ""),
        ("warn", s["honest"] % n_str),
        ("blank", ""),
        ("cta", s["cta"]),
    ]
    return lines


def main(argv):
    if "--check" in argv:
        res, p_ship, spark, top = run()
        print("p_best(ship)=%d%% top_lever=%s n=%d seed=%d" % (p_ship, top, res["label"]["n"], res["label"]["seed"]))
        print("spark:", spark)
        return 0
    lang = "en" if "--en" in argv else "ru"
    _harness.render(transcript(include_prompt="--no-prompt" not in argv, lang=lang),
                    animate="--no-anim" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
