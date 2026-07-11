# Moat-Fit 3 Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить 3 moat-fit MCP-тула (`export_session`, `proof_card`, `quote_of_day`) поверх существующего детерминированного гейта 🔵 + рецепты-триггеры, не ослабляя контур и соблюдая инвариант приватности.

**Architecture:** Session-share переиспользует `session_render.render_md/render_html` (уже отдают самодостаточный экранированный shareable-артефакт), добавляя панель абстеншенов + share-футер. proof_card и quote_of_day строятся на `_fidelity_check` / `engine.fidelity._iter_chunks` (fail-closed: не 🔵 → нет карточки/цитаты). Тулы возвращают строки/данные, файлов не пишут, приватные журналы не читают.

**Tech Stack:** Python 3 (stdlib), pytest. Офлайн-CI: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`. Ветка `feat/moat-legible`, без push/merge.

---

## File Structure

- `scripts/session_render.py` — ДОБАВИТЬ: `_abstentions_md/_abstentions_html`, `_share_footer_md/_share_footer_html`, `export_session(session, surface, include_abstentions)`, `render_proof_card(quote, source)`.
- `scripts/mcp_server.py` — ДОБАВИТЬ: handlers `_export_session`, `_proof_card`, `_quote_of_day` + 3 записи в `TOOLS`.
- `recipes.json` — ДОБАВИТЬ 3 рецепта + debate/panel-синонимы в существующие.
- `tests/test_export_session.py`, `tests/test_proof_card.py`, `tests/test_quote_of_day.py` — новые.
- `tests/test_recipes.py` — расширить.
- `docs/selfdoc/index.json` + `docs/MANUAL.md` — регенерировать (сдвиг test_count от новых тест-файлов).

---

### Task 1: `export_session` — шеримый пруф заседания

**Files:**
- Modify: `scripts/session_render.py` (после `render_md`/`render_html`, ~строка 157/507)
- Modify: `scripts/mcp_server.py` (handler + запись в TOOLS)
- Test: `tests/test_export_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_session.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_export_session.py -q`
Expected: FAIL with `ImportError: cannot import name 'export_session'`

- [ ] **Step 3: Implement in `scripts/session_render.py`** (добавить после `render_html`, использует уже определённые `_e`, `render_md`, `render_html`)

```python
_SHARE_FOOTER = ("Собрано в Consilium-Principis — совет заземлён в public-domain текстах; "
                 "🔵 = сверено посимвольно с источником. Перед тем как делиться — проверь, "
                 "что в тексте нет ничего личного.")


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
    Приватность: работает ТОЛЬКО с переданным объектом; файлов не читает/не пишет. Нет
    question → fail-closed {error}."""
    if not isinstance(session, dict) or not session.get("question"):
        return {"error": "нужен объект заседания с полем question"}
    items = session.get("abstentions") if include_abstentions else None
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
    return {"content": content, "surface": surface}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_export_session.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Register tool in `scripts/mcp_server.py`** (handler рядом с `_list_recipes`, запись в TOOLS рядом с `render_session`)

```python
def _export_session(session, surface="md", include_abstentions=True):
    from session_render import export_session
    return export_session(session, surface=surface, include_abstentions=include_abstentions)
```

Запись в словарь `TOOLS`:

```python
    "export_session": {
        "description": "Шеримый пруф заседания (по ЯВНОМУ запросу юзера — правило 0). Отдаёт "
                       "самодостаточный md (дефолт) | html артефакт: вопрос → советники → "
                       "🔵-цитаты с источником → синтез + панель «что совет НЕ стал выдумывать» "
                       "(session.abstentions) + атрибуция. Приватность: только текущее заседание "
                       "(переданный объект), файлов не пишет — верни `content` юзеру, сохраняет он.",
        "input_schema": {"type": "object",
                         "properties": {"session": {"type": "object"},
                                        "surface": {"type": "string", "enum": ["md", "html"]},
                                        "include_abstentions": {"type": "boolean"}},
                         "required": ["session"]},
        "handler": _export_session,
    },
```

- [ ] **Step 6: Run full offline suite**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: all pass EXCEPT possibly `test_selfdoc_fresh` (new test file shifted test_count) — fix in Step 7. Ignore env-flaky `test_ssrf_check_passes_public_blocks_private`.

- [ ] **Step 7: Regen selfdoc if test_selfdoc_fresh failed**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`
Then re-run the suite to confirm green.

- [ ] **Step 8: Commit**

```bash
git add scripts/session_render.py scripts/mcp_server.py tests/test_export_session.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "feat(share): export_session — шеримый пруф заседания (+панель абстеншенов, приватность fail-closed)"
```

---

### Task 2: `proof_card` — карточка одной 🔵-цитаты

**Files:**
- Modify: `scripts/session_render.py` (`render_proof_card`)
- Modify: `scripts/mcp_server.py` (handler `_proof_card` + запись в TOOLS)
- Test: `tests/test_proof_card.py`

- [ ] **Step 1: Write the failing test** (fixture-корпус с явным tier — паттерн tests/test_fidelity_tiers.py; без него tier дефолтит в "A" и 🔵 не даётся)

```python
# tests/test_proof_card.py
"""proof_card — карточка ОДНОЙ 🔵-verbatim-цитаты (виирал-ассет). Fail-closed: не 🔵 → нет карточки."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def _make_advisor(tmp_path, chunks):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(adv)


def test_verbatim_blue_quote_makes_card(tmp_path):
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"}])
    r = _proof_card("Confine thyself to the present.", adv)
    assert r["verified"] is True
    assert "Meditations 7.29" in r["content"]
    assert "посимвольно" in r["content"]
    assert r["content"].startswith("<!doctype html>")
    assert "<script" not in r["content"].lower()


def test_non_verbatim_quote_no_card(tmp_path):
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"}])
    r = _proof_card("This is a fabricated quote never in corpus.", adv)
    assert r["verified"] is False
    assert r.get("content") is None


def test_green_tier_quote_rejected(tmp_path):
    # 🟢 (комментарий S-тир) не пускаем на 🔵-пруф-карту (карточка заявляет первоисточник)
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "A commentator paraphrase of the sage.", "tier": "S1", "source": "Commentary p.5"}])
    r = _proof_card("A commentator paraphrase of the sage.", adv)
    assert r["verified"] is False
    assert r.get("content") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_proof_card.py -q`
Expected: FAIL with `ImportError: cannot import name '_proof_card'`

- [ ] **Step 3: Implement `render_proof_card` in `scripts/session_render.py`**

```python
def render_proof_card(quote, source):
    """Самодостаточная html-карточка одной 🔵-verbatim-цитаты + источник + бейдж-пруф.
    Только для уже верифицированной 🔵-цитаты (проверку делает вызывающий)."""
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
        '<span class=badge>🔵 сверено посимвольно с источником</span></div></html>'
    )
```

- [ ] **Step 4: Implement handler in `scripts/mcp_server.py`**

```python
def _proof_card(quote, advisor_dir):
    from session_render import render_proof_card
    fc = _fidelity_check(quote, advisor_dir)
    if not fc["verbatim"] or fc["status"] != "🔵":
        return {"verified": False, "content": None,
                "note": "не сверено посимвольно как первоисточник — 🔵-карточку не рисую"}
    return {"verified": True, "content": render_proof_card(quote, fc["source"])}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_proof_card.py -q`
Expected: PASS (3 passed)

- [ ] **Step 6: Register tool in `TOOLS`** (`scripts/mcp_server.py`)

```python
    "proof_card": {
        "description": "Виирал-ассет «show your work»: самодостаточная html-карточка ОДНОЙ цитаты "
                       "с источником + бейдж «🔵 сверено посимвольно». Fail-closed: если цитата НЕ "
                       "дословна в P1/P2-корпусе советника → {verified:false, content:null} (карточки "
                       "нет — суть рва). advisor_dir = advisors/{имя} или lenses/{имя}.",
        "input_schema": _obj({"quote": "string", "advisor_dir": "string"}, ["quote", "advisor_dir"]),
        "handler": _proof_card,
    },
```

- [ ] **Step 7: Run full offline suite + regen selfdoc if needed**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
If `test_selfdoc_fresh` fails: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`, re-run.

- [ ] **Step 8: Commit**

```bash
git add scripts/session_render.py scripts/mcp_server.py tests/test_proof_card.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "feat(share): proof_card — карточка одной 🔵-цитаты (fail-closed, show-your-work)"
```

---

### Task 3: `quote_of_day` — verbatim-цитата дня (pull-only)

**Files:**
- Modify: `scripts/mcp_server.py` (handler `_quote_of_day` + запись в TOOLS)
- Test: `tests/test_quote_of_day.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quote_of_day.py
"""quote_of_day — детерминированная verbatim-цитата дня из P1/P2-корпуса. Pull-only, гарантия 🔵."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def _make_advisor(tmp_path, chunks):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(adv)


P1_CHUNKS = [
    {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"},
    {"text": "Waste no more time arguing about what a good man should be.", "tier": "P1",
     "source": "Meditations 10.16"},
    {"text": "The happiness of your life depends upon the quality of your thoughts.", "tier": "P2",
     "source": "Meditations 5.16"},
]


def test_returns_blue_quote_from_corpus(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    r = _quote_of_day(adv, date="2026-07-11")
    assert r["marker"] == "🔵"
    assert r["source"]
    corpus_texts = [c["text"] for c in P1_CHUNKS]
    assert r["text"] in corpus_texts          # реально из корпуса, не выдумана


def test_deterministic_same_date(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    a = _quote_of_day(adv, date="2026-07-11")
    b = _quote_of_day(adv, date="2026-07-11")
    assert a["text"] == b["text"]


def test_varies_across_dates(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, P1_CHUNKS)
    picks = {_quote_of_day(adv, date=f"2026-07-{d:02d}")["text"] for d in range(1, 20)}
    assert len(picks) >= 2                     # не всегда один и тот же чанк


def test_empty_or_non_p1_pool_no_blue(tmp_path):
    from mcp_server import _quote_of_day
    adv = _make_advisor(tmp_path, [
        {"text": "Some low-tier apparatus text.", "tier": "A", "source": "x"}])
    r = _quote_of_day(adv, date="2026-07-11")
    assert r.get("marker") != "🔵"
    assert "note" in r
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_quote_of_day.py -q`
Expected: FAIL with `ImportError: cannot import name '_quote_of_day'`

- [ ] **Step 3: Implement handler in `scripts/mcp_server.py`** (использует `engine.fidelity._iter_chunks`, `_fidelity_check`, `_advisor_dirs`, `_resolve`; `import hashlib`, `import datetime` — вверху файла, проверь наличие)

```python
def _quote_of_day(advisor_dir=None, date=None):
    """Детерминированная 🔵-verbatim-цитата дня из P1/P2-корпуса собранного советника. Pull-only.
    advisor_dir не задан → первый собранный. date (ISO) — инъекция для детерминизма; иначе сегодня."""
    from engine.fidelity import _iter_chunks
    from corpusbuild.paths import corpus_path
    import hashlib, datetime
    if advisor_dir:
        adv = _resolve(advisor_dir)
        adv_list = [adv] if os.path.isfile(corpus_path(adv)) else []
    else:
        adv_list = [d for d in _advisor_dirs() if os.path.isfile(corpus_path(d))]
    if not adv_list:
        return {"note": "нет собранных советников с корпусом"}
    adv = adv_list[0]
    pool = [(ch.get("text", ""), ch.get("source") or ch.get("citation") or "")
            for ch in _iter_chunks(adv) if ch.get("tier") in ("P1", "P2") and ch.get("text")]
    if not pool:
        return {"note": "нет P1/P2-цитат в корпусе (нечего цитировать дословно)"}
    ds = date or datetime.date.today().isoformat()
    start = int(hashlib.sha256(ds.encode("utf-8")).hexdigest()[:8], 16) % len(pool)
    # детерминированный обход от выбранного индекса; берём первый, что реально проходит 🔵-гейт
    for k in range(len(pool)):
        text, src = pool[(start + k) % len(pool)]
        fc = _fidelity_check(text, adv)
        if fc["status"] == "🔵":
            return {"text": text, "source": fc["source"] or src,
                    "advisor": os.path.basename(adv), "marker": "🔵"}
    return {"note": "P1/P2-цитаты не прошли verbatim-гейт"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_quote_of_day.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Register tool in `TOOLS`** (`scripts/mcp_server.py`)

```python
    "quote_of_day": {
        "description": "Ретеншн-крючок (PULL-ONLY, по запросу): одна 🔵-verbatim-цитата дня из "
                       "P1/P2-корпуса собранного советника + источник. Детерминирована по дате "
                       "(в течение дня стабильна). advisor_dir опционален (нет → первый собранный). "
                       "Нет P1/P2-цитат → {note} (не выдумывает generic-мудрость).",
        "input_schema": {"type": "object",
                         "properties": {"advisor_dir": {"type": "string"},
                                        "date": {"type": "string"}},
                         "required": []},
        "handler": _quote_of_day,
    },
```

- [ ] **Step 6: Run full offline suite + regen selfdoc if needed**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
If `test_selfdoc_fresh` fails: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`, re-run.

- [ ] **Step 7: Commit**

```bash
git add scripts/mcp_server.py tests/test_quote_of_day.py docs/selfdoc/index.json docs/MANUAL.md
git commit -m "feat(ritual): quote_of_day — verbatim-цитата дня (pull-only, детерминизм по дате)"
```

---

### Task 4: Рецепты + именованные режимы-синонимы

**Files:**
- Modify: `recipes.json`
- Test: `tests/test_recipes.py` (расширить)

- [ ] **Step 1: Write the failing test** (добавить в конец `tests/test_recipes.py`)

```python
def test_moat_fit_share_recipes_present():
    # share-session / quote-of-day / proof-card — новые moat-fit рецепты (3 тула), 2026-07-11
    rs = load_recipes()
    ids = [r["id"] for r in rs]
    for rid in ("share-session", "quote-of-day", "proof-card"):
        assert rid in ids, f"{rid} рецепт пропал"
        r = next(r for r in rs if r["id"] == rid)
        assert set(r.keys()) == {"id", "title", "short", "triggers", "does", "reads"}
        assert r["triggers"] and isinstance(r["triggers"], list)


def test_match_finds_share_session():
    r = match_recipe("поделись заседанием совета", load_recipes())
    assert r is not None and r["id"] == "share-session"


def test_match_finds_quote_of_day():
    r = match_recipe("дай цитату дня", load_recipes())
    assert r is not None and r["id"] == "quote-of-day"


def test_debate_synonym_routes_to_clash():
    r = match_recipe("устрой дебаты двух советников", load_recipes())
    assert r is not None and r["id"] == "clash-two"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_recipes.py -q`
Expected: FAIL (рецептов нет / debate-триггер не найден)

- [ ] **Step 3: Add 3 recipes to `recipes.json`** (в конец массива) + debate/panel-синонимы

Добавить в массив три объекта:

```json
  {
    "id": "share-session",
    "title": "Поделиться заседанием — шеримый пруф",
    "short": "Поделиться пруфом",
    "triggers": ["поделись заседанием", "экспортируй совет", "сохрани как пруф", "шеримый вариант", "выгрузи заседание"],
    "does": "Соберу самодостаточный артефакт заседания (текст или страница): цитаты с источником + что совет НЕ стал выдумывать. Отдам тебе — сохраняешь и делишься сам.",
    "reads": "Приватность: только это заседание, файлов сам не пишу. Перед шером проверь, что нет личного."
  },
  {
    "id": "quote-of-day",
    "title": "Цитата дня — дословно, с источником",
    "short": "Цитата дня",
    "triggers": ["цитата дня", "мысль дня", "вдохнови", "дай цитату", "цитату на сегодня"],
    "does": "Дам одну 🔵-дословную цитату дня из текстов собранного советника — честную, с источником, не generic-мудрость.",
    "reads": "Стабильна в течение дня. Нет дословных цитат в корпусе — честно скажу, а не выдумаю."
  },
  {
    "id": "proof-card",
    "title": "Карточка цитаты — докажи дословность",
    "short": "Карточка цитаты",
    "triggers": ["покажи пруф цитаты", "карточка цитаты", "докажи цитату", "сверь цитату", "это точно цитата"],
    "does": "Сделаю карточку одной цитаты с источником и бейджем «сверено посимвольно» — «show your work».",
    "reads": "Fail-closed: если цитата не найдена дословно в первоисточнике — карточки не будет (не блефую)."
  }
```

Расширить триггеры существующих рецептов (найти по `id` и добавить в массив `triggers`):
- `clash-two`: добавить `"дебаты"`, `"устрой дебаты"`, `"debate"`.
- `full-council`: добавить `"панель экспертов"`, `"expert panel"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_recipes.py -q`
Expected: PASS

- [ ] **Step 5: Run full offline suite**

Run: `cd /Users/ilyautov/personal/Projects/personal-board-skill-2026-06-10 && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: all pass. `recipes.json` не тест-файл → selfdoc test_count не сдвигается (но если сдвинулся — regen как выше).

- [ ] **Step 6: Commit**

```bash
git add recipes.json tests/test_recipes.py
git commit -m "feat(recipes): share-session/quote-of-day/proof-card + debate/panel-синонимы"
```

---

## Self-Review (проверка плана против спеки)

- **Покрытие спеки:** export_session (Task 1), proof_card (Task 2), quote_of_day (Task 3), рецепты + именованные режимы-синонимы (Task 4) — все 4 буллета спеки закрыты.
- **Инвариант приватности:** export_session валидирует объект и не читает файлов (Task 1 test); quote_of_day/proof_card только PD-корпус. Ни один не пишет файлов.
- **Fail-closed:** proof_card не-🔵 → нет карточки (Task 2 test); quote_of_day не-P1/P2 → note без 🔵 (Task 3 test); export невалидный session → error (Task 1 test).
- **Типы/имена согласованы:** `export_session`/`render_proof_card` в session_render; `_export_session`/`_proof_card`/`_quote_of_day` handlers; `_obj`, `_fidelity_check`, `_resolve`, `_advisor_dirs`, `_iter_chunks` — существующие, проверены в коде.
- **selfdoc-regen** в каждой задаче с новым тест-файлом (Tasks 1–3).
- **Плейсхолдеров нет** — весь код приведён.
