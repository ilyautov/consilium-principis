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


# ── права на ПЕРЕВОД (аудит 2026-10-16): автор в PD ≠ перевод в PD везде ──

def test_every_seed_figure_declares_translation_rights():
    import json
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    for fig in cat["figures"]:
        t = fig["rights"].get("translation")
        assert isinstance(t, dict), fig["id"]
        assert t["translator"] and isinstance(t["translator_death_year"], int)
        assert isinstance(t["published_year"], int) and t["published_year"] < 1931  # US-PD


def test_translation_status_life_plus_70():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import catalog
    giles = {"rights": {"translation": {"translator": "Lionel Giles", "translator_death_year": 1958,
                                        "published_year": 1910}}}
    st = catalog.translation_status(giles, year=2026)
    assert st["us"] == "public_domain" and st["life_plus_70"] == "protected"
    assert st["life_plus_70_free_from"] == 2029
    assert "2029" in catalog.translation_warning(giles, year=2026)
    assert catalog.translation_status(giles, year=2029)["life_plus_70"] == "public_domain"
    assert catalog.translation_warning(giles, year=2029) is None
    assert catalog.translation_status({"rights": {}}) is None
    assert catalog.translation_status({"rights": {"translation": {"translator_death_year": True}}}) == \
        {"translator": ""}


def test_shipped_catalog_flags_only_giles_today():
    import json, sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import catalog
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    flagged = [f["id"] for f in cat["figures"] if catalog.translation_warning(f, year=2026)]
    assert flagged == ["sun-tzu"]
