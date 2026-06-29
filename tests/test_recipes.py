"""Меню рецептов — discoverable «что умеет твой совет» для нетехнического юзера.

Мощь Consilium (премортем, шахматный движок спора, зеркало, столкнуть двух) была спрятана в
SKILL.md — юзер не знал, что спросить. Рецепты = простые фразы-триггеры + что делает + как читать
результат (приём workflows.yaml из marketplaces-mcp-ru, в домене совета). stdlib-пол: данные в
recipes.json, без pyyaml. load → render_menu (показать) → match_recipe (понять, что просит юзер).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from recipes import load_recipes, render_menu, render_html, render_widget, match_recipe


def test_recipes_well_formed():
    rs = load_recipes()
    assert len(rs) >= 6
    for r in rs:
        assert {"id", "title", "triggers", "does"} <= set(r)
        assert isinstance(r["triggers"], list) and r["triggers"]


def test_every_recipe_has_short_button_label():
    # короткая подпись нужна для кнопок-опций в Code/Cowork (длинный title на кнопку не лезет)
    for r in load_recipes():
        assert r.get("short"), f"{r['id']} без short-подписи под кнопку"
        assert len(r["short"]) <= 22, f"{r['id']} short слишком длинная для кнопки"


def test_menu_is_human_readable():
    menu = render_menu(load_recipes())
    assert "Что может пойти не так" in menu        # премортем-триггер виден
    assert "совет" in menu.lower()


def test_render_html_shows_all_recipes_and_is_safe():
    rs = load_recipes()
    h = render_html(rs)
    assert h.startswith("<!doctype html>") and "</html>" in h
    assert h.count('class="card"') == len(rs)      # визуализация показывает ВСЕ, не лимит 4
    assert "🔵" in h and "🟡" in h                  # контур-легенда не теряется
    assert "<script" not in h.lower()              # без скриптов — безопасный артефакт


def test_render_widget_clickable_all_recipes():
    rs = load_recipes()
    w = render_widget(rs)
    assert w.count("sendPrompt(") == len(rs)        # каждая карточка кликабельна (все, не 4)
    assert "var(--font-sans" in w                    # тема Cowork
    assert "<script" not in w.lower()                # без тега script
    # фраза-триггер первого рецепта уходит в чат
    assert rs[0]["triggers"][0] in w


def test_match_finds_premortem():
    r = match_recipe("что может пойти не так с моим запуском", load_recipes())
    assert r is not None and r["id"] == "premortem"


def test_match_finds_single_advisor():
    r = match_recipe("что бы сказал Аврелий про выгорание", load_recipes())
    assert r is not None and r["id"] in ("ask-one", "full-council")


def test_match_none_on_gibberish():
    assert match_recipe("qwerty asdfgh zxcvb", load_recipes()) is None
