# Apparatus-aware ingest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При добавлении мыслителя из PD-книги сервер распознаёт редакторский аппарат (вступление,
инлайн-комментарий толкователей, приложения) и не запекает его как слова автора — дефолт размечает
тирами (автор 🔵 / комментарий 🟢), без блокирующего выбора, ноль ollama.

**Architecture:** Новый чистый модуль `scripts/corpusbuild/apparatus.py` (детекция + чистка + сплит +
тиринг записей). `pipeline.build` для источников с `apparatus.mode=="tier"` зовёт `apparatus.tier_records`
вместо `tag_regions`. `add_source` сам сканирует, авто-применяет `tier`, отдаёт дружелюбную сводку с
опциональными правками. Режим — переключаемое свойство источника в манифесте (пересборка из сырого
файла, недеструктивно). Спека: `docs/superpowers/specs/2026-06-30-apparatus-aware-ingest-design.md`.

**Tech Stack:** Python 3.10+, stdlib only (`re`). Без ollama, без сети в модуле. pytest.

**Инвариант рва (держать во ВСЕХ задачах):** 🔵 (P1) присваивается ТОЛЬКО уверенно-авторскому тексту
вне `[…]`. Любая неопределённость (неуверенные секции, скобки, несбаланс) → 🟢 (S1) или drop, НИКОГДА P1.

---

## Карта файлов

- **Create** `scripts/corpusbuild/apparatus.py` — детекторы, `scan`, `strip_sections`, `clean`,
  `split_inline`, `tier_records`. Единственная новая «мозговая» единица; чистая, без I/O.
- **Modify** `scripts/corpusbuild/clean.py` — тонкая обёртка `apparatus_tier(recs, source, advisor_dir)`
  (читает манифест, зовёт `apparatus.tier_records`).
- **Modify** `scripts/corpusbuild/pipeline.py` — ветка: `mode=="tier"` → `apparatus_tier`, иначе `tag_regions`.
- **Modify** `scripts/manifest_builder.py` — валидация поля `apparatus`.
- **Modify** `scripts/mcp_server.py` — `_add_source`: `mode` (auto/tier/clean/raw), `front_until`/`back_from`,
  `hint`/`adjustments`/`needs_host_review`; INSTRUCTIONS rule 10.
- **Create** `tests/fixtures/giles_like.txt` — мини-«издание» для детерминированных тестов.
- **Create** `tests/test_apparatus.py`, **Modify** `tests/test_lifecycle_tools.py`.

---

### Task 1: `apparatus.py` — чистый модуль детекции/чистки/сплита

**Files:**
- Create: `scripts/corpusbuild/apparatus.py`
- Create: `tests/test_apparatus.py`

- [ ] **Step 1: Write failing test for `split_inline`**

```python
# tests/test_apparatus.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import apparatus as ap


def test_split_inline_author_vs_commentary():
    segs = ap.split_inline("All warfare is based on deception. [Chang Yu says: deceive all.] Hence:")
    roles = [r for _, r in segs]
    assert roles == ["author", "commentary", "author"]
    assert segs[0][0].startswith("All warfare")
    assert "Chang Yu" in segs[1][0]


def test_split_inline_unbalanced_is_commentary():
    # незакрытая скобка → остаток commentary (fail-closed вниз, НЕ author)
    segs = ap.split_inline("Sun Tzu said [unterminated note about strategy")
    assert ("author" in [r for _, r in segs])               # «Sun Tzu said» — автор
    assert segs[-1][1] == "commentary"                       # хвост — вниз


def test_split_inline_nested_is_commentary():
    segs = ap.split_inline("Body [outer [inner] still note] tail")
    # один commentary-сегмент целиком, затем author «tail»
    assert [r for _, r in segs] == ["author", "commentary", "author"]
    assert "inner" in [t for t, r in segs if r == "commentary"][0]
```

- [ ] **Step 2: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpusbuild.apparatus'`

- [ ] **Step 3: Implement `apparatus.py` core (split_inline + lexicon/regex)**

```python
# scripts/corpusbuild/apparatus.py
"""Распознавание редакторского аппарата PD-изданий (вступление / инлайн-комментарий / приложения).
Чистый и ДЕТЕРМИНИРОВАННЫЙ: без ollama, без сети, без I/O. Контур: 🔵 только уверенно-авторскому
тексту вне [...]. Любая неопределённость → 🟢/drop, НИКОГДА 🔵."""
import re

# Лексикон классических толкователей (издания Giles/Legge Сунь-Цзы и пр.) + общие маркеры.
_COMMENTATORS = ("Ts'ao Kung", "Ts’ao Kung", "Tu Mu", "Chang Yu", "Chang Yü", "Wang Hsi",
                 "Li Ch'uan", "Li Ch’uan", "Mei Yao", "Chia Lin", "Tu Yu", "Ho Shih",
                 "the commentator", "commentators", "scholiast")
_FRONT_RE = re.compile(r"^\s*(CHAPTER\s+I\b|I\.\s|BOOK\s+I\b|PART\s+I\b)", re.I)
_BACK_RE = re.compile(r"^\s*(APPENDIX|BIBLIOGRAPHY|INDEX\b|FOOTNOTES|THE\s+END)\b", re.I)


def split_inline(text):
    """[(segment, role)], role ∈ {author, commentary}. author — вне [...]; всё в скобках (вкл.
    вложенные) — commentary; незакрытая скобка → остаток commentary (fail-closed вниз)."""
    out, buf, depth = [], [], 0

    def push(role):
        s = "".join(buf).strip()
        if s:
            out.append((s, role))
        buf.clear()

    for ch in text:
        if ch == "[":
            if depth == 0:
                push("author")
            depth += 1
            buf.append(ch)
        elif ch == "]":
            buf.append(ch)
            if depth > 0:
                depth -= 1
                if depth == 0:
                    push("commentary")
        else:
            buf.append(ch)
    if buf:
        push("commentary" if depth > 0 else "author")   # незакрытая скобка → вниз
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Write failing tests for `strip_sections` + `clean`**

```python
# append to tests/test_apparatus.py
def test_strip_sections_cuts_front_and_back():
    text = "Intro by translator\nblah\nI. LAYING PLANS\nSun Tzu said\nAPPENDIX\nrefs"
    body = ap.strip_sections(text, front_until="I. LAYING PLANS", back_from="APPENDIX")
    assert "Sun Tzu said" in body
    assert "Intro by translator" not in body and "refs" not in body


def test_clean_removes_brackets_and_sections():
    text = "preamble\nI. LAYING PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nx"
    out = ap.clean(text, front_until="I. LAYING PLANS", back_from="APPENDIX")
    assert "War is deception." in out
    assert "Tu Mu" not in out and "preamble" not in out and "[" not in out
```

- [ ] **Step 6: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: FAIL — `AttributeError: module 'corpusbuild.apparatus' has no attribute 'strip_sections'`

- [ ] **Step 7: Implement `strip_sections` + `clean`**

```python
# append to scripts/corpusbuild/apparatus.py
_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")


def strip_sections(text, front_until=None, back_from=None):
    """Срез фронт/бэк-материи: всё ДО строки с front_until и ОТ строки с back_from. None → не резать."""
    lines = text.splitlines()
    start, end = 0, len(lines)
    if front_until:
        for i, ln in enumerate(lines):
            if front_until in ln:
                start = i
                break
    if back_from:
        for i in range(len(lines) - 1, -1, -1):
            if back_from in lines[i]:
                end = i
                break
    return "\n".join(lines[start:end]).strip()


def clean(text, front_until=None, back_from=None):
    """Только слова автора: strip_sections + удалить инлайн [...]-спаны (повторно для вложенности)."""
    body = strip_sections(text, front_until, back_from)
    prev = None
    while prev != body:                       # вложенные [a [b] c] схлопываем итеративно
        prev = body
        body = _BRACKET_RE.sub("", body)
    return re.sub(r"[ \t]{2,}", " ", body).strip()
```

- [ ] **Step 8: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: PASS (5 passed)

- [ ] **Step 9: Write failing test for `scan`**

```python
# append to tests/test_apparatus.py
def test_scan_detects_apparatus():
    text = ("An Introduction by the translator about Wellington.\n" * 6 +
            "I. LAYING PLANS\n" +
            "Sun Tzu said: war is deception. [Tu Mu says: deceive.]\n" * 5 +
            "APPENDIX\nbibliography\n")
    r = ap.scan(text)
    assert r["has_apparatus"] is True
    assert r["signals"]["front_until"] == "I. LAYING PLANS"
    assert r["signals"]["back_from"].startswith("APPENDIX")
    assert r["inline_commentary"] == "bracket"
    assert r["suggested_mode"] == "tier"
    assert r["sample_author"] and r["sample_apparatus"]


def test_scan_clean_text_no_apparatus():
    r = ap.scan("Just plain prose with no editorial apparatus at all. " * 20)
    assert r["has_apparatus"] is False
    assert r["inline_commentary"] is None
```

- [ ] **Step 10: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'scan'`

- [ ] **Step 11: Implement detectors + `scan`**

```python
# append to scripts/corpusbuild/apparatus.py
def _bracket_ratio(lines):
    nonblank = [l for l in lines if l.strip()]
    return (sum(1 for l in nonblank if "[" in l) / len(nonblank)) if nonblank else 0.0


def _first_line(lines, rx):
    for i, ln in enumerate(lines):
        if rx.match(ln):
            return i, ln.strip()
    return None, None


def scan(text):
    """Детерминированный отчёт об аппарате. Поле signals — СЛУЖЕБНОЕ (юзеру не показывать)."""
    lines = text.splitlines()
    bracket_ratio = _bracket_ratio(lines)
    commentator_hits = sum(text.count(c) for c in _COMMENTATORS)
    fi, front_marker = _first_line(lines, _FRONT_RE)
    bi, back_marker = _first_line(lines, _BACK_RE)
    front_ok = fi is not None and fi > 3              # есть что отрезать спереди
    back_ok = bi is not None
    bracket = bracket_ratio >= 0.25 or commentator_hits >= 5
    has_apparatus = bracket or front_ok or back_ok
    sample_app = next((l.strip() for l in lines if "[" in l and len(l.strip()) > 20), "")
    sample_auth = next((l.strip() for l in lines
                        if l.strip() and "[" not in l and len(l.strip()) > 20
                        and not any(c in l for c in _COMMENTATORS)), "")
    return {
        "has_apparatus": has_apparatus,
        "signals": {
            "bracket_ratio": round(bracket_ratio, 3),
            "commentator_hits": commentator_hits,
            "front_until": front_marker if front_ok else None,
            "back_from": back_marker if back_ok else None,
            "front_confident": front_ok,
            "back_confident": back_ok,
        },
        # неуверенно, если аппарат есть, но границы не нашлись — хост уточняет
        "needs_host_review": has_apparatus and not (front_ok and back_ok),
        "sample_author": sample_auth,
        "sample_apparatus": sample_app,
        "suggested_mode": "tier",
        "inline_commentary": "bracket" if bracket else None,
    }
```

- [ ] **Step 12: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: PASS (7 passed)

- [ ] **Step 13: Commit**

```bash
git add scripts/corpusbuild/apparatus.py tests/test_apparatus.py
git commit -m "feat(apparatus): чистый детектор аппарата — scan/clean/split_inline (0 ollama)"
```

---

### Task 2: `tier_records` + ingest-интеграция (секции + инлайн в один проход)

**Files:**
- Modify: `scripts/corpusbuild/apparatus.py` (добавить `tier_records`)
- Modify: `scripts/corpusbuild/clean.py` (обёртка `apparatus_tier`)
- Modify: `scripts/corpusbuild/pipeline.py` (ветка по `mode=="tier"`)
- Modify: `tests/test_apparatus.py`

- [ ] **Step 1: Write failing test for `tier_records`**

```python
# append to tests/test_apparatus.py
def _recs(text):
    return [(("line", i + 1), ln) for i, ln in enumerate(text.splitlines()) if ln.strip()]


def test_tier_records_body_inline_and_confident_sections():
    text = ("Intro prose\nI. PLANS\nWar is deception. [Tu Mu: yes.]\nKnow the enemy.\nAPPENDIX\nrefs")
    out = ap.tier_records(_recs(text), front_until="I. PLANS", back_from="APPENDIX",
                          front_confident=True, back_confident=True, inline="bracket")
    tiers = {seg["text"][:12]: seg["tier"] for seg in out}
    assert all("Intro prose" not in s["text"] and "refs" not in s["text"] for s in out)  # секции срезаны
    assert any(s["tier"] == "P1" and "War is deception" in s["text"] for s in out)        # автор 🔵
    assert any(s["tier"] == "S1" and "Tu Mu" in s["text"] for s in out)                   # коммент 🟢


def test_tier_records_uncertain_front_margin_is_green_not_blue():
    # fail-closed: неуверенная фронт-секция → S1, НЕ P1
    text = "Mystery preamble line\nI. PLANS\nWar is deception."
    out = ap.tier_records(_recs(text), front_until="I. PLANS", back_from=None,
                          front_confident=False, back_confident=False, inline="bracket")
    pre = [s for s in out if "Mystery preamble" in s["text"]]
    assert pre and pre[0]["tier"] == "S1"            # неуверенно → 🟢, не 🔵
```

- [ ] **Step 2: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -k tier_records -q`
Expected: FAIL — `AttributeError: ... has no attribute 'tier_records'`

- [ ] **Step 3: Implement `tier_records`**

```python
# append to scripts/corpusbuild/apparatus.py
def tier_records(recs, front_until=None, back_from=None,
                 front_confident=False, back_confident=False, inline="bracket"):
    """recs: [(loc, text)] → [{loc, text, tier}]. Секции-поля: drop если уверенно, иначе S1 (🟢,
    fail-closed). Тело: split_inline → author=P1 (🔵), commentary=S1 (🟢)."""
    texts = [t for _, t in recs]
    start, end = 0, len(recs)
    if front_until:
        for i, t in enumerate(texts):
            if front_until in t:
                start = i
                break
    if back_from:
        for i in range(len(texts) - 1, -1, -1):
            if back_from in texts[i]:
                end = i
                break
    out = []
    for i, (loc, text) in enumerate(recs):
        if i < start or i >= end:                     # поле (вступление/приложение)
            confident = front_confident if i < start else back_confident
            if confident:
                continue                              # уверенно аппарат → drop
            out.append({"loc": loc, "text": text, "tier": "S1"})   # неуверенно → 🟢
            continue
        if inline == "bracket":
            for seg, role in split_inline(text):
                out.append({"loc": loc, "text": seg, "tier": "P1" if role == "author" else "S1"})
        else:
            out.append({"loc": loc, "text": text, "tier": "P1"})
    return out
```

- [ ] **Step 4: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -k tier_records -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Write failing e2e test (pipeline tier mode on a manifest source)**

```python
# append to tests/test_apparatus.py
import json


def _make_advisor(tmp_path, body, manifest):
    sd = tmp_path / "sources"
    sd.mkdir(parents=True)
    (sd / "book.txt").write_text(body, encoding="utf-8")
    (sd / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(tmp_path)


def test_pipeline_tier_mode_tags_author_blue_commentary_green(tmp_path):
    from corpusbuild import pipeline
    body = "Intro\nI. PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nrefs\n"
    man = {"book.txt": {"tier": "P1", "apparatus": {
        "mode": "tier", "inline_commentary": "bracket",
        "front_until": "I. PLANS", "back_from": "APPENDIX",
        "front_confident": True, "back_confident": True}}}
    adv = _make_advisor(tmp_path, body, man)
    chunks = pipeline.build(adv)
    tiers = {c["tier"] for c in chunks}
    blob = " ".join(c["text"] for c in chunks)
    assert "P1" in tiers and "S1" in tiers           # оба тира появились
    assert "Tu Mu" not in " ".join(c["text"] for c in chunks if c["tier"] == "P1")  # коммент не в 🔵
    assert "Intro" not in blob and "refs" not in blob                                # секции срезаны
```

- [ ] **Step 6: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -k pipeline_tier -q`
Expected: FAIL — chunks tag всё как P1 через `tag_regions` (ветка ещё не добавлена); assert на «Tu Mu не в 🔵» падает.

- [ ] **Step 7: Add `apparatus_tier` wrapper to `clean.py`**

```python
# append to scripts/corpusbuild/clean.py
def apparatus_tier(recs, source: str, advisor_dir: str):
    """Тиринг источника с apparatus.mode=='tier': секции + инлайн-комментарий (зовёт apparatus)."""
    from engine import provenance as prov
    from .apparatus import tier_records
    man = prov.load_manifest(advisor_dir) or {}
    appa = (man.get(source) or {}).get("apparatus") or {}
    return tier_records(recs,
                        front_until=appa.get("front_until"), back_from=appa.get("back_from"),
                        front_confident=appa.get("front_confident", False),
                        back_confident=appa.get("back_confident", False),
                        inline=appa.get("inline_commentary", "bracket"))
```

- [ ] **Step 8: Branch `pipeline.build` on tier mode**

Modify `scripts/corpusbuild/pipeline.py` — replace the per-source body of the `for fn` loop:

```python
    for fn in sorted(os.listdir(src_dir)):
        if os.path.splitext(fn)[1].lower() not in SUPPORTED:
            continue
        recs = ingest.extract_source(os.path.join(src_dir, fn))
        if _is_tier_mode(fn, advisor_dir):           # apparatus tier → секции+инлайн одним проходом
            tagged = clean.apparatus_tier(recs, fn, advisor_dir)
        else:
            tagged = clean.tag_regions(recs, fn, advisor_dir)
        all_chunks.extend(chunkmod.chunk_records(tagged, fn, chunk_cfg))
```

Add helper near top of `pipeline.py` (after imports):

```python
def _is_tier_mode(source: str, advisor_dir: str) -> bool:
    from engine import provenance as prov
    man = prov.load_manifest(advisor_dir) or {}
    return ((man.get(source) or {}).get("apparatus") or {}).get("mode") == "tier"
```

- [ ] **Step 9: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -q`
Expected: PASS (all)

- [ ] **Step 10: Run full suite (no regressions, no-deps)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: PASS (all prior + new)

- [ ] **Step 11: Commit**

```bash
git add scripts/corpusbuild/apparatus.py scripts/corpusbuild/clean.py scripts/corpusbuild/pipeline.py tests/test_apparatus.py
git commit -m "feat(apparatus): tier_records + pipeline-ветка mode=tier (секции drop/🟢, инлайн author 🔵/коммент 🟢)"
```

---

### Task 3: Манифест-схема — валидация поля `apparatus`

**Files:**
- Modify: `scripts/manifest_builder.py:33-58` (функция `validate_manifest`)
- Modify: `tests/test_apparatus.py`

- [ ] **Step 1: Write failing test**

```python
# append to tests/test_apparatus.py
def test_validate_manifest_checks_apparatus():
    import manifest_builder as mb
    import tempfile, os as _os
    with tempfile.TemporaryDirectory() as sd:
        with open(_os.path.join(sd, "book.txt"), "w", encoding="utf-8") as f:
            f.write("I. PLANS\nbody\n")
        bad = {"book.txt": {"tier": "P1", "apparatus": {"mode": "nonsense"}}}
        r = mb.validate_manifest(bad, sd)
        assert not r["ok"] and any("apparatus-mode" in p["issue"] for p in r["problems"])
        # маркер границы, которого нет в тексте, ловится
        bad2 = {"book.txt": {"tier": "P1", "apparatus": {"mode": "tier", "front_until": "MISSING"}}}
        r2 = mb.validate_manifest(bad2, sd)
        assert not r2["ok"] and any(p.get("marker") == "MISSING" for p in r2["problems"])
        ok = {"book.txt": {"tier": "P1", "apparatus": {"mode": "tier", "front_until": "I. PLANS"}}}
        assert mb.validate_manifest(ok, sd)["ok"]
```

- [ ] **Step 2: Run, verify fail**

Run: `python3 -m pytest tests/test_apparatus.py -k validate_manifest -q`
Expected: FAIL — bad mode не отлавливается (`r["ok"]` is True).

- [ ] **Step 3: Implement apparatus-validation in `validate_manifest`**

In `scripts/manifest_builder.py`, inside the `for src, rec in manifest.items():` loop, after the
existing `regions` loop (before the function returns), insert:

```python
        appa = rec.get("apparatus")
        if appa is not None:
            if appa.get("mode") not in ("tier", "clean", "raw"):
                problems.append({"source": src, "issue": f"apparatus-mode:{appa.get('mode')}"})
            for edge in ("front_until", "back_from"):
                marker = appa.get(edge)
                if marker and marker not in text:
                    problems.append({"source": src, "marker": marker,
                                     "issue": f"apparatus-marker-not-in-source:{edge}"})
```

(`text` is already read earlier in the loop for region checks.)

- [ ] **Step 4: Run, verify pass**

Run: `python3 -m pytest tests/test_apparatus.py -k validate_manifest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/manifest_builder.py tests/test_apparatus.py
git commit -m "feat(manifest): валидация apparatus (mode ∈ tier/clean/raw, маркеры границ есть в тексте)"
```

---

### Task 4: `add_source` — режимы auto/tier/clean/raw + hint/adjustments

**Files:**
- Modify: `scripts/mcp_server.py` (`_add_source` ~271-299; tool-schema `add_source`)
- Modify: `tests/test_lifecycle_tools.py`

- [ ] **Step 1: Write failing test (auto-detect → tier + hint + adjustments)**

```python
# append to tests/test_lifecycle_tools.py
def test_add_source_text_with_apparatus_auto_tiers(tmp_path):
    # вставка текста с аппаратом → mode=tier авто, дружелюбный hint, опц. правки (не блокирует)
    body = ("Translator intro about Wellington and Waterloo.\n" * 6 +
            "I. LAYING PLANS\n" +
            "War is based on deception. [Tu Mu: deceive the foe.]\n" * 4 +
            "APPENDIX\nbibliography\n")
    r = dispatch("add_source", {"advisor_dir": "advisors/x-apparatus",
                                "text": body, "basename": "book", "tier": "P1"})
    assert r["ok"] and r["mode"] == "tier"
    assert r["hint"] and "🔵" in r["hint"] and "🟢" in r["hint"]
    assert any(a["mode"] == "clean" for a in r["adjustments"])      # «только его слова»
    # манифест записан с apparatus.mode=tier
    import json, os
    man = json.load(open(os.path.join(r["advisor_dir"], "sources", "manifest.json")))
    entry = next(v for k, v in man.items() if k.startswith("book"))
    assert entry["apparatus"]["mode"] == "tier"


def test_add_source_clean_mode_writes_clean_file(tmp_path):
    body = "intro\nI. LAYING PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nx\n"
    r = dispatch("add_source", {"advisor_dir": "advisors/x-clean", "text": body,
                                "basename": "book", "tier": "P1", "mode": "clean",
                                "front_until": "I. LAYING PLANS", "back_from": "APPENDIX"})
    assert r["ok"] and r["mode"] == "clean"
    import os
    files = os.listdir(os.path.join(r["advisor_dir"], "sources"))
    assert any(f.endswith(".clean.txt") for f in files)            # чистый файл создан
    assert any(f == "book.txt" for f in files)                     # сырой сохранён (реверс)
```

> Примечание: тест-файл уже имеет autouse-фикстуру `_root`→tmp_path (write-guard), поэтому запись в
> `advisors/...` идёт под tmp_path. Это существующий паттерн в `tests/test_lifecycle_tools.py`.

- [ ] **Step 2: Run, verify fail**

Run: `python3 -m pytest tests/test_lifecycle_tools.py -k apparatus -q`
Expected: FAIL — `KeyError: 'mode'` (нет в ответе) / нет apparatus-логики.

- [ ] **Step 3: Implement apparatus flow in `_add_source`**

Replace `_add_source` in `scripts/mcp_server.py` with (keeps existing land/SSRF/traversal guards):

```python
def _add_source(advisor_dir, url=None, text=None, path=None, basename=None,
                tier="P1", license=None, mode="auto", front_until=None, back_from=None):
    """Затянуть источник без шелла. Если PD-том содержит редакторский аппарат (вступление/инлайн-
    комментарий/приложения) — НЕ запекать его как слова автора: дефолт mode=tier (автор 🔵, коммент
    🟢), не блокируя выбором. mode: auto|tier|clean|raw. front_until/back_from — хост-оверрайды границ."""
    import collect_common as cc
    from corpusbuild import apparatus as ap
    d, err = _resolve_under_root(advisor_dir)        # write-side traversal-гард
    if err:
        return err
    try:
        raw, hint, prov, lic = _load_source_text(url=url, path=path, text=text, license=license)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"источник не загрузился: {e}"}

    report = ap.scan(raw)
    fu = front_until or report["signals"]["front_until"]
    bf = back_from or report["signals"]["back_from"]
    effective = ("tier" if report["has_apparatus"] else "raw") if mode == "auto" else mode

    landed_name = basename or hint
    if effective == "clean":                          # пишем ЧИСТЫЙ файл + сохраняем сырой
        cleaned = ap.clean(raw, fu, bf)
        cc.land_to_sources(d, landed_name, raw, url=prov, license_note=lic)          # сырой (реверс)
        clean_src = cc.land_to_sources(d, (landed_name or "src") + ".clean", cleaned,
                                       url=prov, license_note=lic)
        fn = os.path.basename(clean_src)
        appa = {"mode": "clean", "source_raw": (landed_name or "src") + ".txt"}
    else:
        src_path = cc.land_to_sources(d, landed_name, raw, url=prov, license_note=lic)
        fn = os.path.basename(src_path)
        if effective == "tier":
            appa = {"mode": "tier", "inline_commentary": report["inline_commentary"] or "bracket",
                    "front_until": fu, "back_from": bf,
                    "front_confident": report["signals"]["front_confident"],
                    "back_confident": report["signals"]["back_confident"]}
        else:
            appa = {"mode": "raw"}

    man_p = os.path.join(d, "sources", "manifest.json")
    try:
        man = json.load(open(man_p, encoding="utf-8"))
    except Exception:
        man = {}
    man[fn] = {"tier": tier, "apparatus": appa}
    with open(man_p, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)

    out = {"ok": True, "advisor_dir": d, "source_file": fn, "tier": tier,
           "mode": effective, "chars": len(raw),
           "next_action": "Собери корпус: build_advisor(advisor_dir)."}
    if effective == "tier":
        out["hint"] = ("Добавил источник. Его слова помечу 🔵, толкования/комментарий — 🟢, "
                       "вступление и приложения отброшу. Хочешь только его слова — скажи об этом.")
        out["adjustments"] = [{"phrase": "только его слова", "mode": "clean"},
                              {"phrase": "оставь комментарии как есть", "mode": "raw"}]
        out["needs_host_review"] = report["needs_host_review"]
    elif effective == "clean":
        out["hint"] = "Добавил только слова автора (🔵); комментарий и служебные разделы убраны."
    else:
        out["hint"] = "Добавил источник."
    return out
```

- [ ] **Step 4: Add params to the `add_source` tool schema**

In `scripts/mcp_server.py` find the `add_source` entry in `list_tools()` and add to its
`input_schema.properties` (next to existing `tier`/`license`):

```python
                "mode": {"type": "string", "enum": ["auto", "tier", "clean", "raw"],
                         "description": "auto (дефолт): детект аппарата → tier, если есть. tier/clean/raw — явно."},
                "front_until": {"type": "string", "description": "хост-оверрайд: маркер конца вступления"},
                "back_from": {"type": "string", "description": "хост-оверрайд: маркер начала приложений"},
```

- [ ] **Step 5: Run, verify pass**

Run: `python3 -m pytest tests/test_lifecycle_tools.py -k apparatus -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Run full suite (no-deps)**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: PASS — note: existing `add_source` tests that asserted exact response keys may need
`mode`/`hint` tolerated. If `test_add_source_text_lands_and_sets_tier_then_builds` asserts an exact
key set, relax it to a subset check (`{"ok","advisor_dir","source_file","tier"} <= set(r)`).

- [ ] **Step 7: Commit**

```bash
git add scripts/mcp_server.py tests/test_lifecycle_tools.py
git commit -m "feat(add_source): авто-детект аппарата → mode=tier/clean/raw + hint/adjustments (act-then-offer)"
```

---

### Task 5: INSTRUCTIONS rule 10 (подача выбора не-тех юзеру)

**Files:**
- Modify: `scripts/mcp_server.py` (константа `INSTRUCTIONS`)
- Modify: `tests/test_lifecycle_tools.py`

- [ ] **Step 1: Write failing test**

```python
# append to tests/test_lifecycle_tools.py
def test_instructions_have_apparatus_rule():
    ins = __import__("mcp_server").INSTRUCTIONS
    assert "АППАРАТ" in ins or "аппарат" in ins
    assert "🔵 автор" in ins or ("🔵" in ins and "🟢" in ins and "толков" in ins.lower())
    assert "не как обязательный выбор" in ins or "не блокируй" in ins.lower()
```

- [ ] **Step 2: Run, verify fail**

Run: `python3 -m pytest tests/test_lifecycle_tools.py -k apparatus_rule -q`
Expected: FAIL — нет правила.

- [ ] **Step 3: Add rule 10 to `INSTRUCTIONS`**

Append before the closing `"""` of the `INSTRUCTIONS` constant:

```python

10. КНИГА С РЕДАКТОРСКИМ АППАРАТОМ. add_source сам детектит вступление переводчика, инлайн-комментарий
   толкователей и приложения. Когда он вернул mode=tier с hint/adjustments — сообщи юзеру простым
   языком, ЧТО чьими словами станет (🔵 = слова автора, 🟢 = толкования/комментарий, вступление и
   приложения отброшены), и предложи правку ФРАЗОЙ («хочешь только его слова — скажи»), НЕ как
   обязательный выбор и не блокируя. Правки обратимы: «только его слова» → add_source(source_file,
   mode=clean) + пересборка; сырой файл цел. needs_host_review=true → сам сверь границы книги
   (где кончается предисловие, где начинаются приложения) и при нужде уточни их человеческим
   вопросом или передай front_until/back_from; технических полей (signals/доли) не показывай.
```

- [ ] **Step 4: Run, verify pass**

Run: `python3 -m pytest tests/test_lifecycle_tools.py -k apparatus_rule -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/mcp_server.py tests/test_lifecycle_tools.py
git commit -m "feat(instructions): rule 10 — подача аппарат-выбора не-тех юзеру (act-then-offer)"
```

---

### Task 6: Регрессия на реальном Сунь-Цзы + чистка артефакта

**Files:**
- Modify: `tests/test_apparatus.py` (опциональный сетевой тест, помечен skip без сети)

- [ ] **Step 1: Add an opt-in regression test (skipped by default)**

```python
# append to tests/test_apparatus.py
import pytest


@pytest.mark.skipif(not os.environ.get("RUN_NET_TESTS"),
                    reason="сетевой тест Gutenberg — включи RUN_NET_TESTS=1")
def test_real_sun_tzu_tier_demotes_commentary(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import collect_common as cc, collect_pd
    from corpusbuild import pipeline
    raw = collect_pd.strip_gutenberg(cc.fetch("https://www.gutenberg.org/cache/epub/132/pg132.txt"))
    r = ap.scan(raw)
    assert r["has_apparatus"] and r["inline_commentary"] == "bracket"
    sd = tmp_path / "sources"; sd.mkdir(parents=True)
    (sd / "aow.txt").write_text(raw, encoding="utf-8")
    man = {"aow.txt": {"tier": "P1", "apparatus": {
        "mode": "tier", "inline_commentary": "bracket",
        "front_until": r["signals"]["front_until"], "back_from": r["signals"]["back_from"],
        "front_confident": r["signals"]["front_confident"],
        "back_confident": r["signals"]["back_confident"]}}}
    (sd / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    chunks = pipeline.build(str(tmp_path))
    blue = [c for c in chunks if c["tier"] == "P1"]
    green = [c for c in chunks if c["tier"] == "S1"]
    # комментаторы НЕ должны доминировать в 🔵; должны жить в 🟢
    blue_text = " ".join(c["text"] for c in blue)
    assert "Wellington" not in blue_text                       # вступление вне 🔵
    assert green, "толкования должны попасть в 🟢, а не исчезнуть"
```

- [ ] **Step 2: Run it explicitly (manual, with network)**

Run: `RUN_NET_TESTS=1 python3 -m pytest tests/test_apparatus.py -k real_sun_tzu -q`
Expected: PASS. (Если границы Giles-издания не совпали — подстроить `_FRONT_RE`/`_BACK_RE` в Task 1,
это и есть «ризонинг хоста» по реальной книге.)

- [ ] **Step 3: Remove the throwaway sun-tzu advisor from the e2e walk**

```bash
rm -rf advisors/sun-tzu        # тестовый артефакт прошлого прогона (гитигнор, в репо его нет)
```

- [ ] **Step 4: Run full suite both modes (final gate)**

Run: `python3 -m pytest tests/ -q && HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: PASS both.

- [ ] **Step 5: Commit**

```bash
git add tests/test_apparatus.py
git commit -m "test(apparatus): opt-in регрессия на реальном Сунь-Цзы (RUN_NET_TESTS)"
```

---

## Self-Review (выполнено при написании плана)

**Spec coverage:**
- scan/clean/split_inline → Task 1 ✓; tier_records (секции+инлайн, fail-closed margins) → Task 2 ✓;
  реестр детекторов → Task 1 (функции `_FRONT_RE`/`_BACK_RE`/`_COMMENTATORS` + scan; расширяется
  добавлением паттерна) ✓; манифест-схема+валидация → Task 3 ✓; add_source auto/tier/clean/raw +
  hint/adjustments/needs_host_review → Task 4 ✓; переключаемость/реверс (сырой файл цел) → Task 4
  (clean пишет .clean.txt, сырой остаётся; tier читает raw) ✓; INSTRUCTIONS подача → Task 5 ✓;
  реальный Сунь-Цзы → Task 6 ✓; инвариант fail-closed → пин-тесты в Task 1/2 ✓.
- Уточнение vs спека: «реестр детекторов» в v1 реализован как набор regex/лексикон внутри `scan`
  (не формальный список функций) — YAGNI; расширяется добавлением паттерна. Поведение спеки сохранено.

**Placeholder scan:** нет TBD/«handle edge cases» — весь код приведён дословно.

**Type consistency:** `tier_records`/`apparatus_tier` возвращают `[{loc,text,tier}]` — ровно вход
`chunk_records` (`rec["tier"]/["text"]/["loc"]`). `scan` ключи (`signals.front_until`,
`front_confident`, `inline_commentary`) одинаковы в Task 1, 2, 4. `apparatus.mode ∈ {tier,clean,raw}`
согласован в Task 3/4. Манифест-запись `{tier, apparatus:{mode,...}}` одинакова в add_source и читателях.
