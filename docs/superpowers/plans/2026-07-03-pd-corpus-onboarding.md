# PD-онбординг корпуса — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Чужой человек в любом MCP-агенте называет PD-мыслителя → видит превью-карточку издания → подтверждает → его машина собирает советника локально из общественного достояния.

**Architecture:** Каталог указателей (`catalog/pd_figures.json`, ноль текста) + чистый модуль `scripts/catalog.py` (load/validate/подпись/превью/оркестрация с инъекцией fetch+build → оффлайн-тесты) + 5 тонких stateless MCP-хендлеров в `mcp_server.py` + CLI `catalog_verify.py`. Логика в сервере (агент-агностично); корпус собирается и живёт локально (`advisors/*`, gitignored); verbatim-ров цел (детерминированный strip, ноль ручной правки).

**Tech Stack:** Python 3 stdlib (json, hashlib, urllib через `collect_common`); реюз `collect_common`, `corpusbuild.apparatus`, `corpusbuild.pipeline`, `collect_pd.strip_gutenberg`; pytest оффлайн (мок fetch/build).

**Спека:** `docs/superpowers/specs/2026-07-03-pd-corpus-onboarding-design.md`.

**Инвариант CI (каждый прогон тестов):** `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` — ноль сети, ноль движка. Все сетевые вызовы в тестах — через инъектированный мок `fetch`.

---

## File Structure

- **Create `scripts/catalog.py`** — чистая логика: `load_catalog`, `validate_catalog`, `get_figure`, `strip_for_signature`, `text_sha256`, `verify_signature`, `build_preview`, `preview_source(fetch=…)`, `add_from_catalog(fetch=…, build=…)`, `search_gutenberg(fetch=…)`. Сеть/сборка — только через инъектируемые callables (дефолт — реальные).
- **Create `catalog/pd_figures.json`** — данные каталога (указатели). MVP: Марк Аврелий, Эпиктет, Сунь-Цзы (Giles), плюс место под расширение. `expected.sha256` посевается Task 8.
- **Create `scripts/catalog_verify.py`** — CLI: обход каталога, сверка подписи/PD-basis (`--seed` пишет sha256).
- **Modify `scripts/mcp_server.py`** — 5 тонких хендлеров (`_catalog_list/_catalog_search/_catalog_preview/_catalog_add/_catalog_verify`) + 5 записей `TOOLS` + хук в `INSTRUCTIONS`.
- **Modify `install.py`** — включить `catalog/` в RUNTIME.
- **Tests:** `tests/test_catalog.py` (чистая логика), `tests/test_catalog_tools.py` (хендлеры с мок-fetch/build), `tests/test_catalog_verify.py`.

---

## Task 1: Каталог — схема, загрузка, валидация

**Files:**
- Create: `scripts/catalog.py`
- Create: `catalog/pd_figures.json`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog.py
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import catalog

def _write_catalog(root, figures):
    os.makedirs(os.path.join(root, "catalog"), exist_ok=True)
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "figures": figures}, f, ensure_ascii=False)

def test_load_and_validate_good_catalog():
    with tempfile.TemporaryDirectory() as root:
        _write_catalog(root, [{
            "id": "marcus-aurelius", "name": "Марк Аврелий", "seat": "стоик",
            "lang": "en",
            "source": {"platform": "gutenberg", "ref": "2680",
                       "edition": "пер. George Long, 1862",
                       "url": "https://www.gutenberg.org/cache/epub/2680/pg2680.txt",
                       "pd_basis": "Project Gutenberg (US-PD)"}}])
        data = catalog.load_catalog(root)
        assert catalog.validate_catalog(data) == []
        assert catalog.get_figure(data, "marcus-aurelius")["name"] == "Марк Аврелий"
        assert catalog.get_figure(data, "nope") is None

def test_validate_rejects_bad_entries():
    bad = {"version": 1, "figures": [
        {"id": "x"},                                   # нет name/source
        {"id": "y", "name": "Y", "source": {"platform": "randomsite", "url": "http://x"}},  # не-PD платформа
    ]}
    errs = catalog.validate_catalog(bad)
    assert any("source" in e for e in errs)
    assert any("платформа" in e for e in errs)

def test_load_missing_catalog_is_empty_failclosed():
    with tempfile.TemporaryDirectory() as root:
        data = catalog.load_catalog(root)          # файла нет
        assert data == {"version": 1, "figures": []}
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_catalog.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'catalog'`).

- [ ] **Step 3: Минимальная реализация**

```python
# scripts/catalog.py
"""Каталог PD-фигур (указатели, ноль текста) + оркестрация сборки советника из общественного
достояния. Сеть/сборка инъектируются (fetch=/build=) → всё оффлайн-тестируемо. Логика в сервере,
хост только предлагает и рисует. Firewall: каталог = указатели, корпус — локально в advisors/*."""
import os, json, hashlib

ALLOWED_PLATFORMS = {"gutenberg", "standardebooks", "wikisource"}


def load_catalog(root):
    """Читает <root>/catalog/pd_figures.json. Нет файла → пустой каталог (fail-closed, не падение)."""
    p = os.path.join(root, "catalog", "pd_figures.json")
    if not os.path.exists(p):
        return {"version": 1, "figures": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def validate_catalog(data):
    """→ список человеческих ошибок ([] = валиден). Fail-closed: кривая запись глушит фигуру."""
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get("figures"), list):
        return ["каталог: нет списка figures"]
    seen = set()
    for i, fig in enumerate(data["figures"]):
        tag = fig.get("id", f"#{i}")
        if not fig.get("id") or not fig.get("name"):
            errs.append(f"{tag}: нет id или name")
        if fig.get("id") in seen:
            errs.append(f"{tag}: дублирующийся id")
        seen.add(fig.get("id"))
        src = fig.get("source")
        if not isinstance(src, dict) or not src.get("url"):
            errs.append(f"{tag}: нет source.url")
            continue
        if src.get("platform") not in ALLOWED_PLATFORMS:
            errs.append(f"{tag}: платформа '{src.get('platform')}' не в whitelist {sorted(ALLOWED_PLATFORMS)}")
    return errs


def get_figure(data, fid):
    for fig in data.get("figures", []):
        if fig.get("id") == fid:
            return fig
    return None
```

Создать `catalog/pd_figures.json`:

```json
{
  "version": 1,
  "figures": [
    {
      "id": "marcus-aurelius", "name": "Марк Аврелий", "seat": "стоик / этика решений", "lang": "en",
      "source": {"platform": "gutenberg", "ref": "2680", "edition": "пер. George Long, 1862",
                 "url": "https://www.gutenberg.org/cache/epub/2680/pg2680.txt",
                 "pd_basis": "Project Gutenberg (US-PD)"}
    },
    {
      "id": "epictetus", "name": "Эпиктет", "seat": "стоик / контроль контролируемого", "lang": "en",
      "source": {"platform": "gutenberg", "ref": "45109", "edition": "Enchiridion, пер. Long",
                 "url": "https://www.gutenberg.org/cache/epub/45109/pg45109.txt",
                 "pd_basis": "Project Gutenberg (US-PD)"}
    },
    {
      "id": "sun-tzu", "name": "Сунь-Цзы", "seat": "стратег / конфликт", "lang": "en",
      "source": {"platform": "gutenberg", "ref": "132", "edition": "The Art of War, пер. Lionel Giles 1910",
                 "url": "https://www.gutenberg.org/cache/epub/132/pg132.txt",
                 "pd_basis": "Project Gutenberg (US-PD)"}
    }
  ]
}
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python3 -m pytest tests/test_catalog.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Коммит**

```bash
git add scripts/catalog.py catalog/pd_figures.json tests/test_catalog.py
git commit -m "feat(catalog): схема PD-каталога + load/validate/get (fail-closed, platform-whitelist)"
```

---

## Task 2: Подпись текста (детерминированная, для fail-closed на дрейфе)

**Files:**
- Modify: `scripts/catalog.py`
- Test: `tests/test_catalog.py`

Подпись считается по тексту ПОСЛЕ `strip_gutenberg` (детерминированный regex, стабилен пока Gutenberg не переиздал). Полный apparatus-tier — это дело сборки (Task 6), НЕ подписи, иначе эвристики дают нестабильный хэш.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog.py  (добавить)
def test_strip_and_signature_deterministic():
    raw = ("*** START OF THE PROJECT GUTENBERG EBOOK X ***\n"
           "Настоящий текст произведения.\n"
           "*** END OF THE PROJECT GUTENBERG EBOOK X ***\n")
    stripped = catalog.strip_for_signature(raw)
    assert "PROJECT GUTENBERG" not in stripped
    assert "Настоящий текст" in stripped
    sha = catalog.text_sha256(stripped)
    assert sha == catalog.text_sha256(catalog.strip_for_signature(raw))   # детерминизм

def test_verify_signature_failclosed_on_drift():
    stripped = "abc"
    ok, actual, _ = catalog.verify_signature(stripped, {"sha256": catalog.text_sha256("abc")})
    assert ok
    ok2, _, reason = catalog.verify_signature(stripped, {"sha256": "deadbeef"})
    assert not ok2 and "подпись" in reason.lower()

def test_verify_signature_absent_expected_warns_not_fails():
    ok, actual, reason = catalog.verify_signature("abc", None)
    assert ok and "не посеяна" in reason.lower()   # bootstrap: нет expected → строим, но помечаем
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_catalog.py -q`
Expected: FAIL (`AttributeError: module 'catalog' has no attribute 'strip_for_signature'`).

- [ ] **Step 3: Реализация (добавить в scripts/catalog.py)**

```python
def strip_for_signature(raw):
    """Текст ПОСЛЕ снятия Gutenberg-обёртки — детерминированная основа подписи и сборки."""
    import collect_pd
    return collect_pd.strip_gutenberg(raw).strip()


def text_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_signature(stripped, expected):
    """→ (ok, actual_sha, reason). expected None → bootstrap (ok, но помечаем «не посеяна»).
    Есть expected.sha256 и не сошлось → fail-closed (текст уплыл — не собираем молча)."""
    actual = text_sha256(stripped)
    if not expected or not expected.get("sha256"):
        return True, actual, "подпись не посеяна (bootstrap) — прогони catalog_verify --seed"
    if actual != expected["sha256"]:
        return False, actual, "подпись не сошлась: издание на источнике изменилось (fail-closed)"
    return True, actual, "ok"
```

- [ ] **Step 4: Запустить — PASS**

Run: `python3 -m pytest tests/test_catalog.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add scripts/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): детерминированная подпись (strip_gutenberg→sha256) + verify fail-closed на дрейфе"
```

---

## Task 3: Превью-объект (render-agnostic, с OCR-warn)

**Files:**
- Modify: `scripts/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog.py (добавить)
def test_build_preview_shape_and_ocr_warn():
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Ясный текст. " * 40) + \
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    pv = catalog.build_preview(name="Марк Аврелий", edition="Long 1862",
                               pd_basis="PG (US-PD)", url="https://www.gutenberg.org/x", raw=raw)
    assert pv["kind"] == "pd_preview"
    assert pv["figure"] == "Марк Аврелий" and pv["pd_basis"] == "PG (US-PD)"
    assert "PROJECT GUTENBERG" not in pv["sample"]
    assert pv["bytes"] > 0 and len(pv["sha256"]) == 64
    assert pv["pd_host_ok"] is True
    assert pv["warnings"] == []

def test_build_preview_flags_ocr_noise_and_nonpd_host():
    noisy = "@#$%^&*<>|~`" * 60 + " a"
    pv = catalog.build_preview(name="X", edition="e", pd_basis="?",
                               url="http://randomsite.example/x", raw=noisy)
    assert pv["pd_host_ok"] is False
    assert any("шум" in w.lower() or "качество" in w.lower() for w in pv["warnings"])
```

- [ ] **Step 2: Запустить — FAIL** (`no attribute 'build_preview'`).

Run: `python3 -m pytest tests/test_catalog.py -q`

- [ ] **Step 3: Реализация (добавить в scripts/catalog.py)**

```python
def _ocr_noise_ratio(text):
    if not text:
        return 1.0
    junk = sum(1 for c in text if not (c.isalnum() or c.isspace() or c in ".,;:!?—-–'\"()«»"))
    return junk / len(text)


def build_preview(*, name, edition, pd_basis, url, raw):
    """Render-agnostic превью-объект: один dict → адаптеры рендера (Cowork-виджет/текст/чужой агент)."""
    import collect_common as cc
    stripped = strip_for_signature(raw)
    sample = stripped[:400]
    warnings = []
    ratio = _ocr_noise_ratio(stripped[:2000])
    if ratio > 0.15:
        warnings.append(f"возможен OCR-шум/низкое качество (доля не-текст. символов {ratio:.0%})")
    pd_ok = cc.is_pd_host(url)
    if not pd_ok:
        warnings.append("хост не в PD-whitelist — потребуется явный license=public-domain")
    return {
        "kind": "pd_preview", "figure": name, "edition": edition, "pd_basis": pd_basis,
        "bytes": len(stripped.encode("utf-8")), "sha256": text_sha256(stripped),
        "sample": sample, "pd_host_ok": pd_ok, "warnings": warnings,
        "confirm_hint": "Собрать советника локально из этого издания?",
    }
```

- [ ] **Step 4: Запустить — PASS.**

Run: `python3 -m pytest tests/test_catalog.py -q`

- [ ] **Step 5: Коммит**

```bash
git add scripts/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): render-agnostic превью-объект (sample+подпись+PD-host+OCR-warn)"
```

---

## Task 4: Оркестрация preview/add/search (инъекция fetch+build)

**Files:**
- Modify: `scripts/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog.py (добавить)
GUT = "https://www.gutenberg.org/cache/epub/2680/pg2680.txt"
PD_RAW = ("*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Мысль. " * 50) +
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n")

def _catalog_root():
    import tempfile
    root = tempfile.mkdtemp()
    _write_catalog(root, [{"id": "marcus-aurelius", "name": "Марк Аврелий", "seat": "стоик",
        "source": {"platform": "gutenberg", "ref": "2680", "edition": "Long 1862",
                   "url": GUT, "pd_basis": "PG (US-PD)"}}])
    return root

def test_preview_source_by_id_uses_injected_fetch():
    root = _catalog_root()
    pv = catalog.preview_source("marcus-aurelius", root=root, fetch=lambda url, **k: PD_RAW)
    assert pv["kind"] == "pd_preview" and pv["figure"] == "Марк Аврелий"

def test_add_from_catalog_verifies_sig_and_builds():
    root = _catalog_root()
    # посеять expected.sha256, чтобы verify прошёл
    expected_sha = catalog.text_sha256(catalog.strip_for_signature(PD_RAW))
    data = catalog.load_catalog(root); data["figures"][0]["source"]["expected"] = {"sha256": expected_sha}
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    built = {}
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW,
                                   build=lambda adv_dir, **k: built.setdefault("dir", adv_dir))
    assert res["ok"] and res["advisor"].endswith("marcus-aurelius")
    assert built["dir"].endswith("marcus-aurelius")   # сборка вызвана

def test_add_from_catalog_failclosed_on_signature_drift():
    root = _catalog_root()
    data = catalog.load_catalog(root); data["figures"][0]["source"]["expected"] = {"sha256": "deadbeef"}
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    res = catalog.add_from_catalog("marcus-aurelius", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW, build=lambda *a, **k: None)
    assert not res["ok"] and "подпись" in res["error"].lower()

def test_add_nonpd_url_requires_license():
    root = _catalog_root()
    res = catalog.add_from_catalog("http://randomsite.example/book.txt", root=root, license=None,
                                   fetch=lambda url, **k: PD_RAW, build=lambda *a, **k: None)
    assert not res["ok"] and "license" in res["error"].lower()
```

- [ ] **Step 2: Запустить — FAIL** (`no attribute 'preview_source'`).

Run: `python3 -m pytest tests/test_catalog.py -q`

- [ ] **Step 3: Реализация (добавить в scripts/catalog.py)**

```python
def _resolve_ref(ref, root):
    """id из каталога → (name, edition, pd_basis, url, expected); голый url → минимальная запись."""
    if ref.startswith("http://") or ref.startswith("https://"):
        return {"name": ref, "edition": "", "pd_basis": "", "url": ref, "expected": None}
    fig = get_figure(load_catalog(root), ref)
    if not fig:
        return None
    s = fig["source"]
    return {"name": fig["name"], "edition": s.get("edition", ""), "pd_basis": s.get("pd_basis", ""),
            "url": s["url"], "expected": s.get("expected")}


def preview_source(ref, *, root, fetch):
    r = _resolve_ref(ref, root)
    if r is None:
        return {"error": f"нет фигуры '{ref}' в каталоге"}
    raw = _decode(fetch(r["url"]))
    return build_preview(name=r["name"], edition=r["edition"], pd_basis=r["pd_basis"],
                         url=r["url"], raw=raw)


def add_from_catalog(ref, *, root, license, fetch, build):
    """Мутирующий: fetch → strip → verify подпись (fail-closed) → land → build. Rule 0 (согласие) —
    на уровне хоста (превью-карточка перед вызовом). Собирает в <root>/advisors/<id> локально."""
    import collect_common as cc
    r = _resolve_ref(ref, root)
    if r is None:
        return {"ok": False, "error": f"нет фигуры '{ref}' в каталоге"}
    if not cc.is_pd_host(r["url"]) and license != "public-domain":
        return {"ok": False, "error": "не-PD хост требует license=public-domain (подтверди PD-статус сам)"}
    raw = _decode(fetch(r["url"]))
    stripped = strip_for_signature(raw)
    ok, actual, reason = verify_signature(stripped, r["expected"])
    if not ok:
        return {"ok": False, "error": reason, "actual_sha256": actual}
    fid = ref if not ref.startswith("http") else cc.slugify(r["name"])
    adv_dir = os.path.join(root, "advisors", fid)
    os.makedirs(os.path.join(adv_dir, "sources"), exist_ok=True)
    cc.land_to_sources(adv_dir, fid, stripped, url=r["url"],
                       license_note=r["pd_basis"] or "public-domain")
    build(adv_dir, built_at=cc.today())
    return {"ok": True, "advisor": adv_dir, "sha256": actual, "note": reason}


def _decode(raw):
    return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")


def search_gutenberg(author, *, fetch):
    """Кандидаты-издания из gutendex.com (JSON API PG). Хвост вне каталога. Оффлайн → error, не краш."""
    url = "https://gutendex.com/books?search=" + author.replace(" ", "%20")
    try:
        data = json.loads(_decode(fetch(url)))
    except Exception as e:
        return {"ok": False, "error": f"поиск недоступен (оффлайн?): {e}", "candidates": []}
    out = []
    for b in data.get("results", [])[:8]:
        txt = next((v for k, v in (b.get("formats") or {}).items()
                    if "text/plain" in k and v.endswith(".txt")), None)
        if txt:
            out.append({"gutenberg_id": b.get("id"), "title": b.get("title"),
                        "authors": [a.get("name") for a in b.get("authors", [])],
                        "url": txt, "pd_basis": "Project Gutenberg (US-PD)"})
    return {"ok": True, "candidates": out}
```

- [ ] **Step 4: Запустить — PASS** (все тесты test_catalog.py).

Run: `python3 -m pytest tests/test_catalog.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add scripts/catalog.py tests/test_catalog.py
git commit -m "feat(catalog): оркестрация preview/add/search (DI fetch+build, verify fail-closed, non-PD gate)"
```

---

## Task 5: MCP-хендлеры + записи TOOLS + диспатч

**Files:**
- Modify: `scripts/mcp_server.py` (хендлеры рядом с `_add_source`; записи в `TOOLS` dict, ~1281)
- Test: `tests/test_catalog_tools.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog_tools.py
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server

def test_catalog_list_tool_registered_and_returns_figures(monkeypatch):
    assert "catalog_list" in mcp_server.TOOLS
    out = mcp_server.dispatch("catalog_list", {})
    assert isinstance(out.get("figures"), list)
    assert any(f["id"] == "marcus-aurelius" for f in out["figures"])

def test_catalog_preview_tool_uses_fetch(monkeypatch):
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nТекст.\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: raw)
    out = mcp_server.dispatch("catalog_preview", {"ref": "marcus-aurelius"})
    assert out["kind"] == "pd_preview" and out["figure"] == "Марк Аврелий"

def test_catalog_search_tool(monkeypatch):
    gutendex = json.dumps({"results": [{"id": 3800, "title": "Ethics", "authors": [{"name": "Spinoza"}],
        "formats": {"text/plain; charset=utf-8": "https://www.gutenberg.org/files/3800/3800-0.txt"}}]})
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: gutendex)
    out = mcp_server.dispatch("catalog_search", {"author": "Spinoza"})
    assert out["ok"] and out["candidates"][0]["gutenberg_id"] == 3800
```

- [ ] **Step 2: Запустить — FAIL** (`catalog_list` не в TOOLS).

Run: `python3 -m pytest tests/test_catalog_tools.py -q`

- [ ] **Step 3: Реализация — добавить хендлеры (в scripts/mcp_server.py, рядом с _add_source)**

```python
def _catalog_list():
    import catalog
    data = catalog.load_catalog(_root())
    errs = catalog.validate_catalog(data)
    figs = [{"id": f["id"], "name": f["name"], "seat": f.get("seat", ""),
             "edition": f["source"].get("edition", ""), "pd_basis": f["source"].get("pd_basis", "")}
            for f in data.get("figures", []) if f.get("id") not in
            {e.split(":")[0] for e in errs}]                      # fail-closed: битую фигуру не показываем
    return {"figures": figs, "catalog_errors": errs}

def _catalog_search(author):
    import catalog, collect_common as cc
    return catalog.search_gutenberg(author, fetch=cc.fetch)

def _catalog_preview(ref):
    import catalog, collect_common as cc
    return catalog.preview_source(ref, root=_root(), fetch=cc.fetch)

def _catalog_add(ref, license=None):
    import catalog, collect_common as cc
    from corpusbuild import pipeline
    return catalog.add_from_catalog(ref, root=_root(), license=license, fetch=cc.fetch,
                                    build=lambda adv_dir, **k: pipeline.build(adv_dir, **k))

def _catalog_verify():
    import catalog, collect_common as cc
    return catalog.verify_catalog(_root(), fetch=cc.fetch)      # реализуется в Task 7
```

Добавить в `TOOLS` dict (после записи `add_source`):

```python
    "catalog_list": {
        "description": "Список PD-фигур каталога (общественное достояние) — id/имя/место/издание/PD-basis. "
                       "Без фетча. Чужой выбирает, кого собрать в совет.",
        "input_schema": _obj({}, []),
        "handler": _catalog_list,
    },
    "catalog_search": {
        "description": "Поиск PD-издания фигуры ВНЕ каталога (Gutenberg через gutendex). Возвращает "
                       "кандидатов с PD-basis. Оффлайн → честная ошибка.",
        "input_schema": _obj({"author": "string"}, ["author"]),
        "handler": _catalog_search,
    },
    "catalog_preview": {
        "description": "Превью PD-издания перед сборкой: сэмпл текста + подпись + PD-host + warnings. "
                       "НЕ собирает. Это consent-карточка — покажи юзеру ПЕРЕД catalog_add. ref = id "
                       "каталога ИЛИ прямой url.",
        "input_schema": _obj({"ref": "string"}, ["ref"]),
        "handler": _catalog_preview,
    },
    "catalog_add": {
        "description": "Собрать PD-советника ЛОКАЛЬНО из каталога/url. ПОДТВЕРДИ у юзера (Rule 0) — "
                       "покажи catalog_preview первым. Fetch→сверка подписи (fail-closed на дрейфе)→"
                       "сборка в advisors/<id>. Не-PD хост требует license=public-domain.",
        "input_schema": _obj({"ref": "string", "license": "string"}, ["ref"]),
        "handler": _catalog_add,
    },
    "catalog_verify": {
        "description": "Ритуал целостности каталога (как moat-check): обойти записи, сверить подпись/"
                       "PD-basis, репортить дрейф. Без сборки.",
        "input_schema": _obj({}, []),
        "handler": _catalog_verify,
    },
```

- [ ] **Step 4: Запустить — PASS.** (test_catalog_verify реализуется в Task 7; пока `_catalog_verify` сошлётся на несуществующую функцию — временно вернуть заглушку `return {"ok": True, "checked": 0}` в `_catalog_add`? Нет — `verify_catalog` нужна. Порядок: реализуй `verify_catalog` в Task 7 ПОСЛЕ; здесь `_catalog_verify` не тестируется, а `catalog.verify_catalog` ещё нет → импорт ленивый, тест на verify не запускается тут.)

Run: `python3 -m pytest tests/test_catalog_tools.py -q`
Expected: PASS (3 passed — list/preview/search; verify не трогаем).

- [ ] **Step 5: Коммит**

```bash
git add scripts/mcp_server.py tests/test_catalog_tools.py
git commit -m "feat(catalog): 5 stateless MCP-тулов (list/search/preview/add/verify) + записи TOOLS"
```

---

## Task 6: catalog_add — интеграция сборки (реальный pipeline.build на мок-fetch)

**Files:**
- Test: `tests/test_catalog_tools.py`

Проверяем, что `catalog_add` реально прогоняет `corpusbuild.pipeline.build` и получает собранный корпус — на инъектированном мок-fetch (сеть не трогаем), реальный build в tmp-advisors.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog_tools.py (добавить)
def test_catalog_add_builds_real_corpus_offline(tmp_path, monkeypatch):
    # каталог в tmp с посеянной подписью
    import catalog
    raw = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\n" + ("Добродетель есть знание. " * 60) + \
          "\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"
    sha = catalog.text_sha256(catalog.strip_for_signature(raw))
    (tmp_path / "catalog").mkdir()
    (tmp_path / "catalog" / "pd_figures.json").write_text(json.dumps({"version": 1, "figures": [
        {"id": "epictetus", "name": "Эпиктет", "seat": "стоик",
         "source": {"platform": "gutenberg", "ref": "45109", "edition": "e",
                    "url": "https://www.gutenberg.org/cache/epub/45109/pg45109.txt",
                    "pd_basis": "PG (US-PD)", "expected": {"sha256": sha}}}]}, ensure_ascii=False),
        encoding="utf-8")
    monkeypatch.setattr("mcp_server._root", lambda: str(tmp_path))
    monkeypatch.setattr("collect_common.fetch", lambda url, **k: raw)
    out = mcp_server.dispatch("catalog_add", {"ref": "epictetus"})
    assert out["ok"]
    assert (tmp_path / "advisors" / "epictetus" / "build" / "corpus.jsonl").exists()
```

- [ ] **Step 2: Запустить — FAIL** (нет собранного corpus.jsonl / путь `_root` мока).

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_catalog_tools.py::test_catalog_add_builds_real_corpus_offline -q`

- [ ] **Step 3: Реализация**

Если тест падает из-за сигнатуры `pipeline.build(advisor_dir, config=None, built_at="unknown")` — `_catalog_add` уже передаёт `build=lambda adv_dir, **k: pipeline.build(adv_dir, **k)` и `add_from_catalog` зовёт `build(adv_dir, built_at=cc.today())`. Убедиться, что `pipeline.build` пишет `build/corpus.jsonl` в SIMPLE-тире без сети (он это делает: no-manifest→tier A, лексический). Если `build` требует `config`, передать `config=None` (дефолт). Никакого нового кода — тест верифицирует интеграцию; правь только если сигнатура-мисматч.

- [ ] **Step 4: Запустить — PASS.**

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/test_catalog_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add tests/test_catalog_tools.py scripts/mcp_server.py scripts/catalog.py
git commit -m "test(catalog): catalog_add строит реальный corpus.jsonl оффлайн (мок-fetch, tmp-advisors)"
```

---

## Task 7: catalog_verify + CLI + `--seed`

**Files:**
- Modify: `scripts/catalog.py` (функция `verify_catalog`)
- Create: `scripts/catalog_verify.py` (CLI)
- Test: `tests/test_catalog_verify.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog_verify.py
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import catalog

def _root_with(fig):
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "catalog"))
    with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "figures": [fig]}, f, ensure_ascii=False)
    return root

RAW = "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nТекст произведения.\n*** END OF THE PROJECT GUTENBERG EBOOK X ***\n"

def test_verify_reports_ok_when_signature_matches():
    sha = catalog.text_sha256(catalog.strip_for_signature(RAW))
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG", "expected": {"sha256": sha}}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW)
    assert rep["ok"] and rep["entries"][0]["status"] == "ok"

def test_verify_flags_drift():
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG", "expected": {"sha256": "deadbeef"}}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW)
    assert not rep["ok"] and rep["entries"][0]["status"] == "drift"

def test_seed_writes_signatures():
    root = _root_with({"id": "m", "name": "M", "source": {"platform": "gutenberg", "url": "https://www.gutenberg.org/x",
                       "pd_basis": "PG"}})
    rep = catalog.verify_catalog(root, fetch=lambda url, **k: RAW, seed=True)
    data = catalog.load_catalog(root)
    assert data["figures"][0]["source"]["expected"]["sha256"] == catalog.text_sha256(catalog.strip_for_signature(RAW))
```

- [ ] **Step 2: Запустить — FAIL** (`no attribute 'verify_catalog'`).

Run: `python3 -m pytest tests/test_catalog_verify.py -q`

- [ ] **Step 3: Реализация — `verify_catalog` в scripts/catalog.py**

```python
def verify_catalog(root, *, fetch, seed=False):
    """Обойти каталог: fetch → strip → сверить подпись/PD-basis. seed=True → записать sha256 в записи.
    → {ok, entries:[{id, status: ok|drift|unseeded|error, ...}]}. Ритуал целостности (как moat-check)."""
    data = load_catalog(root)
    entries, all_ok = [], True
    changed = False
    for fig in data.get("figures", []):
        src = fig.get("source", {})
        try:
            stripped = strip_for_signature(_decode(fetch(src["url"])))
        except Exception as e:
            entries.append({"id": fig.get("id"), "status": "error", "detail": str(e)}); all_ok = False
            continue
        actual = text_sha256(stripped)
        if seed:
            src["expected"] = {"sha256": actual, "bytes": len(stripped.encode("utf-8"))}
            changed = True
            entries.append({"id": fig.get("id"), "status": "seeded", "sha256": actual})
            continue
        exp = src.get("expected", {}).get("sha256")
        if not exp:
            entries.append({"id": fig.get("id"), "status": "unseeded"}); all_ok = False
        elif exp != actual:
            entries.append({"id": fig.get("id"), "status": "drift", "expected": exp, "actual": actual})
            all_ok = False
        else:
            entries.append({"id": fig.get("id"), "status": "ok"})
    if changed:
        with open(os.path.join(root, "catalog", "pd_figures.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return {"ok": all_ok, "entries": entries}
```

Создать `scripts/catalog_verify.py`:

```python
#!/usr/bin/env python3
"""catalog_verify.py — ритуал целостности PD-каталога. Обходит записи, сверяет подпись/PD-basis.
  python scripts/catalog_verify.py            # проверить (fail на дрейфе → exit 1)
  python scripts/catalog_verify.py --seed     # посеять/обновить sha256 (нужна сеть)"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog, collect_common as cc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true", help="записать sha256 в каждую запись (нужна сеть)")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(__file__), ".."))
    a = ap.parse_args()
    rep = catalog.verify_catalog(os.path.abspath(a.root), fetch=cc.fetch, seed=a.seed)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    sys.exit(0 if rep["ok"] else 1)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Запустить — PASS** (test_catalog_verify.py + весь набор).

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: PASS (весь сьют зелёный).

- [ ] **Step 5: Коммит**

```bash
git add scripts/catalog.py scripts/catalog_verify.py tests/test_catalog_verify.py
git commit -m "feat(catalog): verify_catalog + CLI (--seed) — ритуал целостности каталога (fail-closed на дрейфе)"
```

---

## Task 8: Посеять подписи в шипуемый каталог (maintainer, сеть — вне CI)

**Files:**
- Modify: `catalog/pd_figures.json`

⚠️ Единственный шаг с сетью — выполняется мейнтейнером локально, НЕ в CI.

- [ ] **Step 1: Посеять**

Run: `python3 scripts/catalog_verify.py --seed`
Expected: печатает `{"ok": true, "entries": [{"status": "seeded", ...} ×3]}`; `catalog/pd_figures.json` получает `expected.sha256` на каждую запись.

- [ ] **Step 2: Проверить**

Run: `python3 scripts/catalog_verify.py`
Expected: `{"ok": true, "entries": [{"status": "ok"} ×3]}`, exit 0.

- [ ] **Step 3: Коммит**

```bash
git add catalog/pd_figures.json
git commit -m "chore(catalog): посеять подписи 3 стартовых PD-фигур (Марк Аврелий/Эпиктет/Сунь-Цзы)"
```

---

## Task 9: install.py — включить catalog/ в RUNTIME

**Files:**
- Modify: `install.py` (список RUNTIME)
- Test: `tests/test_catalog_tools.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog_tools.py (добавить)
def test_install_ships_catalog():
    import install
    assert any("catalog" in str(x) for x in install.RUNTIME), "catalog/ не в RUNTIME install.py"
```

- [ ] **Step 2: Запустить — FAIL.**

Run: `python3 -m pytest tests/test_catalog_tools.py::test_install_ships_catalog -q`

- [ ] **Step 3: Реализация — добавить `"catalog"` в список RUNTIME в install.py**

Найти список RUNTIME (рядом с `"lenses"`, `"gov_heads.json"`) и добавить элемент `"catalog"`.

- [ ] **Step 4: Запустить — PASS.**

Run: `python3 -m pytest tests/test_catalog_tools.py -q`

- [ ] **Step 5: Коммит**

```bash
git add install.py tests/test_catalog_tools.py
git commit -m "feat(install): шипуем catalog/ (указатели PD-фигур) в RUNTIME"
```

---

## Task 10: INSTRUCTIONS-хук (хост предлагает PD-сборку)

**Files:**
- Modify: `scripts/mcp_server.py` (блок `INSTRUCTIONS`)

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_catalog_tools.py (добавить)
def test_instructions_mention_catalog_flow():
    assert "catalog_preview" in mcp_server.INSTRUCTIONS
    assert "catalog_add" in mcp_server.INSTRUCTIONS
    # порядок consent: превью ПЕРЕД сборкой
    assert mcp_server.INSTRUCTIONS.index("catalog_preview") < mcp_server.INSTRUCTIONS.index("catalog_add")
```

- [ ] **Step 2: Запустить — FAIL.**

Run: `python3 -m pytest tests/test_catalog_tools.py::test_instructions_mention_catalog_flow -q`

- [ ] **Step 3: Реализация — добавить абзац в INSTRUCTIONS (после правила про seed_council/пустую доску)**

```
ПУСТАЯ ДОСКА / МАЛО СОВЕТНИКОВ: предложи собрать из общественного достояния. Покажи catalog_list →
юзер называет фигуру → catalog_preview(ref) (карточка: издание, PD-basis, сэмпл, warnings) → ПОКАЖИ
её и спроси согласие → ТОЛЬКО потом catalog_add(ref) (собирает локально, Rule 0). Фигуры вне каталога:
catalog_search(автор) → выбери издание → preview → add(url, license=public-domain). Никогда не собирай
без показанного превью. Текст никуда не отправляется — сборка на машине юзера, корпус локальный.
```

- [ ] **Step 4: Запустить — PASS** (весь сьют).

Run: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
Expected: PASS (весь сьют зелёный).

- [ ] **Step 5: Коммит**

```bash
git add scripts/mcp_server.py tests/test_catalog_tools.py
git commit -m "feat(instructions): хук PD-онбординга (превью→согласие→сборка, catalog_search для хвоста)"
```

---

## Финальная верификация (после всех задач)

- [ ] Оффлайн-сьют зелёный: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q`
- [ ] Firewall: `sh scripts/firewall_check.sh` → OK (каталог = указатели, ноль приватных имён/текста).
- [ ] Ручной smoke (сеть, локально): `python3 scripts/catalog_verify.py` → все ok; собрать фигуру через CLI-эквивалент и проверить `advisors/<id>/build/corpus.jsonl`.
- [ ] Адверсариальное ревью всей ветки перед мержем (правило дуги Moat v2).
