#!/usr/bin/env python3
"""Заседание совета: ОДИН канонический data-объект → тонкие рендер-адаптеры под surface.

Архитектура (подтверждена практикой Cowork): объект заседания проходит грунтование и
fidelity-гейт (best_match) ОДИН раз; surface'ы — чистая презентация поверх проверенного
результата. Не дублируем контур по рендерам.

Адаптеры:
  • render_md(s)     — markdown. Портативно: работает в голом Claude Code и через
                       mcp__cowork__present_files. Универсальный текстовый surface.
  • render_widget(s) — HTML-строка для mcp__visualize__show_widget (НАТИВНЫЙ Cowork-рендер):
                       инлайн в ленте, тёмная тема даром через --color-*, клик замыкается в
                       чат через глобальный sendPrompt(). Только в Cowork.
  • render_html(s)   — самодостаточный HTML (свои стили, light/dark). Универсальный фолбэк:
                       файл, открываемый где угодно, в т.ч. вне Cowork.

Маркер достоверности → семантическая переменная Cowork (тема адаптируется авто):
  🔵 blue → --color-text-info · 🟡 yellow → --color-text-warning · нарушение → --color-text-danger

Канонический объект (источник истины):
  {
    "question": str,                                   # обязателен
    "reframe": str | None,                             # переформулировка вопроса советом
    "advisors": [ {
        "name": str,
        "opinions": [ {
            "marker": "blue" | "yellow" | "violation" | None,
            "argument": str,                           # довод на языке юзера
            "quote": {"text": str, "source": str|None, "translation": str|None} | None,
        } ],
    } ],
    "disagreement": {"axis": str, "sides": [str,...], "resolver": str} | None,
    "synthesis": str,                                  # обязателен
    "what_you_lose": str | None,                       # чем платишь за синтез
    "step": str | None,
    "forcing_question": str | None,
  }
plain по умолчанию: числа сюда не кладём (см. правило «Подача» в SKILL.md) — словесный вывод.
"""
import html as _html

_e = _html.escape

# marker → (глиф, семантическая переменная Cowork, self-contained цвет-фолбэк)
_MARK = {
    "blue":      ("🔵", "--color-text-info",    "#2f6fed"),
    "yellow":    ("🟡", "--color-text-warning", "#d98a00"),
    "violation": ("⛔", "--color-text-danger",  "#d64545"),
}


def _marker(m):
    if m == "amber":              # терпим синоним
        m = "yellow"
    return _MARK.get(m)


def _onclick(prompt):
    """sendPrompt('...') безопасно: экранируем для JS-строки и HTML-атрибута."""
    js = prompt.replace("\\", "\\\\").replace("'", "\\'")
    return _e(f"sendPrompt('{js}')", quote=True)


# ---------- markdown (портативный, работает в голом Claude Code) ----------

def render_md(s):
    # _e и в md: Cowork рендерит .md как rich-HTML → raw <img onerror> исполнился бы
    out = ["# Заседание совета", "", f"**Вопрос:** {_e(s['question'])}"]
    if s.get("reframe"):
        out += ["", f"*Совет переформулирует:* {_e(s['reframe'])}"]
    for a in s.get("advisors", []):
        out += ["", f"## {_e(a['name'])}"]
        for op in a.get("opinions", []):
            mk = _marker(op.get("marker"))
            glyph = (mk[0] + " ") if mk else ""
            out.append(f"{glyph}{_e(op['argument'])}")
            q = op.get("quote")
            if q:
                src = f" ({_e(q['source'])})" if q.get("source") else ""
                out.append(f"> «{_e(q['text'])}»{src}")
                if q.get("translation"):
                    out.append(f"> _{_e(q['translation'])}_")
    d = s.get("disagreement")
    if d:
        out += ["", "## Где расходятся", f"**Ось:** {_e(d['axis'])}"]
        out += [f"- {_e(side)}" for side in d.get("sides", [])]
        if d.get("resolver"):
            out.append(f"**Снимается:** {_e(d['resolver'])}")
    out += ["", "## Синтез", _e(s["synthesis"])]
    if s.get("what_you_lose"):
        out.append(f"_Чем платишь:_ {_e(s['what_you_lose'])}")
    if s.get("step"):
        out += ["", "## Шаг", _e(s["step"])]
    if s.get("forcing_question"):
        out += ["", f"**Вопрос-форсаж:** {_e(s['forcing_question'])}"]
    out += ["", "---",
            "🔵 дословная цитата (с источником) · 🟡 мысль в духе автора · отказ вместо выдумки."]
    return "\n".join(out)


# ---------- show_widget (нативный Cowork, кликабельный) ----------

def _opinion_block(op, color_expr):
    mk = _marker(op.get("marker"))
    dot = (f'<span style="color:{color_expr}">{mk[0]}</span> ' if mk else "")
    html = [f'<p style="margin:0 0 6px">{dot}{_e(op["argument"])}</p>']
    q = op.get("quote")
    if q:
        src = f' <span style="opacity:.6;font-size:.85em">({_e(q["source"])})</span>' if q.get("source") else ""
        tr = (f'<span style="display:block;opacity:.75;margin-top:3px">{_e(q["translation"])}</span>'
              if q.get("translation") else "")
        html.append(
            '<blockquote style="margin:0 0 4px;padding:6px 10px;border-radius:8px;'
            'background:var(--color-background-secondary,rgba(127,127,127,.12))">'
            f'<em>«{_e(q["text"])}»</em>{src}{tr}</blockquote>')
    return "".join(html)


def render_widget(s, actions=None):
    """HTML-строка для mcp__visualize__show_widget. actions = [(label, prompt), ...] → кнопки
    sendPrompt. Цвета через --color-* (тёмная тема Cowork адаптируется сама)."""
    if actions is None:
        actions = [("📓 занести в журнал", "занеси это решение в журнал"),
                   ("🔍 покажи разбор", "покажи разбор с числами")]
    bubbles = []
    for a in s.get("advisors", []):
        first_mk = next((_marker(o.get("marker")) for o in a.get("opinions", []) if _marker(o.get("marker"))), None)
        edge = f"var({first_mk[1]},{first_mk[2]})" if first_mk else "var(--color-text-tertiary,#9aa0a6)"
        ops = "".join(_opinion_block(o, edge) for o in a.get("opinions", []))
        bubbles.append(
            f'<article style="border-left:4px solid {edge};padding:4px 14px;margin:0 0 14px">'
            f'<h3 style="margin:0 0 6px;font-size:1.02rem">{_e(a["name"])}</h3>{ops}</article>')
    parts = [
        '<div style="font-family:var(--font-sans,system-ui,sans-serif);'
        'color:var(--color-text-primary,CanvasText);max-width:720px">',
        '<h2 style="font-size:1.25rem;margin:0 0 8px">Заседание совета</h2>',
        f'<p style="margin:0 0 4px"><span style="opacity:.6">Вопрос:</span> {_e(s["question"])}</p>',
    ]
    if s.get("reframe"):
        parts.append(f'<p style="opacity:.8;font-style:italic;margin:0 0 16px">{_e(s["reframe"])}</p>')
    parts += ['<div style="margin:16px 0">', *bubbles, "</div>"]
    d = s.get("disagreement")
    if d:
        sides = " · ".join(_e(x) for x in d.get("sides", []))
        parts.append(
            '<section style="margin:14px 0"><h3 style="font-size:.95rem;opacity:.8;margin:0 0 4px">'
            f'Где расходятся</h3><p style="margin:0"><b>Ось:</b> {_e(d["axis"])}<br>{sides}'
            + (f'<br><b>Снимается:</b> {_e(d["resolver"])}' if d.get("resolver") else "") + "</p></section>")
    parts.append(
        '<section style="border-top:1px solid var(--color-border-primary,rgba(127,127,127,.3));'
        f'padding-top:12px;margin-top:14px"><h3 style="font-size:.95rem;opacity:.8;margin:0 0 4px">'
        f'Синтез</h3><p style="margin:0">{_e(s["synthesis"])}</p>'
        + (f'<p style="opacity:.75;margin:6px 0 0"><em>Чем платишь: {_e(s["what_you_lose"])}</em></p>'
           if s.get("what_you_lose") else "") + "</section>")
    if s.get("step"):
        parts.append('<section style="margin:14px 0"><h3 style="font-size:.95rem;opacity:.8;margin:0 0 4px">'
                     f'Шаг</h3><p style="margin:0;font-weight:600">{_e(s["step"])}</p></section>')
    btns = "".join(
        f'<button onclick="{_onclick(p)}" style="font:inherit;cursor:pointer;'
        'padding:8px 14px;border-radius:999px;border:1px solid '
        'var(--color-border-primary,rgba(127,127,127,.4));background:transparent;'
        f'color:var(--color-text-primary,CanvasText)">{_e(label)}</button>'
        for label, p in actions)
    parts.append(f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px">{btns}</div>')
    parts.append(
        '<p style="margin-top:18px;font-size:.8rem;opacity:.7">🔵 дословная цитата (с источником) · '
        '🟡 мысль в духе автора · отказ вместо выдумки.</p></div>')
    return "".join(parts)


# ---------- self-contained HTML (универсальный фолбэк, вне Cowork) ----------

def _opinion_html(op):
    mk = _marker(op.get("marker"))
    dot = (f'<span class="m">{mk[0]}</span> ' if mk else "")
    h = [f'<p class=arg>{dot}{_e(op["argument"])}</p>']
    q = op.get("quote")
    if q:
        src = f' <span class="src">({_e(q["source"])})</span>' if q.get("source") else ""
        tr = f'<span class="gloss">{_e(q["translation"])}</span>' if q.get("translation") else ""
        h.append(f'<blockquote><em>«{_e(q["text"])}»</em>{src}{tr}</blockquote>')
    return "".join(h)


def render_html(s, title="Заседание совета"):
    body = [f"<h1>{_e(title)}</h1>",
            f'<p class=q><span>Вопрос:</span> {_e(s["question"])}</p>']
    if s.get("reframe"):
        body.append(f'<p class=frame>{_e(s["reframe"])}</p>')
    body.append('<div class="voices">')
    for a in s.get("advisors", []):
        mk = next((_marker(o.get("marker")) for o in a.get("opinions", []) if _marker(o.get("marker"))), None)
        color = mk[2] if mk else "#9aa0a6"
        ops = "".join(_opinion_html(o) for o in a.get("opinions", []))
        body.append(f'<article class="voice" style="border-left-color:{color}">'
                    f'<h2>{_e(a["name"])}</h2>{ops}</article>')
    body.append("</div>")
    d = s.get("disagreement")
    if d:
        sides = "".join(f"<li>{_e(x)}</li>" for x in d.get("sides", []))
        body.append(f'<section class=fault><h3>Где расходятся</h3><p><b>Ось:</b> {_e(d["axis"])}</p>'
                    f'<ul>{sides}</ul>'
                    + (f'<p><b>Снимается:</b> {_e(d["resolver"])}</p>' if d.get("resolver") else "")
                    + "</section>")
    body.append(f'<section class=synth><h3>Синтез</h3><p>{_e(s["synthesis"])}</p>'
                + (f'<p class=lose><em>Чем платишь: {_e(s["what_you_lose"])}</em></p>'
                   if s.get("what_you_lose") else "") + "</section>")
    if s.get("step"):
        body.append(f'<section class=step><h3>Шаг</h3><p>{_e(s["step"])}</p></section>')
    if s.get("forcing_question"):
        body.append(f'<p class=forcing><b>Вопрос-форсаж:</b> {_e(s["forcing_question"])}</p>')
    body.append('<p class=legend>🔵 дословная цитата (с источником) · 🟡 мысль в духе автора · '
                'цитата — в оригинале, перевод рядом как глосса.</p>')
    return (
        "<!doctype html><html lang=ru><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{_e(title)}</title><style>"
        ":root{color-scheme:light dark}"
        "body{font:16px/1.55 system-ui,sans-serif;margin:0 auto;max-width:760px;"
        "padding:24px;background:Canvas;color:CanvasText}"
        "h1{font-size:1.4rem;margin:0 0 12px}h2{font-size:1.05rem;margin:0 0 6px}"
        "h3{font-size:.95rem;margin:0 0 4px;opacity:.8}"
        ".q{font-size:1.05rem;margin:0 0 6px}.q span{opacity:.6}"
        ".frame{opacity:.8;font-style:italic;margin:0 0 18px}"
        ".voices{display:flex;flex-direction:column;gap:14px;margin:18px 0}"
        ".voice{border-left:4px solid;padding:4px 14px}.voice .m{font-size:.9em}"
        ".arg{margin:0 0 8px}"
        "blockquote{margin:0 0 6px;padding:8px 12px;border-radius:8px;"
        "background:color-mix(in srgb,CanvasText 6%,transparent);font-size:.95rem}"
        ".src{opacity:.6;font-size:.85em}.gloss{display:block;opacity:.75;margin-top:4px}"
        "section{margin:16px 0}.synth{border-top:1px solid "
        "color-mix(in srgb,CanvasText 15%,transparent);padding-top:14px}"
        ".step p{font-weight:600}.forcing{opacity:.85}"
        ".legend{margin-top:22px;font-size:.82rem;opacity:.7}"
        "</style>" + "".join(body) + "</html>"
    )
