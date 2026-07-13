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
            "marker": "blue" | "green" | "yellow" | "violation" | None,
            "argument": str,                           # довод на языке юзера
            "quote": {"text": str, "source": str|None, "translation": str|None} | None,
        } ],
    } ],
    "disagreement": {"axis": str, "sides": [str,...], "resolver": str} | None,
    "premortem": [ {"advisor": str, "reason": str} ] | None,      # §4: pre-mortem ДО расчёта
    "matrix2x2": {"axes": [str, str],                             # §4: 2×2 ПОСЛЕ расчёта
                  "quadrants": [{"corner": str, "name": str, "council_read": str}]} | None,
    "synthesis": str,                                  # обязателен
    "what_you_lose": str | None,                       # чем платишь за синтез
    "step": str | None,
    "forcing_question": str | None,
  }
plain по умолчанию: числа сюда не кладём (см. правило «Подача» в SKILL.md) — словесный вывод.
"""
import html as _html

_e = _html.escape


def _disagreement(s):
    """Нормализованный блок несогласия или None. Защита: хост может прислать кривую структуру
    (без axis / не-dict / axis=None) — рендер НЕ должен падать (иначе пересборка лезет в чат)."""
    d = s.get("disagreement")
    if isinstance(d, dict) and d.get("axis"):
        sides = d.get("sides")
        return {"axis": d["axis"],
                "sides": [x for x in sides if x] if isinstance(sides, list) else [],
                "resolver": d.get("resolver")}
    return None

def _premortem_items(s):
    """Нормализованный pre-mortem (§4, «прошёл год — почему провалилось») или []. Та же
    защита, что _disagreement: кривая структура от хоста НЕ роняет рендер. Элемент живёт
    только с ОБОИМИ полями (advisor+reason) — половинки тихо опускаются (fail-closed)."""
    p = s.get("premortem")
    if not isinstance(p, list):
        return []
    return [{"advisor": str(it["advisor"]), "reason": str(it["reason"])}
            for it in p
            if isinstance(it, dict) and it.get("advisor") and it.get("reason")]


def _matrix2x2(s):
    """Нормализованный 2×2 (§4, оси = top_uncertainties расчёта) или None. Fail-closed:
    без ровно двух непустых осей или без валидных квадрантов блок не рендерится."""
    m = s.get("matrix2x2")
    if not isinstance(m, dict):
        return None
    axes = m.get("axes")
    if not (isinstance(axes, list) and len(axes) == 2 and all(axes)):
        return None
    quads = m.get("quadrants")
    if not isinstance(quads, list):
        return None
    q_out = [{"corner": str(q["corner"]), "name": str(q.get("name") or ""),
              "council_read": str(q["council_read"])}
             for q in quads
             if isinstance(q, dict) and q.get("corner") and q.get("council_read")]
    if not q_out:
        return None
    return {"axes": [str(a) for a in axes], "quadrants": q_out}


# marker → (глиф, семантическая переменная Cowork, self-contained цвет-фолбэк)
_MARK = {
    "blue":      ("🔵", "--color-text-info",    "#2f6fed"),
    "green":     ("🟢", "--color-text-success", "#1D9E75"),   # дословно из комментария (S-тир)
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
    d = _disagreement(s)
    if d:
        out += ["", "## Где расходятся", f"**Ось:** {_e(d['axis'])}"]
        out += [f"- {_e(side)}" for side in d["sides"]]
        if d.get("resolver"):
            out.append(f"**Снимается:** {_e(d['resolver'])}")
    pm = _premortem_items(s)
    if pm:
        out += ["", "## Пре-мортем — год спустя, вариант провалился: почему?"]
        out += [f"- **{_e(it['advisor'])}:** {_e(it['reason'])}" for it in pm]
    mx = _matrix2x2(s)
    if mx:
        out += ["", f"## 2×2: {_e(mx['axes'][0])} × {_e(mx['axes'][1])}"]
        for q in mx["quadrants"]:
            nm = f" · {_e(q['name'])}" if q["name"] else ""
            out.append(f"- **{_e(q['corner'])}{nm}:** {_e(q['council_read'])}")
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
    "green":     ("комментарий",  "--color-background-success", "--color-text-success", "#1D9E75", "ti-book"),
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


# Сценический стиль (scoped под .cp-stage). Тумблер инженерии = .show-eng (inline classList.toggle,
# без <script>). По умолчанию театр: .eng скрыт. CSS, не JS — CSP-safe.
_STAGE_STYLE = (
 '<style>'
 '.cp-stage{font-family:var(--font-serif,Georgia,"Times New Roman",serif);'
 'color:var(--color-text-primary,CanvasText);max-width:600px;margin:0 auto;padding:6px 6px 4px;line-height:1.6}'
 '.cp-stage .eyebrow{font-family:var(--font-sans,system-ui,sans-serif);font-size:11px;letter-spacing:.24em;'
 'text-transform:uppercase;color:var(--color-text-tertiary,#999);text-align:center;margin:2px 0 12px}'
 '.cp-stage .eyebrow i{font-style:normal;margin-right:8px;font-size:15px;vertical-align:-3px}'
 '.cp-stage .matter{font-size:20px;line-height:1.4;text-align:center;font-weight:400;margin:0 auto;max-width:30ch}'
 '.cp-stage .rule{display:flex;align-items:center;justify-content:center;gap:11px;margin:15px auto 4px;'
 'color:var(--color-text-tertiary,#aaa);max-width:280px}'
 '.cp-stage .rule::before,.cp-stage .rule::after{content:"";height:1px;flex:1;background:currentColor;opacity:.35}'
 '.cp-stage .rule i{font-style:normal;font-size:12px;opacity:.7}'
 '.cp-stage .aside{text-align:center;font-style:italic;font-size:14.5px;color:var(--color-text-secondary,#888);'
 'margin:6px 18px 4px;line-height:1.55}'
 '.cp-stage .char{margin:24px 0 0;display:flex;gap:15px}'
 '.cp-stage .med{flex:none;width:46px;height:46px;border-radius:50%;display:flex;align-items:center;'
 'justify-content:center;font-size:15px;font-weight:500;font-family:var(--font-serif,Georgia,serif)}'
 '.cp-stage .col{flex:1;min-width:0;padding-top:1px}'
 '.cp-stage .nm{font-family:var(--font-sans,system-ui,sans-serif);font-size:12px;letter-spacing:.13em;'
 'text-transform:uppercase;font-weight:500;margin:5px 0 9px}'
 '.cp-stage .stage{padding-left:15px;border-left:2px solid}'
 '.cp-stage .speech{font-size:15px;line-height:1.62;margin:0 0 11px}'
 '.cp-stage .pull{margin:2px 0 13px;font-size:16px;line-height:1.5;font-style:italic}'
 '.cp-stage .pull .qm{font-family:Georgia,serif;font-style:normal;font-size:26px;line-height:0;'
 'opacity:.4;margin-right:3px;vertical-align:-6px}'
 '.cp-stage .pull .tr{display:block;font-style:normal;font-size:12.5px;opacity:.65;margin-top:5px}'
 '.cp-stage .pull cite{display:block;font-style:normal;font-family:var(--font-sans,system-ui,sans-serif);'
 'font-size:11px;letter-spacing:.05em;text-transform:uppercase;opacity:.5;margin-top:7px}'
 '.cp-stage .rift{margin:24px auto 0;max-width:520px;text-align:center;font-size:14px;line-height:1.6}'
 '.cp-stage .rift .rl{font-family:var(--font-sans,system-ui,sans-serif);font-size:11px;letter-spacing:.18em;'
 'text-transform:uppercase;color:var(--color-text-tertiary,#999);margin-bottom:9px}'
 '.cp-stage .rift .sd{display:block;margin:3px 0;opacity:.92}'
 '.cp-stage .rift .rs{display:block;margin-top:9px;font-style:italic;color:var(--color-text-secondary,#888)}'
 '.cp-stage .verdict{margin:28px auto 2px;text-align:center}'
 '.cp-stage .vlabel{display:flex;align-items:center;justify-content:center;gap:11px;'
 'font-family:var(--font-sans,system-ui,sans-serif);font-size:11.5px;letter-spacing:.24em;text-transform:uppercase;'
 'color:var(--color-text-info,#185FA5);margin-bottom:11px}'
 '.cp-stage .vlabel::before,.cp-stage .vlabel::after{content:"";height:1px;width:34px;'
 'background:currentColor;opacity:.4}'
 '.cp-stage .vtext{font-size:17px;line-height:1.52;max-width:40ch;margin:0 auto;font-weight:400}'
 '.cp-stage .cost{font-family:var(--font-sans,system-ui,sans-serif);font-size:12.5px;font-style:normal;'
 'color:var(--color-text-secondary,#888);margin:11px auto 0;max-width:34ch;line-height:1.5}'
 '.cp-stage .step{font-family:var(--font-sans,system-ui,sans-serif);font-size:14px;text-align:center;'
 'margin:18px 16px 0;line-height:1.55;color:var(--color-text-primary,CanvasText)}'
 '.cp-stage .step i{font-style:normal;color:var(--color-text-info,#185FA5);margin-right:6px}'
 '.cp-stage .forcing{font-family:var(--font-sans,system-ui,sans-serif);font-size:12.5px;font-style:italic;'
 'text-align:center;color:var(--color-text-tertiary,#999);margin:13px 20px 0;line-height:1.5}'
 '.cp-stage .eng{display:none}'
 '.cp-stage.show-eng .eng{display:revert}'
 '.cp-stage .pill{display:inline-flex;align-items:center;gap:4px;font-family:var(--font-sans,system-ui,sans-serif);'
 'font-style:normal;font-size:10.5px;font-weight:500;padding:1px 7px;border-radius:var(--border-radius-md,7px);'
 'margin-top:6px;vertical-align:middle}'
 '.cp-stage .pill i{font-style:normal}'
 '.cp-stage .toggle{text-align:center;margin:22px 0 0}'
 '.cp-stage .toggle button{font-family:var(--font-sans,system-ui,sans-serif);font-size:12px;letter-spacing:.03em;'
 'cursor:pointer;background:transparent;border:none;color:var(--color-text-info,#6BA9E8);padding:6px 10px}'
 '.cp-stage .toggle i{font-style:normal;margin-right:5px;vertical-align:-2px}'
 '.cp-stage .lbl-hide{display:none}.cp-stage.show-eng .lbl-show{display:none}.cp-stage.show-eng .lbl-hide{display:inline}'
 '.cp-stage .legend{font-family:var(--font-sans,system-ui,sans-serif);font-size:11px;text-align:center;'
 'color:var(--color-text-tertiary,#999);margin:10px 16px 0;line-height:1.5}'
 '.cp-stage .acts{display:flex;gap:9px;flex-wrap:wrap;justify-content:center;margin:20px 0 2px}'
 '.cp-stage .acts button{font-family:var(--font-sans,system-ui,sans-serif);font-size:12.5px;cursor:pointer;'
 'padding:7px 15px;border-radius:999px;border:.5px solid var(--color-border-secondary,rgba(127,127,127,.4));'
 'background:transparent;color:var(--color-text-primary,CanvasText)}'
 '.cp-stage .acts i{margin-right:5px}'
 '.cp-stage .roster{margin:16px 0 0}'
 '.cp-stage .seat{display:flex;gap:13px;align-items:flex-start;margin:14px 0 0}'
 '.cp-stage .seat .med{width:38px;height:38px;font-size:13px}'
 '.cp-stage .seat .who{flex:1;min-width:0;padding-top:3px}'
 '.cp-stage .seat .nm{margin:0 0 3px}'
 '.cp-stage .seat .dom{font-size:14px;line-height:1.5;color:var(--color-text-secondary,#888)}'
 '.cp-stage .seat .src{font-size:12px;line-height:1.45;color:var(--color-text-secondary,#999);'
 'opacity:.8;margin-top:3px;display:flex;align-items:baseline;gap:5px}'
 '.cp-stage .seat .src .ti{font-size:11px;opacity:.7}'
 '.cp-stage .disclosure{display:flex;align-items:baseline;gap:8px;margin:22px auto 0;max-width:52ch;'
 'padding:11px 14px;border-radius:10px;background:color-mix(in srgb,var(--color-text-info,#185FA5) 7%,transparent);'
 'font-size:12.5px;line-height:1.5;color:var(--color-text-secondary,#888);text-align:left}'
 '.cp-stage .disclosure .ti{font-size:13px;opacity:.75;flex:none;position:relative;top:2px}'
 '.cp-stage .disclosure b{font-weight:600;color:var(--color-text-primary,#ddd)}'
 '.cp-stage .invite{text-align:center;font-size:18px;line-height:1.46;margin:22px auto 2px;max-width:34ch}'
 '.cp-stage .asks{margin:14px auto 0;max-width:34ch;text-align:center}'
 '.cp-stage .asks .q{font-style:italic;font-size:15px;line-height:1.5;'
 'color:var(--color-text-secondary,#999);margin:7px 0}'
 '.cp-stage .qask{margin:26px auto 0;max-width:540px}'
 '.cp-stage .qask .q{font-size:14.5px;line-height:1.6;margin:12px 0;padding-left:19px;position:relative}'
 '.cp-stage .qask .q::before{content:"";position:absolute;left:0;top:8px;width:6px;height:6px;'
 'border-radius:50%;background:var(--color-text-info,#185FA5);opacity:.65}'
 '</style>')


# AI-disclosure на занавесе (EU AI Act Art.50(1)/(5): ясно и различимо при ПЕРВОМ контакте;
# музейный Lister-GPT паттерн — открытое отрицание буквальной идентичности; NO FAKES: прозрачность,
# не щит). Несёт: что это (AI-представление) · метод (заземлено на публичных текстах) · что
# гарантирует 🔵 и чего НЕ гарантирует (не сами люди / 🟡 — не их слова).
_DISCLOSURE_PLATE = (
    '<div class="disclosure"><i class="ti ti-info-circle" aria-hidden="true"></i>'
    '<span>Это AI-советники — представления мыслителей, заземлённые на их публичных текстах, '
    'а не сами люди. <b>🔵</b> — дословно из корпуса; <b>🟡</b> — экстраполяция, не их слова.</span></div>')


def render_opening(o, actions=None):
    """Сценический ОПЕНИНГ круглого стола (занавес поднят): роспись советников (dramatis personae) +
    приглашение + опц. уточняющие вопросы. o={advisors:[{name, domain?, grounded?}], invitation?,
    questions?, chips?}. actions/chips → sendPrompt быстрые ответы. grounded=False (линза) → без glow."""
    seats = []
    for i, a in enumerate(o.get("advisors", [])):
        accent = _AVATAR[i % len(_AVATAR)]
        glow = ((f'box-shadow:0 0 0 1px color-mix(in srgb,{accent} 40%,transparent),'
                 f'0 3px 16px color-mix(in srgb,{accent} 22%,transparent)')
                if a.get("grounded", True) else 'opacity:.8')
        med = f'background:color-mix(in srgb,{accent} 18%,transparent);color:{accent};{glow}'
        dom = f'<div class="dom">{_e(a["domain"])}</div>' if a.get("domain") else ""
        # Per-persona provenance (издание/источник корпуса) — под именем, если хост передал.
        prov = f'<div class="src"><i class="ti ti-book" aria-hidden="true"></i>{_e(a["provenance"])}</div>' \
            if a.get("provenance") else ""
        seats.append(f'<div class="seat"><div class="med" style="{med}">{_e(_initials(a["name"]))}</div>'
                     f'<div class="who"><div class="nm">{_e(a["name"])}</div>{dom}{prov}</div></div>')
    invite = f'<p class="invite">{_e(o["invitation"])}</p>' if o.get("invitation") else ""
    qs = o.get("questions") or []
    asks = ('<div class="asks">' + "".join(f'<p class="q">{_e(q)}</p>' for q in qs) + '</div>') if qs else ""
    chips = actions or o.get("chips")
    btns = ""
    if chips:
        norm = [(c[0], c[1], c[2] if len(c) == 3 else "ti-arrow-right") for c in chips]
        btns = ('<div class="acts">' + "".join(
            f'<button onclick="{_onclick(p)}"><i class="ti {icon}" aria-hidden="true"></i>{_e(label)}</button>'
            for label, p, icon in norm) + '</div>')
    return (_STAGE_STYLE + '<div class="cp-stage">'
            '<div class="eyebrow"><i class="ti ti-masks-theater" aria-hidden="true"></i>Совет в сборе</div>'
            f'<div class="roster">{"".join(seats)}</div>'
            '<div class="rule"><i class="ti ti-diamond" aria-hidden="true"></i></div>'
            f'{invite}{asks}{btns}{_DISCLOSURE_PLATE}</div>')


def _pull_quote(q, marker):
    """Сценическая pull-цитата: дословные слова + источник-шёпот (виден всегда, честно). Пилюля
    достоверности — только .eng (под капотом). Перевод-глосса рядом."""
    if not q:
        return ""
    tr = (f'<span class="tr">{_e(q["translation"])}</span>' if q.get("translation") else "")
    cite = f'<cite>{_e(q["source"])}</cite>' if q.get("source") else ""
    pill = (f'<span class="eng">{_pill(marker)}</span>' if _pill(marker) else "")
    return f'<div class="pull"><span class="qm">«</span>{_e(q["text"])}»{tr}{cite}{pill}</div>'


def render_widget(s, actions=None, depth="plain"):
    """show_widget (Cowork): ход заседания как СЦЕНА (театр по умолчанию), инженерия — под тумблером.
    Рендерит ЛЮБОЙ ход: реакции+вопросы (без synthesis — круглый стол) ИЛИ синтез-вердикт (с synthesis).
    s.questions=[...] → блок «совет спрашивает». actions=[(label,prompt[,icon])] → sendPrompt. depth:
    plain (театр) | expert (.show-eng). Ров: верифиц. цитата+источник видны, пилюли — .eng (тумблер)."""
    has_synth = bool(s.get("synthesis"))
    if actions is None:
        actions = ([("занести в журнал", "занеси это решение совета в журнал", "ti-notebook"),
                    ("оспорить синтез", "оспорь синтез совета как адвокат дьявола", "ti-swords")]
                   if has_synth else
                   [("давай синтез", "давай синтез сейчас, не доспрашивая", "ti-gavel")])
    norm = [(a[0], a[1], a[2] if len(a) == 3 else "ti-arrow-right") for a in actions]
    root_cls = "cp-stage show-eng" if depth == "expert" else "cp-stage"

    parts = [_STAGE_STYLE,
             f'<div class="{root_cls}">',
             '<h2 style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">'
             f'Заседание совета: {_e(s["question"][:160])}</h2>',
             '<div class="eyebrow"><i class="ti ti-masks-theater" aria-hidden="true"></i>Заседание совета</div>',
             f'<div class="matter">{_e(s["question"])}</div>',
             '<div class="rule"><i class="ti ti-diamond" aria-hidden="true"></i></div>']

    if s.get("reframe"):
        parts.append(f'<p class="aside">Совет видит иначе: {_e(s["reframe"])}</p>')

    for i, a in enumerate(s.get("advisors", [])):
        accent = _AVATAR[i % len(_AVATAR)]
        lines = []
        for op in a.get("opinions", []):
            lines.append(f'<p class="speech">{_e(op["argument"])}</p>')
            lines.append(_pull_quote(op.get("quote"), op.get("marker")))
        body = "".join(lines).rstrip()
        med_style = (f'background:color-mix(in srgb,{accent} 18%,transparent);color:{accent};'
                     f'box-shadow:0 0 0 1px color-mix(in srgb,{accent} 40%,transparent),'
                     f'0 3px 16px color-mix(in srgb,{accent} 22%,transparent)')
        parts.append(
            f'<div class="char"><div class="med" style="{med_style}">{_e(_initials(a["name"]))}</div>'
            f'<div class="col"><div class="nm">{_e(a["name"])}</div>'
            f'<div class="stage" style="border-color:color-mix(in srgb,{accent} 55%,transparent)">'
            f'{body}</div></div></div>')

    d = _disagreement(s)
    if d:
        sd = "".join(f'<span class="sd">{_e(x)}</span>' for x in d["sides"])
        rs = (f'<span class="rs">{_e(d["resolver"])}</span>' if d.get("resolver") else "")
        parts.append('<div class="rift"><div class="rl">где расходятся</div>'
                     f'<b style="font-weight:500">{_e(d["axis"])}</b>{sd}{rs}</div>')

    pm = _premortem_items(s)
    if pm:                                          # §4: pre-mortem — заседание, не счёт
        rows = "".join(f'<span class="sd"><b style="font-weight:500">{_e(it["advisor"])}</b>'
                       f' — {_e(it["reason"])}</span>' for it in pm)
        parts.append('<div class="rift"><div class="rl">пре-мортем · год спустя — почему '
                     f'провалилось</div>{rows}</div>')

    mx = _matrix2x2(s)
    if mx:                                          # §4: 2×2 по осям торнадо (после расчёта)
        rows = []
        for q in mx["quadrants"]:
            nm = f' · {_e(q["name"])}' if q["name"] else ""
            rows.append(f'<span class="sd"><b style="font-weight:500">{_e(q["corner"])}{nm}</b>'
                        f' — {_e(q["council_read"])}</span>')
        parts.append(f'<div class="rift"><div class="rl">2×2 · {_e(mx["axes"][0])} × '
                     f'{_e(mx["axes"][1])}</div>{"".join(rows)}</div>')

    qs = s.get("questions") or []
    if qs:                                          # ход круглого стола: совет допрашивает до синтеза
        items = "".join(f'<p class="q">{_e(q)}</p>' for q in qs)
        parts.append('<div class="qask"><div class="vlabel">Совет спрашивает</div>'
                     f'{items}</div>')

    if has_synth:
        cost = (f'<p class="cost eng">Чем платишь: {_e(s["what_you_lose"])}</p>'
                if s.get("what_you_lose") else "")
        parts.append('<div class="verdict"><div class="vlabel">Вердикт</div>'
                     f'<p class="vtext">{_e(s["synthesis"])}</p>{cost}</div>')

    if s.get("step"):
        parts.append('<p class="step"><i class="ti ti-arrow-right" aria-hidden="true"></i>'
                     f'{_e(s["step"])}</p>')

    if s.get("forcing_question"):
        parts.append(f'<p class="forcing eng">Прежде чем примешь: {_e(s["forcing_question"])}</p>')

    parts.append('<div class="toggle"><button onclick="this.closest(\'.cp-stage\')'
                 '.classList.toggle(\'show-eng\')"><i class="ti ti-adjustments-alt" aria-hidden="true"></i>'
                 '<span class="lbl-show">показать инженерию</span>'
                 '<span class="lbl-hide">скрыть инженерию</span></button></div>')

    parts.append('<p class="legend eng"><span style="color:var(--color-text-info,#185FA5)">'
                 'дословно</span> — сверено с корпусом первоисточника · '
                 '<span style="color:var(--color-text-warning,#854F0B)">в духе автора</span> — '
                 'экстраполяция · отказ вместо выдумки, если совпадения нет.</p>')

    btns = "".join(
        f'<button onclick="{_onclick(p)}"><i class="ti {icon}" aria-hidden="true"></i>{_e(label)}</button>'
        for label, p, icon in norm)
    parts.append(f'<div class="acts">{btns}</div></div>')
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
    d = _disagreement(s)
    if d:
        sides = "".join(f"<li>{_e(x)}</li>" for x in d["sides"])
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


def render_proof_card(quote, source):
    """Самодостаточная html-карточка одной 🔵-verbatim-цитаты + источник + бейдж-пруф.
    Только для уже верифицированной 🔵-цитаты (проверку делает вызывающий). `quote` — текст,
    что передал вызывающий (в проде — верифицированная cite-цитата из корпуса). Бейдж говорит
    «дословно, сверено с первоисточником» — честно к тому, что делает гейт (нормализованный
    verbatim: слова автора, регистр/пунктуация не важны), НЕ «посимвольно» (это было бы
    сильнее реального механизма)."""
    src = f'<p class=src>— {_e(source)}</p>' if source else ""
    return (
        "<!doctype html><html lang=ru><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Пруф цитаты</title><style>"
        ":root{color-scheme:light dark}"
        "body{font:16px/1.6 system-ui,sans-serif;margin:0;min-height:100vh;display:flex;"
        "align-items:center;justify-content:center;background:Canvas;color:CanvasText;padding:24px}"
        ".card{max-width:600px;border:1px solid color-mix(in srgb,CanvasText 15%,transparent);"
        "border-radius:16px;padding:32px}"
        "blockquote{font-size:1.4rem;line-height:1.4;margin:0 0 16px;font-weight:500}"
        ".src{opacity:.7;font-size:.95rem;margin:0 0 20px}"
        ".badge{display:inline-block;font-size:.85rem;padding:6px 12px;border-radius:999px;"
        "background:color-mix(in srgb,#185FA5 20%,transparent)}"
        "</style>"
        f'<div class=card><blockquote>«{_e(quote)}»</blockquote>{src}'
        '<span class=badge>🔵 дословно — сверено с первоисточником</span></div></html>'
    )


# ---------- decision-record (протокол заседания — минуты) ----------

def render_decision_record(record, surface="md"):
    """decision_record.build_record(session) → читаемые минуты заседания. surface=md (единственный
    сейчас). Тиры в assumptions УЖЕ скопированы верно (build_record не поднимает/не изобретает —
    см. decision_record.py); рендер только показывает их эмодзи as-is, не пересчитывает."""
    out = ["# Протокол заседания", "", f"**Вопрос:** {_e(record.get('question') or '')}"]

    positions = record.get("positions") or []
    if positions:
        out += ["", "## Позиции"]
        for p in positions:
            out += ["", f"### {_e(p.get('advisor') or '')}"]
            stance = p.get("stance")
            if stance:
                out.append(_e(stance))
            for a in p.get("assumptions") or []:
                tier = a.get("tier")
                glyph = f"{tier} " if tier else ""
                out.append(f"- {glyph}{_e(a.get('text') or '')}")

    out += ["", "## Диссент"]
    dissent = record.get("dissent") or []
    if dissent:
        for d in dissent:
            who = f"**{_e(d['advisor'])}:** " if d.get("advisor") else ""
            out.append(f"- {who}{_e(d.get('point') or '')}")
        # resolver — КАК снимается расхождение (не советник); показываем честной пометкой,
        # зеркалим форму `## Где расходятся` выше. Пусто → строки нет.
        resolver = record.get("dissent_resolver")
        if resolver:
            out.append(f"**Снимается:** {_e(resolver)}")
    else:
        out.append("явных возражений не зафиксировано.")

    decision = record.get("decision") or {}
    out += ["", "## Решение"]
    choice = decision.get("choice")
    out.append(_e(choice) if choice else "решение не зафиксировано")
    out.append(f"**Статус:** {_e(decision.get('status') or 'defer')}")

    triggers = record.get("re_review_triggers") or []
    if triggers:
        out += ["", "## Триггеры пересмотра"]
        out += [f"- {_e(t)}" for t in triggers]

    prov = record.get("provenance") or {}
    blue = prov.get("blue", 0)
    green = prov.get("green", 0)
    yellow = prov.get("yellow", 0)
    out += ["", "---",
            f"Provenance: {blue}🔵 / {green}🟢 / {yellow}🟡 — сколько заземлено vs без опоры."]
    return "\n".join(out)


# ---------- export_session (шеримый пруф заседания) ----------

_SHARE_FOOTER = ("Собрано в Consilium-Principis — совет заземлён в public-domain текстах; "
                 "🔵 = дословная цитата, сверено с первоисточником. Перед тем как делиться — "
                 "проверь, что в тексте нет ничего личного.")


def _norm_abstentions(items):
    """Нормализует abstentions в список строк (fail-safe). Строка → [строка] (не итерируем по
    символам); не-список/не-строка → None; элементы приводятся к str (не крашим _e на dict/int)."""
    if items is None:
        return None
    if isinstance(items, str):
        items = [items]
    elif not isinstance(items, (list, tuple)):
        return None
    return [str(x) for x in items]


def _abstentions_md(items):
    if not items:
        return []
    out = ["", "## Что совет НЕ стал выдумывать",
           "Вне корпуса совет ушёл в 🟡/отказ вместо фейк-цитаты — здесь:"]
    out += [f"- {_e(x)}" for x in items]
    return out


def _abstentions_html(items):
    if not items:
        return ""
    lis = "".join(f"<li>{_e(x)}</li>" for x in items)
    return ('<section class=abstain><h3>Что совет НЕ стал выдумывать</h3>'
            '<p>Вне корпуса совет ушёл в 🟡/отказ вместо фейк-цитаты:</p>'
            f'<ul>{lis}</ul></section>')


def export_session(session, surface="md", include_abstentions=True):
    """Шеримый пруф заседания. surface: md (дефолт) | html. Добавляет к базовому рендеру
    панель абстеншенов (session['abstentions'], если есть и include_abstentions) + share-футер.
    Приватность: работает ТОЛЬКО с переданным объектом; файлов не читает/не пишет. Экспорт —
    для ЗАВЕРШЁННОГО заседания (нужны question + synthesis); неполный объект → fail-closed
    {error}, а не краш (Режим B до синтеза, битые advisors и т.п.)."""
    if not isinstance(session, dict) or not session.get("question"):
        return {"error": "нужен объект заседания с полем question"}
    if not session.get("synthesis"):
        return {"error": "заседание без синтеза — экспортируй завершённое заседание (сначала синтез)"}
    items = _norm_abstentions(session.get("abstentions") if include_abstentions else None)
    try:
        if surface == "html":
            base = render_html(session)
            extra = _abstentions_html(items)
            extra += f'<p class=share>{_e(_SHARE_FOOTER)}</p>'
            content = base[: -len("</html>")] + extra + "</html>"
        else:
            surface = "md"
            lines = [render_md(session)]
            lines += _abstentions_md(items)
            lines += ["", "---", _SHARE_FOOTER]
            content = "\n".join(lines)
    except (KeyError, TypeError, AttributeError) as e:
        return {"error": f"заседание неполное для экспорта ({e})"}
    return {"content": content, "surface": surface}
