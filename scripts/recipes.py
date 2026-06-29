#!/usr/bin/env python3
"""Меню рецептов — discoverable «что умеет твой совет» для нетехнического юзера.

Мощь Consilium была спрятана в SKILL.md; юзер не знал, что спросить, и видел пустой стол. Рецепты
= простые фразы-триггеры + что делает + как читать результат (приём workflows.yaml из
marketplaces-mcp-ru, в домене совета). Данные в recipes.json (stdlib-пол, без pyyaml).
  • load_recipes()          — список рецептов
  • render_menu(recipes)    — человекочитаемое меню (текст; показать на «что умеешь?»)
  • render_html(recipes)    — то же меню как HTML-карточки (визуализация, surface для Cowork)
  • match_recipe(q, recipes)— какой рецепт просит юзер (по словам триггеров), либо None

Дисплей и выбор — разные слои: текст/HTML показывают ВСЕ рецепты (ничего не прячем),
а сам выбор замыкается через AskUserQuestion-кнопки или фразу-триггер.
"""
import os
import re
import json
import html as _html

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


def render_html(recipes, title="Что умеет твой совет"):
    """Меню как самодостаточный HTML — визуализация-surface (карточки вместо чипов).
    Показывает ВСЕ рецепты (не лимит 4). Выбор замыкается фразой-триггером/кнопкой, не самим HTML."""
    e = _html.escape
    cards = []
    for r in recipes:
        cards.append(
            '<article class="card">'
            f'<h2>{e(r["short"])}</h2>'
            f'<p class="does">{e(r["does"])}</p>'
            f'<p class="say">скажи: «{e(r["triggers"][0])}»</p>'
            "</article>"
        )
    return (
        "<!doctype html><html lang=ru><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)}</title><style>"
        ":root{color-scheme:light dark}"
        "body{font:16px/1.5 system-ui,sans-serif;margin:0;padding:24px;"
        "background:Canvas;color:CanvasText}"
        "h1{font-size:1.4rem;margin:0 0 4px}"
        ".sub{opacity:.7;margin:0 0 20px;font-size:.9rem}"
        ".grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}"
        ".card{border:1px solid color-mix(in srgb,CanvasText 18%,transparent);"
        "border-radius:12px;padding:14px 16px}"
        ".card h2{font-size:1.05rem;margin:0 0 6px}"
        ".does{margin:0 0 10px}"
        ".say{margin:0;font-size:.9rem;opacity:.75;font-style:italic}"
        ".legend{margin-top:22px;font-size:.85rem;opacity:.75}"
        "</style>"
        f"<h1>{e(title)}</h1>"
        "<p class=sub>Просто скажи своими словами — командовать не нужно.</p>"
        f'<div class="grid">{"".join(cards)}</div>'
        "<p class=legend>Маркеры в ответах: 🔵 дословная цитата (с источником) · "
        "🟡 экстраполяция · отказ вместо выдумки.</p>"
        "</html>"
    )


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
