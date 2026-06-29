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


def render_widget(recipes, title="Что умеет твой совет"):
    """Меню как HTML для mcp__visualize__show_widget (нативный Cowork): сетка карточек, клик по
    карточке шлёт фразу-триггер в чат через sendPrompt. AskUserQuestion тут не годится (потолок 4)."""
    e = _html.escape
    def onclick(p):
        return e("sendPrompt('" + p.replace("\\", "\\\\").replace("'", "\\'") + "')", quote=True)
    cards = []
    for r in recipes:
        trig = r["triggers"][0]
        cards.append(
            f'<button onclick="{onclick(trig)}" style="text-align:left;cursor:pointer;font:inherit;'
            'border:1px solid var(--color-border-primary,rgba(127,127,127,.3));border-radius:12px;'
            'padding:14px 16px;background:var(--color-background-secondary,transparent);'
            'color:var(--color-text-primary,CanvasText)">'
            f'<div style="font-weight:600;margin-bottom:6px">{e(r["short"])}</div>'
            f'<div style="font-size:.9rem;opacity:.8">{e(r["does"])}</div></button>')
    return (
        '<div style="font-family:var(--font-sans,system-ui,sans-serif);'
        'color:var(--color-text-primary,CanvasText);max-width:760px">'
        f'<h2 style="font-size:1.25rem;margin:0 0 4px">{e(title)}</h2>'
        '<p style="opacity:.7;margin:0 0 16px;font-size:.9rem">Нажми карточку — спрошу за тебя.</p>'
        '<div style="display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">'
        + "".join(cards) + "</div>"
        '<p style="margin-top:18px;font-size:.82rem;opacity:.7">🔵 дословная цитата (с источником) · '
        '🟡 экстраполяция · отказ вместо выдумки.</p></div>'
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
