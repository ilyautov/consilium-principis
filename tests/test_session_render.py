"""Один канонический объект заседания → три surface-адаптера (md / show_widget / self-contained
HTML). Тест стережёт: общий источник истины, сохранность контура (маркеры+цитата+источник+перевод),
кликабельность виджета (sendPrompt + семантические --color-*), безопасность (escape, без <script>),
graceful-опускание необязательных полей."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from session_render import render_md, render_widget, render_html, render_opening, _e

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


def test_opening_renders_roster_invitation_chips():
    o = {"advisors": [{"name": "Макиавелли", "domain": "власть", "grounded": True},
                      {"name": "CFO-линза", "domain": "деньги", "grounded": False}],
         "invitation": "Что приносишь на стол?",
         "questions": ["Конкретное решение или открытая ситуация?"],
         "chips": [("конкретное решение", "это конкретное решение"),
                   ("открытая ситуация", "это открытая ситуация")]}
    w = render_opening(o)
    assert "Совет в сборе" in w and "Что приносишь" in w
    assert "власть" in w and "Макиавелли" in w          # роспись с доменами
    assert "sendPrompt(" in w and "конкретное решение" in w   # чипы быстрых ответов
    assert "<script" not in w.lower()


def test_roundtable_turn_no_synthesis_asks_questions():
    # ход круглого стола: реакции советников + вопросы, БЕЗ вердикта; кнопка «давай синтез»
    s = {"question": "как быть?", "advisors": [{"name": "Макиавелли",
         "opinions": [{"marker": "yellow", "argument": "реакция без сочувствия"}]}],
         "questions": ["На чём ты зарабатываешь?", "Что значит «быстро» в цифрах?"]}
    w = render_widget(s)
    assert "Совет спрашивает" in w and "На чём ты зарабатываешь" in w
    assert "Вердикт" not in w                            # синтеза ещё нет
    assert "давай синтез" in w                           # кнопка продвинуть к вердикту
    assert "реакция без сочувствия" in w                 # голос советника на сцене


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

def test_premortem_block_renders_md_and_widget():
    # §4 сценарный слой: pre-mortem — формат заседания; canon несёт premortem:[{advisor,reason}]
    s = {"question": "q", "synthesis": "s", "advisors": [],
         "premortem": [{"advisor": "Макиавелли", "reason": "конкурент скопировал за месяц"},
                       {"advisor": "Аврелий", "reason": "выгорел, не дошипил"}]}
    m = render_md(s)
    assert "Пре-мортем" in m and "конкурент скопировал" in m and "Аврелий" in m
    w = render_widget(s)
    assert "пре-мортем" in w.lower() and "конкурент скопировал" in w
    assert "выгорел, не дошипил" in w
    assert "<script" not in w.lower()


def test_matrix2x2_block_renders_md_and_widget():
    # §4: 2×2 ПОСЛЕ расчёта — оси = top_uncertainties, совет разыгрывает 4 квадранта
    s = {"question": "q", "synthesis": "s", "advisors": [],
         "matrix2x2": {"axes": ["traction_prob", "hours_to_ship"],
                       "quadrants": [
                           {"corner": "++", "name": "быстрый успех", "council_read": "шипим и жмём"},
                           {"corner": "+-", "name": "успех, но дорого", "council_read": "режем скоуп"},
                           {"corner": "-+", "name": "дёшево, но мимо", "council_read": "пивот за неделю"},
                           {"corner": "--", "name": "провал", "council_read": "статус-кво был прав"}]}}
    m = render_md(s)
    assert "2×2" in m and "traction_prob" in m and "hours_to_ship" in m
    assert "быстрый успех" in m and "статус-кво был прав" in m
    w = render_widget(s)
    assert "2×2" in w and "traction_prob" in w
    assert "пивот за неделю" in w and "режем скоуп" in w
    assert "<script" not in w.lower()


def test_scenario_blocks_backward_compat_pinned():
    # бэк-компат ЗАПИНЕН: сессия без блоков (и с пустыми/None) → рендер байт-в-байт
    # как у объекта вовсе без этих ключей; маркеры секций не всплывают
    base_md, base_w = render_md(S), render_widget(S)
    assert "Пре-мортем" not in base_md and "2×2" not in base_md
    for empty in (None, [], {}):
        s2 = dict(S)
        s2["premortem"] = empty
        s2["matrix2x2"] = empty if isinstance(empty, dict) or empty is None else None
        assert render_md(s2) == base_md
        assert render_widget(s2) == base_w


def test_scenario_blocks_malformed_never_crash():
    # та же защита, что у disagreement: кривая структура от хоста НЕ роняет рендер
    bads_pm = ("строка", 42, [{"advisor": "X"}], [{"reason": "без имени"}], [None], [{}])
    bads_mx = ("строка", 42, {"axes": ["one"]}, {"axes": ["a", "b"]},
               {"axes": ["a", "b"], "quadrants": "не список"},
               {"axes": ["a", "b"], "quadrants": [{}]}, {"quadrants": []})
    for pm in bads_pm:
        for r in (render_md, render_widget, render_html):
            r({"question": "q", "synthesis": "s", "advisors": [], "premortem": pm})
    for mx in bads_mx:
        for r in (render_md, render_widget, render_html):
            r({"question": "q", "synthesis": "s", "advisors": [], "matrix2x2": mx})


def test_scenario_blocks_escape_xss():
    s = {"question": "q", "synthesis": "s", "advisors": [],
         "premortem": [{"advisor": "<img src=x onerror=alert(1)>", "reason": "r"}],
         "matrix2x2": {"axes": ["<b>a</b>", "b"],
                       "quadrants": [{"corner": "++", "name": "<img src=y>",
                                      "council_read": "чтение"}]}}
    for r in (render_md, render_widget):
        out = r(s)
        assert "<img" not in out and "&lt;img" in out
        assert "<b>a</b>" not in out


def test_premortem_renders_on_roundtable_turn_too():
    # pre-mortem идёт ДО расчёта, т.е. чаще на ходе круглого стола (без synthesis)
    s = {"question": "q", "advisors": [],
         "questions": ["какую величину мы не учли?"],
         "premortem": [{"advisor": "М", "reason": "рынок не заметил"}]}
    w = render_widget(s)
    assert "рынок не заметил" in w and "Совет спрашивает" in w


def test_theater_never_shows_fake_quote_but_keeps_source():
    # ров в театре: верифицированная цитата + источник видны; пилюля достоверности — под .eng
    s = {"question": "q", "synthesis": "s", "advisors": [{"name": "Макиавелли", "opinions": [
        {"marker": "blue", "argument": "довод", "quote": {"text": "verbatim", "source": "Prince"}}]}]}
    w = render_widget(s)
    assert "verbatim" in w and "Prince" in w           # слова + источник-шёпот видны в театре
    assert 'class="eng"' in w                           # пилюля достоверности спрятана под капот


def test_render_md_html_no_synthesis_no_keyerror():
    # C3: canonical object без 'synthesis' (ход круглого стола) не должен ронять
    # render_md/render_html через KeyError — секция «Синтез» опускается, как в render_widget.
    s = {"question": "Q?", "opinions": [], "abstentions": []}  # нет 'synthesis'
    md = render_md(s)
    html = render_html(s)
    assert "Синтез" not in md and "Синтез" not in html
