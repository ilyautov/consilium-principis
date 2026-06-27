"""Grounded-линзы: канон-корпус (public-domain) → потолок поднимается до 🔵.

Frame-линза честна потому, что БЕЗ корпуса (потолок 🟡 by-design). Grounded-линза имеет
PD-канон-корпус + манифест → может говорить 🔵, но ТОЛЬКО если корпус реально есть.
Инвариант честности обобщается: 🔵/🟢 разрешён ⟺ есть корпус. Иначе — претензия на
авторитет без слов (нечестно). Детект корпуса — по раскладке каталога, без модели.
"""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from lenses import (
    load_lens, lens_has_corpus, is_lens_honest, is_frame_lens_honest, list_lenses,
)


def _make_grounded_dir(root, slug, ceiling="🔵", with_corpus=True):
    d = os.path.join(root, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "lens.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {slug}\ngrade: grounded-lens\nmarker_ceiling: {ceiling}\n"
                f"axis: тест\n---\n\n## Кернелы\n- **К:** описание.\n")
    if with_corpus:
        with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"source": "pd:art-of-war", "tier": "P1",
                                "text": "Все войны основаны на обмане."}, ensure_ascii=False) + "\n")
    return d


def test_flat_frame_lens_has_no_corpus():
    assert lens_has_corpus(os.path.join(HERE, "..", "lenses", "cfo.md")) is False


def test_grounded_dir_detected_as_having_corpus():
    with tempfile.TemporaryDirectory() as t:
        d = _make_grounded_dir(t, "strategist", with_corpus=True)
        assert lens_has_corpus(d) is True


def test_grounded_dir_without_corpus_is_not_grounded():
    with tempfile.TemporaryDirectory() as t:
        d = _make_grounded_dir(t, "strategist", with_corpus=False)
        assert lens_has_corpus(d) is False


def test_load_lens_works_on_directory():
    with tempfile.TemporaryDirectory() as t:
        d = _make_grounded_dir(t, "strategist")
        lens = load_lens(d)
        assert lens is not None
        assert lens["grade"] == "grounded-lens"
        assert lens["marker_ceiling"] == "🔵"
        assert "К" in lens["kernels"]


def test_grounded_lens_with_corpus_is_honest():
    lens = {"grade": "grounded-lens", "marker_ceiling": "🔵"}
    assert is_lens_honest(lens, has_corpus=True) is True


def test_grounded_lens_claiming_blue_without_corpus_is_dishonest():
    lens = {"grade": "grounded-lens", "marker_ceiling": "🔵"}
    assert is_lens_honest(lens, has_corpus=False) is False   # авторитет без слов


def test_frame_lens_with_yellow_ceiling_is_honest():
    lens = {"grade": "frame-lens", "marker_ceiling": "🟡"}
    assert is_lens_honest(lens, has_corpus=False) is True


def test_frame_lens_claiming_blue_is_dishonest():
    lens = {"grade": "frame-lens", "marker_ceiling": "🔵"}
    assert is_lens_honest(lens, has_corpus=False) is False
    assert is_frame_lens_honest(lens) is False               # back-compat сохранён


def test_grounded_underclaiming_yellow_is_allowed():
    # есть корпус, но потолок скромный 🟡 — недо-претензия честна
    lens = {"grade": "grounded-lens", "marker_ceiling": "🟡"}
    assert is_lens_honest(lens, has_corpus=True) is True


def test_list_lenses_includes_grounded_dirs():
    with tempfile.TemporaryDirectory() as t:
        # одна flat frame-линза + одна grounded-каталог
        with open(os.path.join(t, "cfo.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: CFO\ngrade: frame-lens\nmarker_ceiling: 🟡\naxis: деньги\n---\n")
        _make_grounded_dir(t, "strategist")
        lenses = list_lenses(t)
        grades = {l["grade"] for l in lenses}
        assert "frame-lens" in grades and "grounded-lens" in grades
