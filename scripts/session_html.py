#!/usr/bin/env python3
"""Заседание совета → самодостаточный HTML (визуализация-surface, как recipes.render_html).

Стена markdown-текста плохо передаёт структуру заседания; в HTML контур играет ЦВЕТОМ
(🔵 синий кант = дословная цитата, 🟡 янтарный = экстраполяция), цитата-оригинал + глосса
видны как блок. Дисплей, не движок: HTML лишь ПОКАЗЫВАЕТ уже готовую сессию; грунтование и
гейт 🔵 происходят раньше (best_match), сюда приходит проверенный результат.

session = {
  "question": str,
  "frame": str | None,                       # переформулировка вопроса (опц.)
  "voices": [ {                              # независимые мнения советников
     "name": str,
     "marker": "blue" | "amber" | None,      # 🔵 / 🟡 / без (линза без корпуса)
     "point": str,                           # довод голосом советника, на языке юзера
     "quote": str | None,                    # дословная строка в ОРИГИНАЛЕ (для 🔵)
     "gloss": str | None,                    # перевод цитаты как глосса (≠ 🔵)
     "source": str | None,                   # источник цитаты
  } ],
  "fault_line": str | None,                  # где советники расходятся
  "synthesis": str,                          # синтез
  "step": str | None,                        # один шаг к действию
}
plain по умолчанию: числа не передаём — сюда кладём словесный вывод (см. правило «Подача»).
"""
import html as _html

_MARK = {"blue": ("🔵", "#2f6fed"), "amber": ("🟡", "#d98a00")}


def _voice_html(v, e):
    glyph, color = _MARK.get(v.get("marker"), ("", "#9aa0a6"))
    head = f'<span class="m">{glyph}</span> ' if glyph else ""
    parts = [f'<article class="voice" style="border-left-color:{color}">',
             f"<h2>{head}{e(v['name'])}</h2>",
             f"<p class=point>{e(v['point'])}</p>"]
    if v.get("quote"):
        block = f'<span class="orig">«{e(v["quote"])}»</span>'
        if v.get("source"):
            block += f' <span class="src">({e(v["source"])})</span>'
        if v.get("gloss"):
            block += f'<span class="gloss">{e(v["gloss"])}</span>'
        parts.append(f"<blockquote>{block}</blockquote>")
    parts.append("</article>")
    return "".join(parts)


def render_session_html(session, title="Заседание совета"):
    e = _html.escape
    body = [f"<h1>{e(title)}</h1>",
            f'<p class=q><span>Вопрос:</span> {e(session["question"])}</p>']
    if session.get("frame"):
        body.append(f'<p class=frame>{e(session["frame"])}</p>')
    body.append('<div class="voices">')
    body += [_voice_html(v, e) for v in session.get("voices", [])]
    body.append("</div>")
    if session.get("fault_line"):
        body.append(f'<section class=fault><h3>Где расходятся</h3><p>{e(session["fault_line"])}</p></section>')
    body.append(f'<section class=synth><h3>Синтез</h3><p>{e(session["synthesis"])}</p></section>')
    if session.get("step"):
        body.append(f'<section class=step><h3>Шаг</h3><p>{e(session["step"])}</p></section>')
    body.append('<p class=legend>🔵 дословная цитата (с источником) · 🟡 мысль в духе автора · '
                'цитата — в оригинале, перевод рядом как глосса.</p>')
    return (
        "<!doctype html><html lang=ru><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)}</title><style>"
        ":root{color-scheme:light dark}"
        "body{font:16px/1.55 system-ui,sans-serif;margin:0 auto;max-width:760px;"
        "padding:24px;background:Canvas;color:CanvasText}"
        "h1{font-size:1.4rem;margin:0 0 12px}"
        "h2{font-size:1.05rem;margin:0 0 6px}h3{font-size:.95rem;margin:0 0 4px;opacity:.8}"
        ".q{font-size:1.05rem;margin:0 0 6px}.q span{opacity:.6}"
        ".frame{opacity:.8;font-style:italic;margin:0 0 18px}"
        ".voices{display:flex;flex-direction:column;gap:14px;margin:18px 0}"
        ".voice{border-left:4px solid;padding:4px 14px}"
        ".voice .m{font-size:.9em}.point{margin:0 0 8px}"
        "blockquote{margin:0;padding:8px 12px;border-radius:8px;"
        "background:color-mix(in srgb,CanvasText 6%,transparent);font-size:.95rem}"
        ".orig{font-style:italic}.src{opacity:.6;font-size:.85em}"
        ".gloss{display:block;opacity:.75;margin-top:4px}"
        "section{margin:16px 0}.synth{border-top:1px solid "
        "color-mix(in srgb,CanvasText 15%,transparent);padding-top:14px}"
        ".step p{font-weight:600}"
        ".legend{margin-top:22px;font-size:.82rem;opacity:.7}"
        "</style>" + "".join(body) + "</html>"
    )
