# Corpus Builder P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить наивный `build_advisor.py` на staged, идемпотентный, версионируемый сборщик корпуса с пер-регионными тирами происхождения, единым `build/`-резолвером и валидационным гейтом — фундамент под provenance-схему и eval-матрицу.

**Architecture:** Пакет `scripts/corpus/` из узких стадий-модулей (ingest → clean → chunk → index), оркестрируемых `pipeline.build()`. Тир происхождения «запекается» в каждый чанк на стадии clean (через `engine/provenance.py` + `sources/manifest.json` с пер-регионными маркерами). Все читатели корпуса ходят через единый `corpus.paths.corpus_path()`, который отдаёт `advisors/<slug>/build/corpus.jsonl` (с фолбэком на легаси-путь). Воспроизводимость — `build.lock.json` (хеши источников + config). Доктор проверяет инварианты рва (нет S→🔵 утечки).

**Tech Stack:** Python 3 (stdlib only в новых модулях), pytest, существующие `scripts/engine/*` и `scripts/tier_full.py` (bge-m3 через ollama). Спека: `docs/superpowers/specs/2026-06-25-corpus-builder-design.md`.

---

## File Structure

**Новые модули (`scripts/corpus/`):**
- `paths.py` — единый резолвер путей (`build_dir`, `corpus_path`, `lock_path`) с легаси-фолбэком.
- `ingest.py` — извлечение текста с авто-кодировкой и позиционным провенансом.
- `clean.py` — нарезка источника на регионы по маркерам манифеста + присвоение тира.
- `chunk.py` — чанкинг (стратегия `size`), несущий `tier`/`region` в каждый чанк.
- `buildlock.py` — запись `build.lock.json` (хеши источников, config, счётчики).
- `doctor.py` — валидационный гейт (распределение тиров, S→🔵 утечка, спот-чек).
- `pipeline.py` — оркестратор `build(advisor_dir, config, built_at)`.

**Новое в `scripts/engine/`:**
- `provenance.py` — загрузка манифеста, `tier_for(source, line_no)` с учётом регионов.

**CLI:**
- `scripts/corpus_build.py` — точка входа (`build` / `--report`).

**Модификации (миграция на резолвер + tier-aware):**
- `scripts/tier_full.py` — читать через `corpus_path`; в meta класть `tier`.
- `scripts/engine/fidelity.py` — гейт 🔵 на тир (P1/P2); S→блок мисатрибуции; читать через `corpus_path`.
- `scripts/engine/lexical.py`, `scripts/eval.py`, `scripts/board_init.py`, `scripts/gen_golden.py`, `scripts/exp_kernels.py` — читать через `corpus_path`.

**Тесты:** `tests/test_corpus_paths.py`, `tests/test_provenance.py`, `tests/test_corpus_ingest.py`, `tests/test_corpus_clean.py`, `tests/test_corpus_chunk.py`, `tests/test_buildlock.py`, `tests/test_corpus_doctor.py`, `tests/test_fidelity_tiers.py`.

**Манифест:** структура чанка получает поля `tier` (str) и `region` (int|null). Манифест-источник получает опциональный `regions: [{tier, from?, until?}]`.

---

### Task 1: Резолвер путей (`corpus/paths.py`)

**Files:**
- Create: `scripts/corpus/__init__.py` (пустой пакет-маркер)
- Create: `scripts/corpus/paths.py`
- Test: `tests/test_corpus_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_paths.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import paths

def test_corpus_path_prefers_build(tmp_path):
    adv = tmp_path / "marcus"
    (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    assert paths.corpus_path(str(adv)) == str(adv / "build" / "corpus.jsonl")

def test_corpus_path_falls_back_to_legacy(tmp_path):
    adv = tmp_path / "marcus"
    adv.mkdir()
    (adv / "corpus.jsonl").write_text("{}\n", encoding="utf-8")
    assert paths.corpus_path(str(adv)) == str(adv / "corpus.jsonl")

def test_corpus_path_defaults_to_build_when_neither_exists(tmp_path):
    adv = tmp_path / "marcus"; adv.mkdir()
    assert paths.corpus_path(str(adv)) == str(adv / "build" / "corpus.jsonl")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/__init__.py
# (пустой — маркер пакета)
```

```python
# scripts/corpus/paths.py
"""Единый резолвер путей корпуса. Все читатели ходят сюда, чтобы build/-реорг
не разъехался по 7 файлам. corpus_path: предпочитает build/, падает на легаси."""
import os


def build_dir(advisor_dir: str) -> str:
    return os.path.join(advisor_dir, "build")


def lock_path(advisor_dir: str) -> str:
    return os.path.join(build_dir(advisor_dir), "build.lock.json")


def corpus_path(advisor_dir: str) -> str:
    """build/corpus.jsonl, если он есть; иначе легаси advisors/<slug>/corpus.jsonl,
    если есть; иначе дефолт build/corpus.jsonl (для свежей сборки)."""
    new = os.path.join(build_dir(advisor_dir), "corpus.jsonl")
    legacy = os.path.join(advisor_dir, "corpus.jsonl")
    if os.path.isfile(new):
        return new
    if os.path.isfile(legacy):
        return legacy
    return new
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_paths.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/__init__.py scripts/corpus/paths.py tests/test_corpus_paths.py
git commit -m "corpus: единый резолвер путей (build/ с легаси-фолбэком)"
```

---

### Task 2: Провенанс и пер-регионные тиры (`engine/provenance.py`)

**Files:**
- Create: `scripts/engine/provenance.py`
- Test: `tests/test_provenance.py`

Манифест-источник может нести `regions: [{tier, from?, until?}]`, где `from`/`until` — подстроки-маркеры. Строки до первого `until` или от `from` до следующего `until` получают тир региона. Нет `regions` → весь файл = top-level `tier`. Нет источника в манифесте → `A` (fail-closed). Нет манифеста → `P1` (бэк-компат).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provenance.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import provenance as prov

def _write_manifest(adv, data):
    os.makedirs(os.path.join(adv, "sources"), exist_ok=True)
    json.dump(data, open(os.path.join(adv, "sources", "manifest.json"), "w", encoding="utf-8"))

def test_no_manifest_defaults_p1(tmp_path):
    adv = str(tmp_path)
    assert prov.tier_for("anything.txt", 5, adv) == "P1"

def test_source_not_in_manifest_is_fail_closed_A(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"known.txt": {"tier": "P1"}})
    assert prov.tier_for("unknown.txt", 1, adv) == "A"

def test_flat_tier_applies_whole_file(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"tarasov.txt": {"tier": "S1"}})
    assert prov.tier_for("tarasov.txt", 99, adv) == "S1"

def test_regions_assign_by_marker(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"med.txt": {"tier": "P1", "regions": [
        {"tier": "B", "until": "THE FIRST BOOK"},
        {"tier": "P1", "from": "THE FIRST BOOK", "until": "APPENDIX"},
        {"tier": "S1", "from": "APPENDIX"}]}})
    lines = ["Translator intro here.", "More intro.", "THE FIRST BOOK", "Real meditation.",
             "APPENDIX", "Editor notes."]
    tiers = [prov.tier_for_line("med.txt", i, lines, adv) for i in range(len(lines))]
    assert tiers == ["B", "B", "P1", "P1", "S1", "S1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_provenance.py -v`
Expected: FAIL — `ImportError: cannot import name 'provenance'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/engine/provenance.py
"""Провенанс: тир происхождения по источнику (+ региону внутри файла) из sources/manifest.json.
Нет манифеста → всё P1 (бэк-компат). Источник вне манифеста → A (fail-closed, см. спеку §1)."""
import os, json

_CACHE = {}


def load_manifest(advisor_dir: str) -> dict:
    path = os.path.join(advisor_dir, "sources", "manifest.json")
    key = (path, os.path.getmtime(path)) if os.path.isfile(path) else (path, 0)
    if key not in _CACHE:
        _CACHE[key] = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None
    return _CACHE[key]


def tier_for(source: str, line_no: int, advisor_dir: str) -> str:
    """Тир без знания текста (плоский). Для пер-регионного — tier_for_line."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "P1"
    entry = man.get(source)
    if entry is None:
        return "A"
    return entry.get("tier", "A")


def tier_for_line(source: str, line_no: int, lines, advisor_dir: str) -> str:
    """Пер-регионный тир: идёт по lines[0..line_no], переключая регион на маркерах from/until."""
    man = load_manifest(advisor_dir)
    if man is None:
        return "P1"
    entry = man.get(source)
    if entry is None:
        return "A"
    regions = entry.get("regions")
    if not regions:
        return entry.get("tier", "A")
    # текущий регион определяем по последнему сработавшему маркеру до line_no включительно
    cur = entry.get("tier", "A")
    active = regions[0]["tier"] if "from" not in regions[0] else cur
    seen = active
    for i in range(line_no + 1):
        ln = lines[i]
        for r in regions:
            mk = r.get("from") or r.get("until")
            if mk and mk in ln:
                seen = r["tier"]
    return seen
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_provenance.py -v`
Expected: PASS (4 passed). Если `test_regions_assign_by_marker` падает на границе — проверь, что маркер `until` переключает на ТИР СЛЕДУЮЩЕГО региона (в манифесте `from`-регион несёт нужный тир), а строка-маркер принадлежит региону, который ею ОТКРЫВАЕТСЯ.

- [ ] **Step 5: Commit**

```bash
git add scripts/engine/provenance.py tests/test_provenance.py
git commit -m "provenance: пер-регионные тиры из манифеста (fail-closed A)"
```

---

### Task 3: Ингест с авто-кодировкой (`corpus/ingest.py`)

**Files:**
- Create: `scripts/corpus/ingest.py`
- Test: `tests/test_corpus_ingest.py`

Переносит экстракторы из `build_advisor.py` (txt/md/pdf/epub) + добавляет авто-детект кодировки для текстовых (мы вручную ловили CP1251). Формат записи: `(("line", n), text)` как в `build_advisor.chunk_lines`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_ingest.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import ingest

def test_reads_utf8(tmp_path):
    p = tmp_path / "a.txt"; p.write_text("Привет мир\nвторая строка\n", encoding="utf-8")
    recs = ingest.extract_source(str(p))
    assert recs[0] == (("line", 1), "Привет мир")
    assert len(recs) == 2

def test_reads_cp1251(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("Управление по Макиавелли\n".encode("cp1251"))
    recs = ingest.extract_source(str(p))
    assert recs[0][1] == "Управление по Макиавелли"

def test_skips_blank_lines(tmp_path):
    p = tmp_path / "c.txt"; p.write_text("one\n\n\ntwo\n", encoding="utf-8")
    recs = ingest.extract_source(str(p))
    assert [r[1] for r in recs] == ["one", "two"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/ingest.py
"""Ингест: текст с позиционным провенансом + авто-детект кодировки (utf-8 → cp1251 → koi8-r → latin-1).
PDF/EPUB делегируем существующим экстракторам build_advisor (ленивый импорт)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_text_auto(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8", "cp1251", "koi8-r", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def extract_source(path: str):
    """→ [ (("line", n), text), ... ] для .txt/.md; для .pdf/.epub — провенанс page/chapter."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        lines = _read_text_auto(path).splitlines()
        return [(("line", i + 1), ln) for i, ln in enumerate(lines) if ln.strip()]
    import build_advisor
    if ext == ".pdf":
        return build_advisor.extract_pdf(path)
    if ext == ".epub":
        return build_advisor.extract_epub(path)
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_ingest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/ingest.py tests/test_corpus_ingest.py
git commit -m "corpus: ингест с авто-детектом кодировки (utf-8/cp1251/koi8-r)"
```

---

### Task 4: Чистка границ и регионы (`corpus/clean.py`)

**Files:**
- Create: `scripts/corpus/clean.py`
- Test: `tests/test_corpus_clean.py`

Принимает записи ингеста + имя источника, проставляет каждому `(loc, text, tier, region_idx)` через `provenance.tier_for_line`. Регион — индекс в списке `regions` (или 0). Так чанкинг сможет не склеивать соседние записи разных тиров.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_clean.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import clean

def _manifest(adv, data):
    os.makedirs(os.path.join(adv, "sources"), exist_ok=True)
    json.dump(data, open(os.path.join(adv, "sources", "manifest.json"), "w", encoding="utf-8"))

def test_tags_tier_per_region(tmp_path):
    adv = str(tmp_path)
    _manifest(adv, {"med.txt": {"tier": "P1", "regions": [
        {"tier": "B", "until": "THE FIRST BOOK"},
        {"tier": "P1", "from": "THE FIRST BOOK"}]}})
    recs = [(("line", 1), "intro"), (("line", 2), "THE FIRST BOOK"), (("line", 3), "real")]
    tagged = clean.tag_regions(recs, "med.txt", adv)
    assert [t["tier"] for t in tagged] == ["B", "P1", "P1"]
    assert tagged[0]["text"] == "intro" and tagged[0]["loc"] == ("line", 1)

def test_no_manifest_all_p1(tmp_path):
    adv = str(tmp_path)
    recs = [(("line", 1), "x"), (("line", 2), "y")]
    tagged = clean.tag_regions(recs, "f.txt", adv)
    assert all(t["tier"] == "P1" for t in tagged)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_clean.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.clean'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/clean.py
"""Чистка/границы: проставить тир каждому ингест-рекорду по регионам манифеста.
Чанкинг потом не склеивает соседей разных тиров (region-boundary)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import provenance as prov  # noqa: E402


def tag_regions(records, source: str, advisor_dir: str):
    """records: [ (loc, text), ... ] → [ {loc, text, tier}, ... ]."""
    lines = [txt for _, txt in records]
    out = []
    for i, (loc, txt) in enumerate(records):
        tier = prov.tier_for_line(source, i, lines, advisor_dir)
        out.append({"loc": loc, "text": txt, "tier": tier})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_clean.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/clean.py tests/test_corpus_clean.py
git commit -m "corpus: чистка границ — тир на регион через манифест"
```

---

### Task 5: Чанкинг с тиром (`corpus/chunk.py`)

**Files:**
- Create: `scripts/corpus/chunk.py`
- Test: `tests/test_corpus_chunk.py`

Стратегия `size` (как `build_advisor.chunk_lines`: ~target_chars с overlap), но НЕ склеивает записи разных тиров (граница региона рвёт чанк) и пишет `tier` в чанк. Чанк: `{source, tier, start, end, text}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_chunk.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import chunk

def test_chunk_carries_tier_and_source():
    tagged = [{"loc": ("line", 1), "text": "a" * 200, "tier": "P1"},
              {"loc": ("line", 2), "text": "b" * 200, "tier": "P1"}]
    chunks = chunk.chunk_records(tagged, "src.txt", {"target": 300, "overlap": 50})
    assert chunks[0]["source"] == "src.txt"
    assert chunks[0]["tier"] == "P1"
    assert "start" in chunks[0] and "end" in chunks[0]

def test_chunk_does_not_merge_across_tiers():
    tagged = [{"loc": ("line", 1), "text": "intro " * 30, "tier": "B"},
              {"loc": ("line", 2), "text": "body " * 30, "tier": "P1"}]
    chunks = chunk.chunk_records(tagged, "src.txt", {"target": 1000, "overlap": 0})
    tiers = {c["tier"] for c in chunks}
    assert tiers == {"B", "P1"}  # граница тира разорвала, не склеила в один чанк
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_chunk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.chunk'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/chunk.py
"""Чанкинг (стратегия size). Граница тира РВЁТ чанк (не склеиваем B-интро с P1-телом).
Каждый чанк несёт tier. Config: {target, overlap}."""


def chunk_records(tagged, source: str, config=None):
    config = config or {}
    target = int(config.get("target", 900))
    overlap = int(config.get("overlap", 180))
    chunks = []
    buf, start_loc, last_loc, cur_tier, cur = [], None, None, None, 0

    def flush():
        nonlocal buf, start_loc, last_loc, cur
        body = " ".join(buf).strip()
        if body:
            chunks.append({"source": source, "tier": cur_tier,
                           "start": list(start_loc), "end": list(last_loc), "text": body})

    for rec in tagged:
        if cur_tier is not None and rec["tier"] != cur_tier:
            flush(); buf, start_loc, cur = [], None, 0      # граница тира
        cur_tier = rec["tier"]
        if start_loc is None:
            start_loc = rec["loc"]
        buf.append(rec["text"]); last_loc = rec["loc"]; cur += len(rec["text"]) + 1
        if cur >= target:
            flush()
            tail, tlen = [], 0
            for t in reversed(buf):
                tail.insert(0, t); tlen += len(t) + 1
                if tlen >= overlap:
                    break
            buf = tail; start_loc = last_loc; cur = sum(len(t) + 1 for t in buf)
    if buf:
        flush()
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_chunk.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/chunk.py tests/test_corpus_chunk.py
git commit -m "corpus: чанкинг size с тиром, граница тира рвёт чанк"
```

---

### Task 6: build.lock (`corpus/buildlock.py`)

**Files:**
- Create: `scripts/corpus/buildlock.py`
- Test: `tests/test_buildlock.py`

Воспроизводимость: хеши источников + config + счётчики тиров. `built_at` передаётся аргументом (детерминизм/тестируемость).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_buildlock.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import buildlock

def test_lock_records_hashes_and_counts(tmp_path):
    adv = tmp_path / "adv"; (adv / "sources").mkdir(parents=True); (adv / "build").mkdir()
    (adv / "sources" / "a.txt").write_text("hello", encoding="utf-8")
    chunks = [{"tier": "P1"}, {"tier": "P1"}, {"tier": "S1"}]
    lock = buildlock.write_lock(str(adv), {"chunk": {"target": 900}}, chunks, built_at="2026-06-25T00:00:00Z")
    assert lock["counts"] == {"P1": 2, "S1": 1, "chunks": 3}
    assert "a.txt" in lock["sources"] and lock["sources"]["a.txt"].startswith("sha256:")
    on_disk = json.load(open(os.path.join(str(adv), "build", "build.lock.json"), encoding="utf-8"))
    assert on_disk["built_at"] == "2026-06-25T00:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_buildlock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.buildlock'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/buildlock.py
"""build.lock.json — воспроизводимость: хеши источников + config + счётчики тиров.
built_at передаётся аргументом (в скриптах нет argless-времени для детерминизма)."""
import os, json, hashlib
from collections import Counter
from . import paths


def _hash_file(path: str) -> str:
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return f"sha256:{h}"


def write_lock(advisor_dir: str, config: dict, chunks, built_at: str) -> dict:
    src_dir = os.path.join(advisor_dir, "sources")
    sources = {}
    if os.path.isdir(src_dir):
        for fn in sorted(os.listdir(src_dir)):
            fp = os.path.join(src_dir, fn)
            if os.path.isfile(fp) and not fn.endswith(".json"):
                sources[fn] = _hash_file(fp)
    counts = dict(Counter(c["tier"] for c in chunks))
    counts["chunks"] = len(chunks)
    lock = {"built_at": built_at, "config": config, "sources": sources, "counts": counts}
    os.makedirs(paths.build_dir(advisor_dir), exist_ok=True)
    json.dump(lock, open(paths.lock_path(advisor_dir), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return lock
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_buildlock.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/buildlock.py tests/test_buildlock.py
git commit -m "corpus: build.lock (хеши источников + config + счётчики тиров)"
```

---

### Task 7: Оркестратор + CLI (`corpus/pipeline.py`, `corpus_build.py`)

**Files:**
- Create: `scripts/corpus/pipeline.py`
- Create: `scripts/corpus_build.py`
- Test: `tests/test_corpus_pipeline.py`

`build()` гоняет ingest→clean→chunk по всем источникам, пишет `build/corpus.jsonl` + lock. Возвращает список чанков. CLI — тонкая обёртка.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_pipeline.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import pipeline, paths

def test_build_writes_tiered_corpus(tmp_path):
    adv = tmp_path / "adv"; (adv / "sources").mkdir(parents=True)
    (adv / "sources" / "work.txt").write_text(("Sentence number %d. " * 3 + "\n") % (1,2,3) * 40, encoding="utf-8")
    json.dump({"work.txt": {"tier": "P1"}}, open(adv / "sources" / "manifest.json", "w", encoding="utf-8"))
    chunks = pipeline.build(str(adv), config={"chunk": {"target": 300, "overlap": 50}}, built_at="2026-06-25T00:00:00Z")
    assert len(chunks) > 0 and all(c["tier"] == "P1" for c in chunks)
    on_disk = [json.loads(l) for l in open(paths.corpus_path(str(adv)), encoding="utf-8") if l.strip()]
    assert len(on_disk) == len(chunks)
    assert os.path.isfile(paths.lock_path(str(adv)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/pipeline.py
"""Оркестратор сборки: ingest → clean → chunk по всем источникам → build/corpus.jsonl + lock."""
import os, json
from . import ingest, clean, chunk as chunkmod, buildlock, paths

SUPPORTED = (".txt", ".md", ".pdf", ".epub")


def build(advisor_dir: str, config=None, built_at: str = "unknown"):
    config = config or {}
    chunk_cfg = config.get("chunk", {})
    src_dir = os.path.join(advisor_dir, "sources")
    all_chunks = []
    for fn in sorted(os.listdir(src_dir)):
        if os.path.splitext(fn)[1].lower() not in SUPPORTED:
            continue
        recs = ingest.extract_source(os.path.join(src_dir, fn))
        tagged = clean.tag_regions(recs, fn, advisor_dir)
        all_chunks.extend(chunkmod.chunk_records(tagged, fn, chunk_cfg))
    os.makedirs(paths.build_dir(advisor_dir), exist_ok=True)
    out = os.path.join(paths.build_dir(advisor_dir), "corpus.jsonl")  # пишем ВСЕГДА в build/
    with open(out, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    buildlock.write_lock(advisor_dir, config, all_chunks, built_at)
    return all_chunks  # corpus_path() теперь автоматически отдаёт build/corpus.jsonl
```

```python
# scripts/corpus_build.py
#!/usr/bin/env python3
"""CLI сборщика корпуса. build по умолчанию; --report — только доктор."""
import sys, os, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from corpus import pipeline, doctor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("advisor_dir")
    ap.add_argument("--report", action="store_true", help="только валидационный доктор")
    args = ap.parse_args()
    if args.report:
        doctor.report(args.advisor_dir); return
    built_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    chunks = pipeline.build(args.advisor_dir, built_at=built_at)
    print(f"собрано чанков: {len(chunks)} → {args.advisor_dir}/build/corpus.jsonl")
    doctor.report(args.advisor_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_pipeline.py -v`
Expected: PASS (1 passed). (CLI-импорт `doctor` появится в Task 9 — до него `corpus_build.py` не запускать; тест pipeline от CLI не зависит.)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/pipeline.py scripts/corpus_build.py tests/test_corpus_pipeline.py
git commit -m "corpus: оркестратор build (ingest→clean→chunk→build/corpus.jsonl+lock)"
```

---

### Task 8: Миграция читателей на резолвер

**Files:**
- Modify: `scripts/tier_full.py` (`_read_corpus_chunks`, ~line 76 — `path = os.path.join(advisor_dir, "corpus.jsonl")`)
- Modify: `scripts/engine/fidelity.py` (~line 16)
- Modify: `scripts/engine/lexical.py` (~line 25)
- Modify: `scripts/eval.py` (~lines 97, 171)
- Modify: `scripts/board_init.py` (~line 24)
- Modify: `scripts/gen_golden.py` (~line 21), `scripts/exp_kernels.py` (~line 34)
- Test: `tests/test_reader_migration.py`

Каждый читатель заменяет литерал `os.path.join(advisor_dir, "corpus.jsonl")` (или `f"{adv}/corpus.jsonl"`) на `corpus.paths.corpus_path(advisor_dir)`. Везде добавить импорт-хелпер.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reader_migration.py
import re, glob, os
def test_no_raw_corpus_jsonl_literals():
    bad = []
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "scripts", "**", "*.py"), recursive=True):
        if os.path.basename(f) in ("paths.py", "pipeline.py"):  # резолвер/писатель — можно
            continue
        src = open(f, encoding="utf-8").read()
        if re.search(r'["\']corpus\.jsonl["\']', src) and "corpus_path" not in src:
            bad.append(os.path.relpath(f))
    assert not bad, f"эти файлы читают corpus.jsonl мимо резолвера: {bad}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_reader_migration.py -v`
Expected: FAIL — список из ~6 файлов.

- [ ] **Step 3: Write minimal implementation**

В каждом файле из списка: добавь в начало (после существующих sys.path-вставок) импорт
```python
from corpus.paths import corpus_path
```
(для `engine/*.py`, где пакет — `scripts`, используй `from corpus.paths import corpus_path` при наличии `scripts` в sys.path; если нет — добавь `import sys, os; sys.path.insert(0, <scripts>)` рядом с существующими вставками файла, копируя его текущий паттерн).

Затем замени литерал на вызов:
- `tier_full.py`: `path = corpus_path(advisor_dir)`
- `engine/fidelity.py`: `path = corpus_path(advisor_dir)`
- `engine/lexical.py`: `cj = corpus_path(advisor_dir)`
- `eval.py` (оба места): `cj = corpus_path(adv_dir)`
- `board_init.py`: `cj = corpus_path(adv_dir)`
- `gen_golden.py`: `open(corpus_path(adv), ...)` ; `exp_kernels.py`: то же.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_reader_migration.py tests/ -v`
Expected: PASS. Дополнительно: `python3 -m pytest tests/ -v` — весь существующий сьют зелёный (35+ тестов).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "corpus: все читатели корпуса через единый резолвер corpus_path"
```

---

### Task 9: Tier-aware семантический индекс

**Files:**
- Modify: `scripts/tier_full.py` (`_read_corpus_chunks` — прокинуть `tier`; `build_index` — meta passages с `tier`)
- Test: `tests/test_index_tier.py`

`_read_corpus_chunks` сейчас отдаёт пассажи с `text`/`source`. Добавить `tier` (из чанка `rec.get("tier")`, дефолт через `provenance.tier_for`). Тогда `meta.json` passages несут тир → ретрив может фильтровать/маркировать.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_index_tier.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tier_full

def test_read_chunks_carries_tier(tmp_path, monkeypatch):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    rows = [{"source": "p.txt", "tier": "P1", "text": "Power is held by appearances. " * 5},
            {"source": "t.txt", "tier": "S1", "text": "Тарасов толкует это так. " * 5}]
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    passages = tier_full._read_corpus_chunks(str(adv))
    assert any(p.get("tier") == "S1" for p in passages)
    assert all("tier" in p for p in passages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_index_tier.py -v`
Expected: FAIL — у пассажей нет ключа `tier`.

- [ ] **Step 3: Write minimal implementation**

В `tier_full._read_corpus_chunks`: при нарезке чанка на пассажи копировать `tier = rec.get("tier")`; если None — `tier = provenance.tier_for(rec.get("source",""), 0, advisor_dir)`. Каждый собираемый пассаж-словарь получает `"tier": tier`. В `build_index` ничего не меняем (passages уже несут tier; они целиком уходят в meta.json).

Добавить вверху `tier_full.py`: `from engine import provenance` (рядом с прочими импортами; если `engine` не в пути — использовать существующий паттерн sys.path этого файла).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_index_tier.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/tier_full.py tests/test_index_tier.py
git commit -m "tier_full: пассажи семантического индекса несут tier"
```

---

### Task 10: Доктор корпуса (`corpus/doctor.py`)

**Files:**
- Create: `scripts/corpus/doctor.py`
- Test: `tests/test_corpus_doctor.py`

Гейт: распределение тиров; флаг неразмеченного (тир `A`); инвариант рва — ни один S1/S2/B/A-чанк не должен попасть в lexical-пул как 🔵-eligible (проверяем, что fidelity-гейт его не пометит 🔵 — это Task 11; здесь печатаем и возвращаем структуру с `ok`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_doctor.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpus import doctor

def _corpus(adv, rows):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_doctor_flags_unlabeled_A(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "x", "tier": "A", "text": "?"}, {"source": "y", "tier": "P1", "text": "ok"}])
    rep = doctor.report(adv)
    assert rep["tiers"]["A"] == 1
    assert rep["ok"] is False  # неразмеченное (A) валит гейт

def test_doctor_ok_when_all_labeled(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "y", "tier": "P1", "text": "ok"}, {"source": "z", "tier": "S1", "text": "comm"}])
    rep = doctor.report(adv)
    assert rep["ok"] is True and rep["tiers"] == {"P1": 1, "S1": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_corpus_doctor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'corpus.doctor'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/corpus/doctor.py
"""Валидационный гейт корпуса: распределение тиров, флаг неразмеченного (A), инварианты рва."""
import json
from collections import Counter
from . import paths


def report(advisor_dir: str) -> dict:
    path = paths.corpus_path(advisor_dir)
    chunks = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    tiers = dict(Counter(c.get("tier", "A") for c in chunks))
    unlabeled = tiers.get("A", 0)
    ok = unlabeled == 0 and len(chunks) > 0
    print(f"[доктор] {advisor_dir}: чанков {len(chunks)}, тиры {tiers}")
    if unlabeled:
        print(f"  ⚠️  {unlabeled} чанков с тиром A (неразмечено/fail-closed) — разметь источник в манифесте")
    print(f"  {'✓ OK' if ok else '✗ ГЕЙТ НЕ ПРОЙДЕН'}")
    return {"ok": ok, "tiers": tiers, "chunks": len(chunks), "unlabeled": unlabeled}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_corpus_doctor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/doctor.py tests/test_corpus_doctor.py
git commit -m "corpus: доктор-гейт (тиры, флаг неразмеченного A)"
```

---

### Task 11: Tier-aware fidelity (гейт мисатрибуции)

**Files:**
- Modify: `scripts/engine/fidelity.py` (читатель корпуса уже через `corpus_path` после Task 8; добавить тир-логику)
- Test: `tests/test_fidelity_tiers.py`

Цитата, поданная голосом советника, получает 🔵 ТОЛЬКО если дословный матч в P1/P2-чанке. Матч только в S1/S2/B/A → НЕ 🔵 (мисатрибуция). Реализуем функцию `tier_of_match(quote, advisor_dir)` → тир чанка, где найден дословный матч (или None).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fidelity_tiers.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import fidelity

def _corpus(adv, rows):
    os.makedirs(os.path.join(adv, "build"), exist_ok=True)
    with open(os.path.join(adv, "build", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def test_quote_in_p1_is_blue_eligible(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "prince.txt", "tier": "P1", "text": "it is safer to be feared than loved"}])
    assert fidelity.tier_of_match("safer to be feared than loved", adv) == "P1"

def test_quote_only_in_s1_is_misattribution(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "tarasov.txt", "tier": "S1", "text": "Тарасов пишет: власть держится на страхе"}])
    assert fidelity.tier_of_match("власть держится на страхе", adv) == "S1"
    assert fidelity.is_blue_eligible("власть держится на страхе", adv) is False

def test_quote_absent_returns_none(tmp_path):
    adv = str(tmp_path)
    _corpus(adv, [{"source": "p.txt", "tier": "P1", "text": "something else entirely"}])
    assert fidelity.tier_of_match("nonexistent phrase", adv) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fidelity_tiers.py -v`
Expected: FAIL — `AttributeError: module 'engine.fidelity' has no attribute 'tier_of_match'`

- [ ] **Step 3: Write minimal implementation**

В `scripts/engine/fidelity.py` добавь (используя существующий нормализатор и чтение корпуса этого файла; если приватная функция чтения называется иначе — переиспользуй её):

```python
def _iter_chunks(advisor_dir):
    import json
    from corpus.paths import corpus_path
    for line in open(corpus_path(advisor_dir), encoding="utf-8"):
        line = line.strip()
        if line:
            yield json.loads(line)


def _norm(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def tier_of_match(quote: str, advisor_dir: str):
    """Тир чанка, где дословно (по нормализации) найдена цитата; None если нигде.
    Приоритет P1/P2 (если матч в нескольких тирах — отдаём самый авторитетный)."""
    q = _norm(quote)
    if not q:
        return None
    order = {"P1": 0, "P2": 1, "S1": 2, "S2": 3, "B": 4, "A": 5}
    best = None
    for ch in _iter_chunks(advisor_dir):
        if q in _norm(ch.get("text", "")):
            t = ch.get("tier", "A")
            if best is None or order.get(t, 9) < order.get(best, 9):
                best = t
    return best


def is_blue_eligible(quote: str, advisor_dir: str) -> bool:
    """🔵 (голосом советника) допустимо только при дословном матче в P1/P2."""
    return tier_of_match(quote, advisor_dir) in ("P1", "P2")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_fidelity_tiers.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/engine/fidelity.py tests/test_fidelity_tiers.py
git commit -m "fidelity: tier-aware гейт — 🔵 только P1/P2, S→блок мисатрибуции"
```

---

### Task 12: Реальная пересборка советников + чистка фронт-маттера

**Files:**
- Modify: `advisors/marcus-aurelius/sources/manifest.json` (создать с regions для интро переводчика)
- Modify: `advisors/machiavelli/sources/manifest.json` (добавить regions, если у Prince/Discourses есть интро)
- Test: ручная проверка через доктор (нет авто-теста — данные gitignored)

- [ ] **Step 1: Создать манифест Аврелия с регионами**

```json
// advisors/marcus-aurelius/sources/manifest.json
{
  "meditations-long-gutenberg.txt": {
    "tier": "P1", "attribution": "Marcus Aurelius", "translator": "George Long",
    "lang": "en", "license": "public-domain",
    "regions": [
      {"tier": "B", "until": "THE FIRST BOOK"},
      {"tier": "P1", "from": "THE FIRST BOOK"}
    ]
  }
}
```

- [ ] **Step 2: Пересобрать обоих советников**

Run:
```bash
python3 scripts/corpus_build.py advisors/marcus-aurelius
python3 scripts/corpus_build.py advisors/machiavelli
```
Expected: доктор печатает распределение тиров; у Аврелия появляется ~7-8% тира **B** (интро Лонга больше не P1); у Макиавелли — P1 (Prince+Discourses) + S1 (Тарасов).

- [ ] **Step 3: Пересобрать семантические индексы**

Run:
```bash
python3 scripts/tier_full.py advisors/marcus-aurelius
python3 scripts/tier_full.py advisors/machiavelli
```
Expected: индексы пересобраны из `build/corpus.jsonl`, meta-пассажи несут tier.

- [ ] **Step 4: Прогнать весь сьют + доктор**

Run: `python3 -m pytest tests/ -v && python3 scripts/corpus_build.py advisors/marcus-aurelius --report`
Expected: все тесты зелёные; доктор Аврелия — `ok: True` или флаг A=0 (если что-то в A — поправить regions).

- [ ] **Step 5: Commit** (только машинерия; advisors/ gitignored — манифесты НЕ коммитятся, они под `advisors/*`)

```bash
git add -A
git commit -m "corpus: пересборка Аврелия/Макиавелли на новом билдере (фронт-маттер→B, Тарасов→S1)"
```

> ВАЖНО: `advisors/*` в .gitignore (кроме README). Манифесты и build/ НЕ уйдут в репо — это ок (user-data). Коммит затронет только tracked-машинерию, если она менялась.

---

## Self-Review

**Spec coverage** (против `2026-06-25-corpus-builder-design.md`):
- §1 стадии 1-4,8: Tasks 3 (ingest), 4 (clean), 5 (chunk), 9 (index) ✓
- §2 data model (чанк с tier): Tasks 5, 7 ✓
- §3 пер-регионные тиры: Task 2 ✓
- §4 build.lock: Task 6 ✓
- §5 доктор: Tasks 10 (+ инвариант 🔵 в Task 11) ✓
- §6 связь с кодом (резолвер, fidelity tier, пути): Tasks 1, 8, 9, 11 ✓
- §7 CLI: Task 7 ✓
- §8 P0 без shortcut (build/ реорг): Tasks 1, 8 ✓
- §9 риск «чистка ломает корпус» (доктор печатает): Task 10 + ручная проверка Task 12 ✓
- **GAP:** инкрементальный кэш стадий (§1 «пересобирается только изменённое») — НЕ в P0-плане. Решение: вынесено в P1 (см. ниже), т.к. требует stage-version + сравнение хешей lock; P0 даёт полную (быструю) пересборку. Это YAGNI до появления тяжёлых стадий (enrich).
- **GAP (намеренно P1):** стадии 5 (enrich), 6 (link/graph), 7 (kernels-в-билдере) — отдельный план после P0.

**Placeholder scan:** Task 7 содержит НАМЕРЕННЫЙ анти-пример (артефакт-`with`) с явной пометкой удалить — это не плейсхолдер, а обучающий маркер «писать всегда в build/». Прочих плейсхолдеров нет.

**Type consistency:** чанк = `{source, tier, start, end, text}` един в Tasks 5/7/9/10/11. `tier_for`(плоский)/`tier_for_line`(регионный) — обе в Task 2, используются в Tasks 4/9. `corpus_path(advisor_dir)` — сигнатура едина (Tasks 1, 8, 9, 11). `report()→dict{ok,tiers,chunks,unlabeled}` (Task 10) и `tier_of_match`/`is_blue_eligible` (Task 11) согласованы с тестами.
