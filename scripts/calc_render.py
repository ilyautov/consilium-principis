#!/usr/bin/env python3
"""Результат «Principis-расчёта» (mc_run) → тонкие рендер-адаптеры под surface (Ф3).

Та же архитектура, что session_render: ОДИН data-объект (выход mc_run/run_calculation) —
чистая презентация поверх уже посчитанного и провалидированного результата. Функции чистые
и детерминированные (фиксированный вход → байт-в-байт тот же выход): ноль LLM, ноль сети,
никакого счёта здесь — только подача.

Адаптеры:
  • render_calc_md(res, label_text, option_names)     — markdown: спарклайн-гистограмма
    исходов на вариант (unicode-бары), торнадо горизонтальными барами, сводка-таблица
    P(лучший)/сожаление. Портативно (голый Claude Code / present_files).
  • render_calc_widget(res, label_text, option_names) — HTML для mcp__visualize__show_widget
    (Cowork): та же механика, что session_render.render_widget — семантические --color-*
    (тёмная тема даром), var(--font-sans), Tabler-иконки, БЕЗ эмодзи в вёрстке, без <script>.

Рамка честности: label_text («📐 рамка» из run_calculation) — обязательная часть подачи,
рендерится в обоих surface (в виджете — текстом, глиф 📐 заменён Tabler-иконкой по
дизайн-системе). Гистограмма опциональна (mc_run отдаёт её только при histogram=True):
нет блока → секция тихо опускается, торнадо и сводка живут сами.
"""
import html as _html

_e = _html.escape

_SPARK = "▁▂▃▄▅▆▇█"          # уровни спарклайна (md)
_TORNADO_BAR_W = 20           # ширина торнадо-бара в md, символов на impact=1.0


def _fmt(v):
    """Число статистики компактно и детерминированно (как predicted в mcp_server)."""
    return "%.4g" % v


def _prob(v):
    return "%.2f" % v


def _ordered_options(res, option_names):
    """[(oid, display_name)] по убыванию P(лучший), тай-брейк — id (детерминизм подачи)."""
    names = option_names if isinstance(option_names, dict) else {}
    oids = sorted(res["p_best"], key=lambda o: (-res["p_best"][o], o))
    return [(oid, str(names.get(oid) or oid)) for oid in oids]


def _histogram_of(res):
    h = res.get("histogram")
    return h if isinstance(h, dict) and isinstance(h.get("counts"), dict) else None


def _spark(counts):
    mx = max(counts) or 1
    return "".join(_SPARK[round(c / mx * (len(_SPARK) - 1))] for c in counts)


# ---------- markdown (портативный) ----------

def render_calc_md(res, label_text=None, option_names=None):
    out = ["## 📐 Расчёт"]
    if label_text:
        out += ["", _e(str(label_text))]
    opts = _ordered_options(res, option_names)
    hist = _histogram_of(res)

    out += ["", "### Исходы по вариантам"]
    for oid, name in opts:
        st = res["options"][oid]
        out += ["", "**%s** — P(лучший) %s" % (_e(name), _prob(res["p_best"][oid]))]
        if hist and oid in hist["counts"]:
            out.append("`%s`  (диапазон %s … %s)"
                       % (_spark(hist["counts"][oid]), _fmt(hist["lo"]), _fmt(hist["hi"])))
        out.append("p10 %s · медиана %s · p90 %s"
                   % (_fmt(st["p10"]), _fmt(st["median"]), _fmt(st["p90"])))

    out += ["", "### Что решает исход (торнадо)"]
    for t in res["tornado"]:
        bar = "█" * max(1, round(t["impact"] * _TORNADO_BAR_W)) if t["impact"] > 0 else "·"
        out.append("- `%s` %s %s" % (_e(str(t["id"])), bar, _prob(t["impact"])))

    out += ["", "### Сводка",
            "| Вариант | P(лучший) | Ожидаемое сожаление |", "|---|---|---|"]
    for oid, name in opts:
        out.append("| %s | %s | %s |"
                   % (_e(name), _prob(res["p_best"][oid]), _fmt(res["expected_regret"][oid])))
    return "\n".join(out)


# ---------- show_widget (нативный Cowork) ----------
# Механика — как session_render._STAGE_STYLE: scoped-<style> + семантические переменные
# Cowork с self-contained фолбэками; вёрстка без эмодзи (Tabler-иконки), без <script>.

_CALC_STYLE = (
 '<style>'
 '.cp-calc{font-family:var(--font-sans,system-ui,sans-serif);'
 'color:var(--color-text-primary,CanvasText);max-width:600px;margin:0 auto;'
 'padding:8px 6px 4px;line-height:1.5}'
 '.cp-calc .eyebrow{font-size:11px;letter-spacing:.24em;text-transform:uppercase;'
 'color:var(--color-text-tertiary,#999);text-align:center;margin:2px 0 10px}'
 '.cp-calc .eyebrow i{font-style:normal;margin-right:8px;font-size:15px;vertical-align:-3px}'
 '.cp-calc .frame{font-size:12.5px;color:var(--color-text-secondary,#888);text-align:center;'
 'margin:0 14px 6px;line-height:1.55}'
 '.cp-calc .sect{font-size:11px;letter-spacing:.18em;text-transform:uppercase;'
 'color:var(--color-text-tertiary,#999);text-align:center;margin:20px 0 8px}'
 '.cp-calc .opt{margin:12px 0}'
 '.cp-calc .onm{font-size:13.5px;font-weight:500;margin:0 0 5px;display:flex;'
 'justify-content:space-between;gap:8px;align-items:baseline}'
 '.cp-calc .onm .pb{font-weight:400;font-size:12px;color:var(--color-text-info,#185FA5)}'
 '.cp-calc .hist{display:flex;align-items:flex-end;gap:2px;height:44px}'
 '.cp-calc .hbin{flex:1;background:color-mix(in srgb,var(--color-text-info,#185FA5) 55%,transparent);'
 'border-radius:2px 2px 0 0;min-height:1px}'
 '.cp-calc .stats{font-size:11.5px;color:var(--color-text-tertiary,#999);margin-top:4px}'
 '.cp-calc .trow{display:flex;align-items:center;gap:8px;font-size:12.5px;margin:5px 0}'
 '.cp-calc .tid{flex:none;width:36%;overflow:hidden;text-overflow:ellipsis;'
 'white-space:nowrap;text-align:right}'
 '.cp-calc .ttrack{flex:1;display:flex;align-items:center;gap:6px}'
 '.cp-calc .tbar{height:8px;border-radius:4px;'
 'background:var(--color-text-warning,#854F0B);opacity:.75}'
 '.cp-calc .tval{font-size:11px;color:var(--color-text-tertiary,#999)}'
 '.cp-calc table{width:100%;border-collapse:collapse;font-size:12.5px}'
 '.cp-calc td,.cp-calc th{padding:4px 6px;text-align:left;border-bottom:.5px solid '
 'var(--color-border-secondary,rgba(127,127,127,.25))}'
 '.cp-calc th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;'
 'color:var(--color-text-tertiary,#999);font-weight:500}'
 '</style>')


def render_calc_widget(res, label_text=None, option_names=None):
    opts = _ordered_options(res, option_names)
    hist = _histogram_of(res)
    parts = [_CALC_STYLE, '<div class="cp-calc">',
             '<div class="eyebrow"><i class="ti ti-math-function" aria-hidden="true"></i>'
             'Расчёт</div>']
    if label_text:
        # глиф 📐 в вёрстке заменяет Tabler-иконка (дизайн-система: без эмодзи в виджете)
        parts.append('<p class="frame">%s</p>' % _e(str(label_text).replace("📐", "").strip()))

    parts.append('<div class="sect">Исходы по вариантам</div>')
    for oid, name in opts:
        st = res["options"][oid]
        parts.append('<div class="opt"><div class="onm"><span>%s</span>'
                     '<span class="pb">P(лучший) %s</span></div>'
                     % (_e(name), _prob(res["p_best"][oid])))
        if hist and oid in hist["counts"]:
            counts = hist["counts"][oid]
            mx = max(counts) or 1
            bins = "".join('<div class="hbin" style="height:%d%%"></div>'
                           % max(2, round(c / mx * 100)) if c else
                           '<div class="hbin" style="height:2%"></div>'
                           for c in counts)
            parts.append('<div class="hist">%s</div>' % bins)
        parts.append('<div class="stats">p10 %s · медиана %s · p90 %s</div></div>'
                     % (_fmt(st["p10"]), _fmt(st["median"]), _fmt(st["p90"])))

    parts.append('<div class="sect">Что решает исход</div>')
    for t in res["tornado"]:
        w = max(2, round(max(0.0, min(1.0, t["impact"])) * 100))
        parts.append('<div class="trow"><span class="tid">%s</span>'
                     '<span class="ttrack"><span class="tbar" style="width:%d%%"></span>'
                     '<span class="tval">%s</span></span></div>'
                     % (_e(str(t["id"])), w, _prob(t["impact"])))

    parts.append('<div class="sect">Сводка</div>'
                 '<table><tr><th>Вариант</th><th>P(лучший)</th><th>Сожаление</th></tr>')
    for oid, name in opts:
        parts.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (_e(name), _prob(res["p_best"][oid]),
                        _fmt(res["expected_regret"][oid])))
    parts.append('</table></div>')
    return "".join(parts)
