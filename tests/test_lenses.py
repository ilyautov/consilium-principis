"""Функциональные линзы (бизнес-функции как советники) — загрузка + структурная честность."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from lenses import load_lens, list_lenses, is_frame_lens_honest

LENSES_DIR = os.path.join(HERE, "..", "lenses")


def test_ships_three_frame_lenses_and_grounded_strategist():
    ls = list_lenses(LENSES_DIR)
    by_name = {l["name"]: l for l in ls}
    for nm in ("Финансист (CFO)", "Маркетолог", "Продажник"):
        assert by_name[nm]["grade"] == "frame-lens"
        assert by_name[nm]["marker_ceiling"] == "🟡"   # 🔵 невозможен — нет корпуса
    # Стратег апгрейднут до grounded (канон Сунь-цзы PD → 🔵)
    strat = by_name["Стратег (Сунь-цзы)"]
    assert strat["grade"] == "grounded-lens"
    assert strat["marker_ceiling"] == "🔵"


def test_cfo_kernels_loaded():
    cfo = load_lens(os.path.join(LENSES_DIR, "cfo.md"))
    assert cfo["name"] == "Финансист (CFO)"
    assert cfo["axis"] == "деньги / устойчивость"
    assert "Unit-экономика" in cfo["kernels"]
    assert len(cfo["kernels"]) >= 4


def test_all_shipped_lenses_are_honest():
    for l in list_lenses(LENSES_DIR):
        assert is_frame_lens_honest(l), f"{l['name']} претендует на маркер выше 🟡 без корпуса"


def test_dishonest_frame_lens_is_caught():
    # frame-lens с потолком 🔵 (нет корпуса, но претендует на голос автора) → инвариант ловит
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "fake.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\nname: Фейк\ngrade: frame-lens\nmarker_ceiling: 🔵\n---\n## Кернелы\n- **X:** y\n")
        assert is_frame_lens_honest(load_lens(p)) is False


def test_missing_lens_returns_none():
    assert load_lens(os.path.join(LENSES_DIR, "nope.md")) is None


def test_kernel_regex_requires_colon_inside_bold():
    # жирный буллет БЕЗ двоеточия (эмфаза/заметка) не должен попасть в кернелы
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "x.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\nname: X\ngrade: frame-lens\nmarker_ceiling: 🟡\n---\n## Кернелы\n"
                    "- **Настоящий кернел:** описание\n- **просто жирная заметка** не кернел\n")
        ks = load_lens(p)["kernels"]
        assert ks == ["Настоящий кернел"]
