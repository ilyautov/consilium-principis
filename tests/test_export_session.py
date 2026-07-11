"""export_session — шеримый пруф заседания: базовый рендер + панель абстеншенов + share-футер.
Инвариант приватности: работает ТОЛЬКО с переданным объектом, файлов не читает/не пишет."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from session_render import export_session

SESSION = {
    "question": "Уйти в свой продукт или остаться в найме?",
    "advisors": [
        {"name": "Марк Аврелий", "opinions": [
            {"argument": "Смотри на то, что в твоей власти.", "marker": "blue",
             "quote": {"text": "Confine thyself to the present.", "source": "Meditations 7.29"}}]},
    ],
    "synthesis": "Проверь гипотезу малым шагом, не сжигая мостов.",
    "step": "Выдели 2 недели на пилот вечерами.",
    "abstentions": ["точный размер рынка нанятого сегмента", "чей именно продукт взлетит"],
}


def test_md_carries_question_synthesis_and_quote():
    out = export_session(SESSION, surface="md")["content"]
    assert "Уйти в свой продукт" in out
    assert "Проверь гипотезу" in out
    assert "Confine thyself to the present." in out and "Meditations 7.29" in out


def test_abstentions_panel_present_when_provided():
    out = export_session(SESSION, surface="md")["content"]
    assert "Что совет НЕ стал выдумывать" in out
    assert "точный размер рынка" in out


def test_no_abstentions_panel_when_absent():
    s = {k: v for k, v in SESSION.items() if k != "abstentions"}
    out = export_session(s, surface="md")["content"]
    assert "Что совет НЕ стал выдумывать" not in out


def test_share_footer_attribution_present():
    for surface in ("md", "html"):
        out = export_session(SESSION, surface=surface)["content"]
        assert "Consilium-Principis" in out
        assert "посимвольно" in out


def test_html_surface_is_safe_and_self_contained():
    out = export_session(SESSION, surface="html")["content"]
    assert out.startswith("<!doctype html>") and out.endswith("</html>")
    assert "<script" not in out.lower()
    assert "Что совет НЕ стал выдумывать" in out


def test_invalid_session_fails_closed():
    r = export_session({"advisors": []}, surface="md")   # нет question
    assert "error" in r and "content" not in r


def test_include_abstentions_false_suppresses_panel():
    out = export_session(SESSION, surface="md", include_abstentions=False)["content"]
    assert "Что совет НЕ стал выдумывать" not in out
