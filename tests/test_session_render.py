"""Один канонический объект заседания → три surface-адаптера (md / show_widget / self-contained
HTML). Тест стережёт: общий источник истины, сохранность контура (маркеры+цитата+источник+перевод),
кликабельность виджета (sendPrompt + семантические --color-*), безопасность (escape, без <script>),
graceful-опускание необязательных полей."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from session_render import render_md, render_widget, render_html, _e

S = {
    "question": "Партнёр хочет 50%, но без инициативы",
    "reframe": "Вопрос не про человека, а про условия vs вклад.",
    "advisors": [
        {"name": "Макиавелли", "opinions": [{
            "marker": "blue", "argument": "Ты отдаёшь силу до того, как она проверена.",
            "quote": {"text": "they are ungrateful, fickle, false",
                      "source": "The Prince, гл. 17",
                      "translation": "люди неблагодарны, непостоянны, лживы"}}]},
        {"name": "CFO-линза", "opinions": [{
            "marker": "yellow", "argument": "50% = претензия на всю стоимость и контроль."}]},
    ],
    "disagreement": {"axis": "защита позиции vs не-править-из-паранойи",
                     "sides": ["структурируй защиту", "не подозревай зря"],
                     "resolver": "структурируй из принципа, на основе вклада"},
    "synthesis": "Структурируй чисто, но из принципа.",
    "what_you_lose": "немного скорости на берегу",
    "step": "Положи условия на бумагу: вестинг + доля по вкладу + гейт качества.",
    "forcing_question": "Согласится ли он на вестинг?",
}


def test_md_carries_full_structure_and_contour():
    m = render_md(S)
    assert m.startswith("# Заседание совета")
    assert "Макиавелли" in m and "CFO-линза" in m
    assert "🔵" in m and "🟡" in m
    assert "The Prince, гл. 17" in m and "люди неблагодарны" in m   # источник + глосса
    assert "## Синтез" in m and "Вопрос-форсаж" in m


def test_widget_is_clickable_and_theme_aware():
    w = render_widget(S)
    assert "sendPrompt(" in w                       # клик замыкается в чат
    assert "--color-text-info" in w                 # семантическая переменная темы (тёмная даром)
    assert "var(--font-sans" in w                   # шрифт Cowork
    assert 'class="ti ' in w                        # Tabler-иконки (дизайн-система Cowork)
    assert "🔵" not in w and "🟡" not in w           # БЕЗ эмодзи в вёрстке виджета (дизайн-система)
    assert "<script" not in w.lower()               # без тега script (только inline onclick)
    assert "position:fixed" not in w                # iframe-констрейнт Cowork (sr-only = absolute, ок)


def test_widget_custom_actions():
    w = render_widget(S, actions=[("Старт", "/board recipe start")])
    assert "/board recipe start" in w and "Старт" in w


def test_html_fallback_self_contained():
    h = render_html(S)
    assert h.startswith("<!doctype html>") and h.rstrip().endswith("</html>")
    assert h.count('class="voice"') == 2
    assert "Где расходятся" in h and "The Prince" in h


def test_amber_synonym_maps_to_yellow():
    # пилюля достоверности в диалоговом виджете висит на ЦИТАТЕ → даём цитату с маркером amber
    s = {"question": "q", "synthesis": "s",
         "advisors": [{"name": "X", "opinions": [{"marker": "amber", "argument": "a",
            "quote": {"text": "t", "source": "src"}}]}]}
    assert "🟡" in render_md(s)                       # md сохраняет эмодзи-маркер
    assert "--color-text-warning" in render_widget(s)  # пилюля «в духе автора» (amber→yellow)


def test_widget_marker_pill_rides_on_quote():
    # КОНТУР в диалоговом surface: пилюля «дословно/в духе автора» рендерится при наличии цитаты
    with_q = {"question": "q", "synthesis": "s", "advisors": [{"name": "X", "opinions": [
        {"marker": "blue", "argument": "a", "quote": {"text": "t", "source": "Prince"}}]}]}
    assert "дословно" in render_widget(with_q) and "Prince" in render_widget(with_q)


def test_malformed_disagreement_never_crashes_render():
    # БАГ из живого прогона: кривой disagreement рушил рендер → пересборка лезла в чат.
    for bad in ({"axis": "X"}, {"sides": ["a", "b"]}, "строка", {"axis": None}, None, []):
        s = {"question": "q", "synthesis": "s", "advisors": [], "disagreement": bad}
        for r in (render_md, render_widget, render_html):
            r(s)                                       # не должно бросить
    # валидный disagreement всё ещё рендерится
    ok = {"question": "q", "synthesis": "s", "advisors": [],
          "disagreement": {"axis": "ось спора", "sides": ["a", "b"], "resolver": "r"}}
    assert "ось спора" in render_widget(ok)


def test_all_surfaces_escape_xss():
    bad = {"question": "<img src=x onerror=alert(1)>", "synthesis": "ok", "advisors": []}
    for r in (render_md, render_widget, render_html):
        out = r(bad)
        assert "<img" not in out and "&lt;img" in out


def test_optional_fields_omitted():
    s = {"question": "q", "synthesis": "s", "advisors": []}
    for r in (render_md, render_widget, render_html):
        out = r(s)
        assert "Где расходятся" not in out and "Шаг" not in out


def test_theater_default_engineering_under_toggle():
    # ТЕАТР по умолчанию: машинерия не вырезана, а под .eng (CSS-скрыта), раскрывается тумблером.
    plain = render_widget(S)
    assert 'class="cp-stage"' in plain                 # корень БЕЗ show-eng → театр
    assert "cp-stage show-eng" not in plain
    assert 'class="cost eng"' in plain                 # «цена» присутствует, но под капотом (.eng)
    assert "показать инженерию" in plain               # тумблер на месте
    assert "<script" not in plain.lower()              # тумблер — inline classList, не скрипт
    # синтез и голоса видны ВСЕГДА (это суть, не шум)
    assert _e(S["synthesis"]) in plain and "sendPrompt(" in plain

def test_theater_expert_reveals_engineering_by_default():
    expert = render_widget(S, depth="expert")
    assert "cp-stage show-eng" in expert               # инженерия раскрыта сразу
    assert "Чем платишь" in expert                     # та же разметка, просто видима

def test_theater_never_shows_fake_quote_but_keeps_source():
    # ров в театре: верифицированная цитата + источник видны; пилюля достоверности — под .eng
    s = {"question": "q", "synthesis": "s", "advisors": [{"name": "Макиавелли", "opinions": [
        {"marker": "blue", "argument": "довод", "quote": {"text": "verbatim", "source": "Prince"}}]}]}
    w = render_widget(s)
    assert "verbatim" in w and "Prince" in w           # слова + источник-шёпот видны в театре
    assert 'class="eng"' in w                           # пилюля достоверности спрятана под капот
