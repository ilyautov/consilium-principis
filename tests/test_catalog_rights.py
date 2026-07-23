"""Гейт прав на СЕЯНЫЙ каталог: каждая публикуемая PD-фигура несёт очищенные права.

Ров легальности: публично мы сеем ТОЛЬКО давно-умерших на
public-domain текстах. Каждый сид обязан нести rights-блок:
  - death_year (int) — фигура давно мертва (тексты в PD: жизнь+70, ГК РФ ст.1281/1282);
  - text_status == "public_domain";
  - consenter_circle == "exhausted" — РФ-тест ст.152.1: круг согласителей (дети/супруг→родители)
    исчерпан, живых родственников нет → согласие не требуется (Пленум ВС РФ №25 п.49).
Fail-closed: сид без очищенных прав НЕ шипится (этот гейт краснеет). rights_clear НЕ «поднимает»
неочищенное — только копирует факт из метаданных, как fidelity-маркеры.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import catalog

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "pd_figures.json"


def _figures():
    return json.loads(CATALOG.read_text(encoding="utf-8"))["figures"]


def test_every_seeded_figure_has_cleared_rights():
    for fig in _figures():
        assert catalog.rights_clear(fig), f"{fig.get('id')}: права не очищены (rights-блок неполон)"


def test_every_seeded_figure_long_dead():
    # Античные сиды: death_year далеко в прошлом. Порог <1900 кодирует «давно мёртв» (тексты
    # заведомо PD, круг родственников исчерпан) без завязки на текущий год (тесты офлайн-детерминизм).
    for fig in _figures():
        dy = fig["rights"]["death_year"]
        assert isinstance(dy, int) and dy < 1900, f"{fig.get('id')}: death_year не «давно» ({dy})"


def test_rights_clear_is_fail_closed():
    assert catalog.rights_clear({"id": "x"}) is False                       # нет блока
    assert catalog.rights_clear({"id": "x", "rights": {"death_year": 180}}) is False  # неполон
    assert catalog.rights_clear({"id": "x", "rights": {
        "death_year": 180, "text_status": "public_domain",
        "consenter_circle": "exhausted"}}) is True
    # не поднять неочищенное (живой / копирайт / круг жив):
    assert catalog.rights_clear({"id": "x", "rights": {
        "death_year": 2000, "text_status": "copyright",
        "consenter_circle": "living"}}) is False
    assert catalog.rights_clear({"id": "x", "rights": {
        "death_year": "180", "text_status": "public_domain",
        "consenter_circle": "exhausted"}}) is False  # death_year не int
