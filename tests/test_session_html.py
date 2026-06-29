"""Рендер заседания в HTML — визуализация-surface. Дисплей готовой сессии, не движок:
контур/гейт случаются раньше, сюда приходит проверенный результат. Тест стережёт структуру,
сохранность контура (маркеры+глосса+источник) и безопасность артефакта (без скриптов)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from session_html import render_session_html

_S = {
    "question": "Партнёр хочет 50%, но без инициативы",
    "frame": "Вопрос не про человека, а про условия vs вклад.",
    "voices": [
        {"name": "Макиавелли", "marker": "blue",
         "point": "Ты отдаёшь силу до того, как она проверена.",
         "quote": "they are ungrateful, fickle, false",
         "gloss": "люди неблагодарны, непостоянны, лживы",
         "source": "The Prince, гл. 17"},
        {"name": "CFO-линза", "marker": "amber",
         "point": "50% = претензия на всю стоимость и контроль."},
    ],
    "fault_line": "Защита позиции против не-править-из-паранойи.",
    "synthesis": "Структурируй чисто, но из принципа, на основе вклада.",
    "step": "Положи условия на бумагу: вестинг + доля по вкладу + гейт качества.",
}


def test_valid_html_shell():
    h = render_session_html(_S)
    assert h.startswith("<!doctype html>") and h.rstrip().endswith("</html>")


def test_all_voices_and_sections_present():
    h = render_session_html(_S)
    assert h.count('class="voice"') == 2
    assert "Где расходятся" in h and "Синтез" in h and "Шаг" in h
    assert "условия vs вклад" in h            # frame отрисован


def test_contour_preserved():
    h = render_session_html(_S)
    assert "🔵" in h and "🟡" in h             # маркеры
    assert "The Prince, гл. 17" in h          # источник 🔵
    assert "люди неблагодарны" in h           # глосса-перевод рядом с оригиналом


def test_safe_artifact_escapes_and_no_script():
    h = render_session_html({"question": "<img src=x onerror=alert(1)>",
                             "synthesis": "ok", "voices": []})
    assert "<img" not in h and "<script" not in h.lower()
    assert "&lt;img" in h                      # опасный ввод экранирован


def test_optional_fields_omitted_gracefully():
    h = render_session_html({"question": "q", "synthesis": "s", "voices": []})
    assert "Где расходятся" not in h and "Шаг" not in h   # нет данных → нет секции
