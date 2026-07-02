"""Рендер результата run_calculation (Ф3): гистограмма исходов, торнадо, сводка.

Архитектура — та же, что session_render: ОДИН data-объект (выход mc_run) → тонкие
рендер-адаптеры под surface (md портативный / widget для mcp__visualize__show_widget).
Функции ЧИСТЫЕ: фиксированный вход → байт-в-байт тот же выход, ноль LLM, ноль сети.
Стережём: детерминизм, escape, механика виджета Cowork (sendPrompt-совместимые
--color-*, без <script>, без эмодзи в вёрстке), graceful без histogram-блока.
"""
import os, sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from calc_render import render_calc_md, render_calc_widget
from mc_run import mc_run

LABEL = ("📐 расчёт по ТВОЕЙ модели: 2 величин (подтверждены тобой), сид 7, "
         "400 сценариев. Это не истина — это твоя модель, прогнанная 400 раз.")

# Фиксированный вход (не из mc_run): рендер — чистая функция данных
RES = {
    "options": {
        "ship": {"mean": 12.5, "median": 10.0, "p10": -8.0, "p90": 40.0},
        "wait": {"mean": 0.0, "median": 0.0, "p10": 0.0, "p90": 0.0},
    },
    "pairwise": {"ship": {"wait": 0.62}, "wait": {"ship": 0.38}},
    "p_best": {"ship": 0.62, "wait": 0.38},
    "expected_regret": {"ship": 3.1, "wait": 12.9},
    "tornado": [{"id": "upside", "impact": 0.91}, {"id": "hours", "impact": 0.22}],
    "top_uncertainties": ["upside", "hours"],
    "label": {"n_uncertainties": 2, "seed": 7, "n": 400, "confirmed": True},
    "histogram": {"bins": 5, "lo": -20.0, "hi": 60.0,
                  "counts": {"ship": [40, 120, 150, 70, 20], "wait": [0, 400, 0, 0, 0]}},
}

NAMES = {"ship": "Выпустить публично", "wait": "Статус-кво"}


def test_md_carries_frame_options_tornado_summary():
    m = render_calc_md(RES, label_text=LABEL, option_names=NAMES)
    assert LABEL in m                                  # «📐 рамка» — обязательная часть подачи
    assert "Выпустить публично" in m and "Статус-кво" in m
    assert "upside" in m and "hours" in m              # торнадо по величинам
    assert "P(лучший)" in m and "0.62" in m
    assert "█" in m                                    # unicode-бары (гистограмма и/или торнадо)
    assert "p10" in m and "p90" in m


def test_md_histogram_sparkline_per_option():
    m = render_calc_md(RES, label_text=LABEL, option_names=NAMES)
    spark_chars = set("▁▂▃▄▅▆▇█")
    assert any(ch in m for ch in spark_chars)          # профиль распределения виден
    # порядок подачи — по P(лучший) убыв.: лидер раньше статус-кво
    assert m.index("Выпустить публично") < m.index("Статус-кво")


def test_tornado_bars_proportional():
    m = render_calc_md(RES, label_text=LABEL, option_names=NAMES)
    lines = [l for l in m.splitlines() if "upside" in l or ("hours" in l and "█" in l)]
    up = next(l for l in lines if "upside" in l)
    hr = next(l for l in lines if "hours" in l)
    assert up.count("█") > hr.count("█")               # impact 0.91 > 0.22 → бар длиннее


def test_pure_and_deterministic():
    a = render_calc_md(RES, label_text=LABEL, option_names=NAMES)
    b = render_calc_md(RES, label_text=LABEL, option_names=NAMES)
    assert a == b
    wa = render_calc_widget(RES, label_text=LABEL, option_names=NAMES)
    wb = render_calc_widget(RES, label_text=LABEL, option_names=NAMES)
    assert wa == wb


def test_widget_follows_cowork_mechanics():
    w = render_calc_widget(RES, label_text=LABEL, option_names=NAMES)
    assert "--color-text-" in w                        # семантические переменные темы
    assert "var(--font-sans" in w                      # шрифт Cowork
    assert 'class="ti ' in w                           # Tabler-иконки, не эмодзи
    assert "📐" not in w and "🔵" not in w              # БЕЗ эмодзи в вёрстке (дизайн-система)
    assert "<script" not in w.lower()
    assert "position:fixed" not in w
    assert "расчёт по ТВОЕЙ модели" in w               # рамка (текст) — в виджете тоже
    assert "Выпустить публично" in w and "upside" in w


def test_widget_histogram_and_tornado_bars_present():
    w = render_calc_widget(RES, label_text=LABEL, option_names=NAMES)
    assert w.count('class="hbin"') == 10               # 5 бинов × 2 варианта
    assert w.count('class="tbar"') == 2                # торнадо-бар на величину


def test_no_histogram_block_renders_gracefully():
    res = {k: v for k, v in RES.items() if k != "histogram"}
    m = render_calc_md(res, label_text=LABEL, option_names=NAMES)
    w = render_calc_widget(res, label_text=LABEL, option_names=NAMES)
    assert "P(лучший)" in m and "upside" in m          # сводка и торнадо живут без гистограммы
    assert 'class="hbin"' not in w


def test_option_names_optional_falls_back_to_ids():
    m = render_calc_md(RES, label_text=LABEL)
    assert "ship" in m and "wait" in m


def test_all_surfaces_escape_xss():
    names = {"ship": "<img src=x onerror=alert(1)>", "wait": "ок"}
    for r in (render_calc_md, render_calc_widget):
        out = r(RES, label_text="<script>alert(1)</script>", option_names=names)
        assert "<img" not in out and "&lt;img" in out
        assert "<script" not in out.lower()


def test_renders_real_mc_run_output_end_to_end():
    m = {
        "question": "тест",
        "options": [{"id": "a", "name": "А"},
                    {"id": "b", "name": "Б", "status_quo": True}],
        "uncertainties": [{"id": "x", "kind": "continuous", "min": 0, "mode": 5,
                           "max": 10, "confirmed_by_user": True, "elicited": "…"}],
        "stakes": {"metric": "часы", "direction": "max"},
        "horizon": "месяц",
        "model": {"a": {"expr": "x + 1", "words": "х плюс один"},
                  "b": {"expr": "x", "words": "х"}},
    }
    res = mc_run(m, seed=42, n=500, histogram=True)
    md = render_calc_md(res, label_text="📐 рамка", option_names={"a": "А", "b": "Б"})
    w = render_calc_widget(res, label_text="📐 рамка", option_names={"a": "А", "b": "Б"})
    assert "А" in md and "x" in md
    assert 'class="hbin"' in w
