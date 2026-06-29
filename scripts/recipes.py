#!/usr/bin/env python3
"""Меню рецептов — discoverable «что умеет твой совет» для нетехнического юзера.

Мощь Consilium была спрятана в SKILL.md; юзер не знал, что спросить, и видел пустой стол. Рецепты
= простые фразы-триггеры + что делает + как читать результат (приём workflows.yaml из
marketplaces-mcp-ru, в домене совета). Данные в recipes.json (stdlib-пол, без pyyaml).
  • load_recipes()          — список рецептов
  • render_menu(recipes)    — человекочитаемое меню (показать на «что умеешь?»)
  • match_recipe(q, recipes)— какой рецепт просит юзер (по словам триггеров), либо None
"""
import os
import re
import json

_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "recipes.json")


def load_recipes(path=None):
    return json.load(open(path or _JSON, encoding="utf-8"))


def render_menu(recipes):
    lines = ["Что умеет твой совет — просто скажи своими словами:", ""]
    for i, r in enumerate(recipes, 1):
        example = r["triggers"][0]
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   скажи: «{example}»")
        lines.append(f"   → {r['does']}")
    lines.append("")
    lines.append("Маркеры в ответах: 🔵 дословная цитата (с источником) · 🟡 экстраполяция · отказ вместо выдумки.")
    return "\n".join(lines)


def _words(s):
    return {w for w in re.findall(r"[а-яёa-z]+", s.lower()) if len(w) >= 4}


def match_recipe(query, recipes):
    """Лучший рецепт по перекрытию значимых слов с триггерами; None если совпадений нет."""
    q = _words(query)
    best, best_score = None, 0
    for r in recipes:
        score = max((len(q & _words(t)) for t in r["triggers"]), default=0)
        if score > best_score:
            best, best_score = r, score
    return best if best_score > 0 else None


if __name__ == "__main__":
    print(render_menu(load_recipes()))
