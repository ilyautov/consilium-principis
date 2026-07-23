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


# EN-паритет CLI (#4): язык влияет на ДЕТЕРМИНИРОВАННЫЙ слой (меню + матч), не на host-mediated
# INSTRUCTIONS (те русские по замеренному дизайну). chrome-строки по языку; поля рецепта — из
# *_en с фолбэком на русский.
_CHROME = {
    "ru": {"head": "Что умеет твой совет — просто скажи своими словами:", "say": "скажи",
           "legend": "Маркеры в ответах: 🔵 дословная цитата (с источником) · 🟡 экстраполяция · отказ вместо выдумки.",
           "title": "Что умеет твой совет", "sub": "Просто скажи своими словами — командовать не нужно.",
           "widget_sub": "Нажми карточку — спрошу за тебя."},
    "en": {"head": "What your council can do — just say it in your own words:", "say": "say",
           "legend": "Markers in replies: 🔵 a verbatim quote (with source) · 🟡 an extrapolation · abstention instead of invention.",
           "title": "What your council can do", "sub": "Just say it in your own words — no commands needed.",
           "widget_sub": "Tap a card — I'll ask for you."},
}


def lang_from_env():
    """Язык CLI по CONSILIUM_LANG: en → английский, всё прочее (ru/auto/пусто) → русский (дефолт)."""
    return "en" if (os.getenv("CONSILIUM_LANG") or "").strip().lower() == "en" else "ru"


def _chrome(lang):
    return _CHROME.get(lang, _CHROME["ru"])


def _field(r, key, lang):
    return r.get(f"{key}_en", r[key]) if lang == "en" else r[key]


def _disp_trigger(r, lang):
    trig = r.get("triggers_en") or r["triggers"] if lang == "en" else r["triggers"]
    return trig[0]


def render_menu(recipes, lang="ru"):
    c = _chrome(lang)
    lines = [c["head"], ""]
    for i, r in enumerate(recipes, 1):
        lines.append(f"{i}. {_field(r, 'title', lang)}")
        lines.append(f'   {c["say"]}: «{_disp_trigger(r, lang)}»')
        lines.append(f"   → {_field(r, 'does', lang)}")
    lines.append("")
    lines.append(c["legend"])
    return "\n".join(lines)


def render_html(recipes, title=None, lang="ru"):
    """Меню как самодостаточный HTML — визуализация-surface (карточки вместо чипов).
    Показывает ВСЕ рецепты (не лимит 4). Выбор замыкается фразой-триггером/кнопкой, не самим HTML."""
    c = _chrome(lang)
    title = title or c["title"]
    e = _html.escape
    cards = []
    for r in recipes:
        cards.append(
            '<article class="card">'
            f'<h2>{e(_field(r, "short", lang))}</h2>'
            f'<p class="does">{e(_field(r, "does", lang))}</p>'
            f'<p class="say">{c["say"]}: «{e(_disp_trigger(r, lang))}»</p>'
            "</article>"
        )
    return (
        f"<!doctype html><html lang={lang}><meta charset=utf-8>"
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
        f"<p class=sub>{e(c['sub'])}</p>"
        f'<div class="grid">{"".join(cards)}</div>'
        f"<p class=legend>{e(c['legend'])}</p>"
        "</html>"
    )


def render_widget(recipes, title=None, lang="ru"):
    """Меню как HTML для mcp__visualize__show_widget (нативный Cowork): сетка карточек, клик по
    карточке шлёт фразу-триггер в чат через sendPrompt. AskUserQuestion тут не годится (потолок 4)."""
    c = _chrome(lang)
    title = title or c["title"]
    e = _html.escape
    def onclick(p):
        return e("sendPrompt('" + p.replace("\\", "\\\\").replace("'", "\\'") + "')", quote=True)
    cards = []
    for r in recipes:
        trig = _disp_trigger(r, lang)
        cards.append(
            f'<button onclick="{onclick(trig)}" style="text-align:left;cursor:pointer;font:inherit;'
            'border:1px solid var(--color-border-primary,rgba(127,127,127,.3));border-radius:12px;'
            'padding:14px 16px;background:var(--color-background-secondary,transparent);'
            'color:var(--color-text-primary,CanvasText)">'
            f'<div style="font-weight:600;margin-bottom:6px">{e(_field(r, "short", lang))}</div>'
            f'<div style="font-size:.9rem;opacity:.8">{e(_field(r, "does", lang))}</div></button>')
    return (
        '<div style="font-family:var(--font-sans,system-ui,sans-serif);'
        'color:var(--color-text-primary,CanvasText);max-width:760px">'
        f'<h2 style="font-size:1.25rem;margin:0 0 4px">{e(title)}</h2>'
        f'<p style="opacity:.7;margin:0 0 16px;font-size:.9rem">{e(c["widget_sub"])}</p>'
        '<div style="display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">'
        + "".join(cards) + "</div>"
        f'<p style="margin-top:18px;font-size:.82rem;opacity:.7">{e(c["legend"])}</p></div>'
    )


def _words(s):
    return {w for w in re.findall(r"[а-яёa-z]+", s.lower()) if len(w) >= 4}


def match_recipe(query, recipes):
    """Лучший рецепт по перекрытию значимых слов с триггерами (RU ∪ EN); None если совпадений нет.
    Матч по объединению языков: юзер на любом языке находит рецепт, независимо от CONSILIUM_LANG."""
    q = _words(query)
    best, best_score = None, 0
    for r in recipes:
        trigs = list(r["triggers"]) + list(r.get("triggers_en", []))
        score = max((len(q & _words(t)) for t in trigs), default=0)
        if score > best_score:
            best, best_score = r, score
    return best if best_score > 0 else None


if __name__ == "__main__":
    print(render_menu(load_recipes(), lang=lang_from_env()))
