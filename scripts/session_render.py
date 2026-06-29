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


# ---------- show_widget (нативный Cowork, диалоговый формат) ----------
# Советники = чат-баблы с аватарами; маркер достоверности = пилюля (🔵→«дословно»),
# не цветная точка. Без эмодзи в вёрстке (Tabler-иконки), веса 400/500, цвет несёт
# только маркер. Соответствие дизайн-системе Cowork (см. mcp__visualize read_me).

# аватар-акцент: mid-ramp hex, адаптивен в обе темы через color-mix
_AVATAR = ["#534AB7", "#D85A30", "#185FA5", "#1D9E75", "#D4537E", "#BA7517"]

# marker → (подпись, css-bg, css-text, fallback-hex, tabler-иконка)
_PILL = {
    "blue":      ("дословно",     "--color-background-info",    "--color-text-info",    "#185FA5", "ti-quote"),
    "yellow":    ("в духе автора", "--color-background-warning", "--color-text-warning", "#854F0B", "ti-bulb"),
    "violation": ("нарушение",    "--color-background-danger",  "--color-text-danger",  "#A32D2D", "ti-alert-triangle"),
}


def _initials(name):
    import re as _re
    words = [w for w in _re.findall(r"[A-Za-zА-Яа-яЁё]+", name) if w]
    if not words:
        return "•"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def _pill(marker):
    p = _PILL.get("yellow" if marker == "amber" else marker)
    if not p:
        return ""
    label, bg, fg, hexf, icon = p
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;'
            f'font-weight:500;background:var({bg},rgba(55,138,221,.16));color:var({fg},{hexf});'
            f'padding:2px 8px;border-radius:var(--border-radius-md,8px)">'
            f'<i class="ti {icon}" aria-hidden="true"></i>{label}</span>')


def _quote_widget(q, marker):
    if not q:
        return ""
    src = (f'<span style="font-size:11.5px;opacity:.6">{_e(q["source"])}</span>'
           if q.get("source") else "")
    tr = (f'<span style="display:block;font-family:var(--font-sans,system-ui);font-style:normal;'
          f'opacity:.75;margin-top:5px;font-size:12.5px">{_e(q["translation"])}</span>'
          if q.get("translation") else "")
    meta = _pill(marker) + src
    metarow = (f'<span style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:7px;'
               f'font-family:var(--font-sans,system-ui);font-style:normal">{meta}</span>') if meta else ""
    return ('<blockquote style="margin:0 0 4px;padding:8px 12px;border-radius:var(--border-radius-md,8px);'
            'background:color-mix(in srgb,CanvasText 6%,transparent);'
            'font-family:var(--font-serif,Georgia,serif);font-size:13.5px;line-height:1.55">'
            f'«{_e(q["text"])}»{tr}{metarow}</blockquote>')


def render_widget(s, actions=None):
    """Диалоговый HTML для mcp__visualize__show_widget: советники = чат-баблы с аватарами.
    actions = [(label, prompt[, icon]), ...] → кнопки sendPrompt. Цвета через --color-*
    (тёмная тема Cowork адаптируется сама)."""
    if actions is None:
        actions = [("занести в журнал", "занеси это решение совета в журнал", "ti-notebook"),
                   ("оспорить синтез", "оспорь синтез совета как адвокат дьявола", "ti-swords")]
    norm = [(a[0], a[1], a[2] if len(a) == 3 else "ti-arrow-right") for a in actions]

    parts = ['<h2 class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;'
             f'clip:rect(0 0 0 0)">Заседание совета (диалог): {_e(s["question"][:160])}</h2>',
             '<div style="font-family:var(--font-sans,system-ui,sans-serif);'
             'color:var(--color-text-primary,CanvasText);max-width:720px;padding:1rem 0">',
             '<div style="font-size:13px;color:var(--color-text-secondary,#777);margin:0 0 12px">'
             '<i class="ti ti-users-group" aria-hidden="true" style="font-size:15px;vertical-align:-2px;'
             'margin-right:5px"></i>Заседание совета · цитаты сверены с корпусом</div>']

    # реплика юзера
    parts.append('<div style="display:flex;justify-content:flex-end;margin:0 0 4px">'
                 '<div style="max-width:86%;background:var(--color-background-info,rgba(55,138,221,.14));'
                 'border-radius:var(--border-radius-lg,12px);padding:10px 14px">'
                 '<div style="font-size:12px;font-weight:500;color:var(--color-text-info,#185FA5);'
                 'margin-bottom:3px">ты</div>'
                 f'<div style="font-size:14px;line-height:1.6">{_e(s["question"])}</div></div></div>')

    if s.get("reframe"):
        parts.append('<p style="text-align:center;font-size:12.5px;font-style:italic;'
                     'color:var(--color-text-tertiary,#999);margin:10px 24px 18px;line-height:1.55">'
                     f'Совет переформулирует: {_e(s["reframe"])}</p>')

    for i, a in enumerate(s.get("advisors", [])):
        accent = _AVATAR[i % len(_AVATAR)]
        ops = []
        for op in a.get("opinions", []):
            ops.append(f'<p style="margin:0 0 8px;font-size:14px;line-height:1.6">{_e(op["argument"])}</p>')
            ops.append(_quote_widget(op.get("quote"), op.get("marker")))
        bubble = ("".join(ops)).rstrip()
        parts.append(
            '<div style="display:flex;gap:10px;margin:0 0 16px">'
            f'<div style="flex:none;width:40px;height:40px;border-radius:50%;'
            f'background:color-mix(in srgb,{accent} 16%,transparent);color:{accent};'
            'display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:500">'
            f'{_e(_initials(a["name"]))}</div>'
            '<div style="flex:1;min-width:0">'
            f'<div style="font-size:14px;font-weight:500;margin:2px 0 6px">{_e(a["name"])}</div>'
            f'<div style="background:color-mix(in srgb,{accent} 7%,transparent);'
            f'border-radius:var(--border-radius-lg,12px);padding:12px 14px">{bubble}</div></div></div>')

    d = s.get("disagreement")
    if d:
        sides = "; ".join(_e(x) for x in d.get("sides", []))
        res = (f'<br><b style="font-weight:500">Снимается:</b> {_e(d["resolver"])}'
               if d.get("resolver") else "")
        parts.append('<div style="background:var(--color-background-secondary,rgba(127,127,127,.08));'
                     'border-radius:var(--border-radius-lg,12px);padding:12px 16px;margin:18px 0 0">'
                     '<div style="font-size:13px;font-weight:500;color:var(--color-text-secondary,#777);'
                     'margin-bottom:4px"><i class="ti ti-arrows-split" aria-hidden="true" '
                     'style="font-size:15px;vertical-align:-2px;margin-right:5px"></i>Где расходятся</div>'
                     '<p style="margin:0;font-size:13.5px;line-height:1.6">'
                     f'<b style="font-weight:500">Ось:</b> {_e(d["axis"])}<br>{sides}{res}</p></div>')

    syn = ('<div style="border:1.5px solid var(--color-border-info,rgba(55,138,221,.4));'
           'border-radius:var(--border-radius-lg,12px);padding:14px 16px;margin:14px 0 0">'
           '<div style="font-size:13px;font-weight:500;color:var(--color-text-info,#185FA5);'
           'margin-bottom:5px"><i class="ti ti-gavel" aria-hidden="true" style="font-size:15px;'
           'vertical-align:-2px;margin-right:5px"></i>Синтез совета</div>'
           f'<p style="margin:0;font-size:14px;line-height:1.65">{_e(s["synthesis"])}</p>')
    if s.get("what_you_lose"):
        syn += ('<p style="margin:8px 0 0;font-size:12.5px;line-height:1.55;'
                'color:var(--color-text-secondary,#777)"><i class="ti ti-coin" aria-hidden="true" '
                'style="font-size:14px;vertical-align:-2px;margin-right:4px"></i>Чем платишь: '
                f'{_e(s["what_you_lose"])}</p>')
    parts.append(syn + "</div>")

    if s.get("step"):
        parts.append('<div style="display:flex;align-items:flex-start;gap:8px;margin:14px 0 0;'
                     'font-size:14px;line-height:1.6"><i class="ti ti-arrow-right" aria-hidden="true" '
                     'style="font-size:17px;color:var(--color-text-info,#185FA5);margin-top:2px"></i>'
                     f'<div><b style="font-weight:500">Шаг:</b> {_e(s["step"])}</div></div>')

    if s.get("forcing_question"):
        parts.append('<p style="margin:12px 0 0;font-size:13px;font-style:italic;'
                     'color:var(--color-text-tertiary,#999);line-height:1.55">'
                     '<i class="ti ti-help-circle" aria-hidden="true" style="font-style:normal;'
                     'vertical-align:-2px;margin-right:4px"></i>Вопрос-форсаж: '
                     f'{_e(s["forcing_question"])}</p>')

    btns = "".join(
        f'<button onclick="{_onclick(p)}" style="font:inherit;cursor:pointer;padding:8px 14px;'
        'border-radius:999px;border:.5px solid var(--color-border-secondary,rgba(127,127,127,.4));'
        'background:transparent;color:var(--color-text-primary,CanvasText)">'
        f'<i class="ti {icon}" aria-hidden="true" style="margin-right:5px"></i>{_e(label)}</button>'
        for label, p, icon in norm)
    parts.append(f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:18px">{btns}</div>')

    parts.append('<p style="margin-top:16px;font-size:11.5px;color:var(--color-text-tertiary,#999);'
                 'line-height:1.5"><span style="display:inline-flex;align-items:center;gap:3px;'
                 'color:var(--color-text-info,#185FA5)"><i class="ti ti-quote" aria-hidden="true"></i>'
                 'дословно</span> — сверено с корпусом первоисточника · отказ вместо выдумки, если '
                 'совпадения нет.</p>')
    parts.append("</div>")
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
