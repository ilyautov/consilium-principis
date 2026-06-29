"""Меню рецептов — discoverable «что умеет твой совет» для нетехнического юзера.

Мощь Consilium (премортем, шахматный движок спора, зеркало, столкнуть двух) была спрятана в
SKILL.md — юзер не знал, что спросить. Рецепты = простые фразы-триггеры + что делает + как читать
результат (приём workflows.yaml из marketplaces-mcp-ru, в домене совета). stdlib-пол: данные в
recipes.json, без pyyaml. load → render_menu (показать) → match_recipe (понять, что просит юзер).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from recipes import load_recipes, render_menu, match_recipe


def test_recipes_well_formed():
    rs = load_recipes()
    assert len(rs) >= 6
    for r in rs:
        assert {"id", "title", "triggers", "does"} <= set(r)
        assert isinstance(r["triggers"], list) and r["triggers"]


def test_menu_is_human_readable():
    menu = render_menu(load_recipes())
    assert "Что может пойти не так" in menu        # премортем-триггер виден
    assert "совет" in menu.lower()


def test_match_finds_premortem():
    r = match_recipe("что может пойти не так с моим запуском", load_recipes())
    assert r is not None and r["id"] == "premortem"


def test_match_finds_single_advisor():
    r = match_recipe("что бы сказал Аврелий про выгорание", load_recipes())
    assert r is not None and r["id"] in ("ask-one", "full-council")


def test_match_none_on_gibberish():
    assert match_recipe("qwerty asdfgh zxcvb", load_recipes()) is None
