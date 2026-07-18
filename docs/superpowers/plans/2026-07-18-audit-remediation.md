# Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the fact-verified findings of the 2026-07-18 external audit (6 critical + 12 high + ~20 medium + low), in priority order, without breaking the offline invariant (1636 passed / 1 skipped) or the fidelity moat.

**Architecture:** Six phases by risk/value: (0) release-blocker leak guard; (1) mass-path mechanical crash+perf; (2) moat-semantics refinement (design-gated); (3) security/correctness; (4) doc-honesty (owner-gated wording); (5) medium/low verify-first backlog. Every code fix is TDD. Every commit is owner-gated (firewall) — the executor STOPS and asks before each commit; NEVER `git add -A`; NEVER push/merge without explicit owner go.

**Tech Stack:** Python 3 stdlib core (numpy only for semantic tier), pytest, ollama/bge-m3 (gated), mcpb packaging.

**Invariants the executor must hold (from CLAUDE.md + firewall):**
- Offline invariant after every phase: `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` → must stay green (currently 1636 passed / 1 skipped).
- env-touching tests use `monkeypatch`; never leave vars in `os.environ`.
- private advisor slugs NEVER in code/tests/docs/bundle — tests use synthetic corpora.
- after adding any new tool/script/test file that changes counts: `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py` else freshness guards fail.
- commit ONLY on explicit owner "go", explicit paths only, with trailers:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01Fzv2bNsXHGuYfacFPp2tFe`.

**Triage note (why these and not the auditor's exact remedies):**
- **C2's proposed remedy is WRONG for the design.** `fidelity_check` is an INTENTIONALLY host-callable protocol-gate (mcp_server.py:6-10). 🔵 asserts *provenance* (words are verbatim in P1/P2), not relevance. The real danger is the substring crop (C1); fix C1 and C2's bite closes. Do NOT gate 🔵 behind cite/gate_verdict only — that breaks the host protocol.
- **C1 has a genuine tradeoff** (sentence-boundary matching would reject legitimate sub-sentence quotes like "the unexamined life"). Phase 2 opens with a DESIGN DECISION gate — do not code C1 before the owner picks the rule.

---

## File Structure

- `.mcpbignore` (new) — bundle exclusion list; the ONLY thing standing between `mcpb pack` and a public leak of `.env`/copyright/private data.
- `scripts/ci_bundle_guard.py` (new) — asserts a simulated bundle file list contains none of the forbidden paths; run in CI + referenced from runbook.
- `scripts/session_render.py` — `render_md` / `render_html` synthesis-section guards (C3).
- `scripts/llm_local.py` — thread `num_predict` + `allow_cloud` through `generate`/`_raw_generate*` (C4, H4).
- `scripts/relevance_judge.py` — pass `num_predict=4`, keep judge local by default (C4, H4).
- `scripts/engine/fidelity.py` — mtime-cached normalized chunks (C5), word threshold (H2), sentence-boundary rule (C1), single `marker_status()` (H6).
- `scripts/mcp_server.py` — `_fidelity_check` delegates to engine (H6); read-side traversal guard (H5).
- `scripts/engine/__init__.py` — `Engine.fidelity_check` delegates to engine `marker_status()` (H6).
- `scripts/engine/lexical.py` — mtime-cached `_split_units` (H10).
- `tests/test_eval.py` (new) — cover the harness proving the main claim (H9).
- `docs/dev/mcp-registry-publish-runbook.md` — add `.mcpbignore` + guard step (C6).
- README / SKILL.md / MANUAL.md / GLOSSARY.md / CHANGELOG.md — honesty edits (H1/H3/H11/H12, owner-gated).

---

## PHASE 0 — C6 release-blocker (do first, unambiguous)

### Task 0.1: `.mcpbignore` excludes all private/secret/copyright paths

**Files:**
- Create: `.mcpbignore`
- Reference: `.gitignore` (source of the forbidden set), `docs/dev/mcp-registry-publish-runbook.md`

- [ ] **Step 1: Write the failing test** (guard script drives this — see Task 0.2; write `.mcpbignore` first as data)

Create `.mcpbignore` with every private/secret/copyright path. mcpb uses gitignore-style globs but does NOT read `.gitignore`:

```
# СЕКРЕТЫ
.env
*.log
# КОПИРАЙТНЫЕ ИСХОДНИКИ И СОБРАННЫЕ КОРПУСА (никогда в public-бандл)
reference-library-raw/
reference-library/
*-raw/
advisors/*/build/
advisors/*/sources/
advisors/*/corpus.jsonl
advisors/*/corpus.lock.json
lenses/*/build/
lenses/*/sources/
# ЛИЧНЫЕ ДАННЫЕ ЮЗЕРА
principis.md
relationship.md
principis_corpus/
council/
decisions/
consults/
board_config.json
gov_heads.local.json
.consilium/
# ЛОКАЛЬНЫЕ АРТЕФАКТЫ СБОРКИ
data/embeddings*.npy
data/embeddings*.meta.json
scripts/golden/
mcp.json
# СЛУЖЕБНОЕ
.git/
__pycache__/
*.pyc
.venv/
venv/
.DS_Store
tests/fixtures/
```

Note: the PD advisors that SHIP (machiavelli/marcus-aurelius/sun-tzu built from PD) are handled by the guard's allowlist logic in 0.2 — here we exclude the raw+build layers universally; if a PD advisor must ship its corpus, add an explicit `!advisors/<pd-name>/corpus.jsonl` line ONLY after the guard confirms it is PD.

- [ ] **Step 2: Manually verify globs** — `python3 -c "import pathlib; print(pathlib.Path('.mcpbignore').read_text())"` and confirm every gitignored private path is represented.

- [ ] **Step 3: Commit** (owner go) — `git add .mcpbignore` + trailers.

### Task 0.2: CI bundle-content guard (fails if a forbidden path would be packed)

**Files:**
- Create: `scripts/ci_bundle_guard.py`
- Create: `tests/test_bundle_guard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bundle_guard.py
import subprocess, sys, os, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_guard_rejects_forbidden(tmp_path):
    # simulate a packed file list containing .env → guard must exit nonzero
    listing = tmp_path / "files.txt"
    listing.write_text(".env\nSKILL.md\nadvisors/some-advisor/build/corpus.jsonl\n")  # synthetic slug — private slugs NEVER in code/tests
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert ".env" in r.stdout or ".env" in r.stderr

def test_guard_allows_clean(tmp_path):
    listing = tmp_path / "files.txt"
    listing.write_text("SKILL.md\nscripts/mcp_server.py\nmanifest.json\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails** — `pytest tests/test_bundle_guard.py -v` → FAIL (script missing).

- [ ] **Step 3: Implement `scripts/ci_bundle_guard.py`**

```python
#!/usr/bin/env python3
"""Fail-closed guard: given a file listing (one path per line) that WOULD be packed
into the .mcpb bundle, exit nonzero if any forbidden (private/secret/copyright) path
appears. Runbook step 2b + CI. Не читает сеть, ноль зависимостей."""
import sys, re, fnmatch

FORBIDDEN = [
    ".env", "*.log", "mcp.json", "board_config.json", "gov_heads.local.json",
    "principis.md", "relationship.md",
    "reference-library-raw/*", "reference-library/*", "*-raw/*",
    "principis_corpus/*", "council/*", "decisions/*", "consults/*", ".consilium/*",
    # ВСЕ корпуса/исходники советников (private И PD) — path-based, БЕЗ списка слагов,
    # чтобы приватные имена НЕ попали в этот коммитимый скрипт. PD-советник, который ДОЛЖЕН
    # shipнуть corpus, добавляется явным allow ниже по ПУБЛИЧНОМУ имени.
    "advisors/*/build/*", "advisors/*/sources/*", "advisors/*/corpus.jsonl", "advisors/*/corpus.lock.json",
    "lenses/*/build/*", "lenses/*/sources/*",
    "data/embeddings*.npy", "data/embeddings*.meta.json", "scripts/golden/*",
]
# PD-советники, которым разрешено shipнуть corpus (публичные имена, безопасно называть):
ALLOW = ["advisors/machiavelli/corpus.jsonl", "advisors/marcus-aurelius/corpus.jsonl",
         "advisors/sun-tzu/corpus.jsonl"]

def offending(paths):
    bad = []
    for p in paths:
        p = p.strip().lstrip("./")
        if not p or p in ALLOW:
            continue
        if any(fnmatch.fnmatch(p, pat) for pat in FORBIDDEN):
            bad.append(p)
    return bad

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "-"
    lines = (open(src, encoding="utf-8") if src != "-" else sys.stdin).read().splitlines()
    bad = offending(lines)
    if bad:
        print("BUNDLE GUARD FAIL — forbidden paths would be packed:", *bad, sep="\n  ")
        sys.exit(1)
    print("bundle-guard: OK")
```

- [ ] **Step 4: Run test to verify it passes** — `pytest tests/test_bundle_guard.py -v` → PASS.

- [ ] **Step 5: Regen selfdoc** (new script + test files) — `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py`.

- [ ] **Step 6: Wire into runbook** — add after the `mcpb pack` step in `docs/dev/mcp-registry-publish-runbook.md`:

```markdown
### 2b. Гард содержимого бандла (ОБЯЗАТЕЛЬНО до Release)
```bash
unzip -Z1 consilium-principis.mcpb | python3 scripts/ci_bundle_guard.py -
# ожидается: bundle-guard: OK. Любой forbidden путь → СТОП, не публиковать.
```
```

- [ ] **Step 7: Offline invariant** — `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q` → green.

- [ ] **Step 8: Commit** (owner go) — `git add scripts/ci_bundle_guard.py tests/test_bundle_guard.py docs/dev/mcp-registry-publish-runbook.md selfdoc/ MANUAL.md` + trailers.

---

## PHASE 1 — mass-path mechanical (safe, testable, no claim change)

### Task 1.1: C3 — guard synthesis section in `render_md` / `render_html`

**Files:**
- Modify: `scripts/session_render.py:148` (`render_md`), `:497` (`render_html`)
- Test: `tests/test_session_render.py` (append)

- [ ] **Step 1: Write the failing test**

```python
def test_render_md_no_synthesis_no_keyerror():
    from session_render import render_md, render_html
    round_table = {"question": "Q?", "opinions": [], "abstentions": []}  # no 'synthesis'
    md = render_md(round_table)      # must not raise KeyError
    html = render_html(round_table)  # must not raise KeyError
    assert "Синтез" not in md
    assert "Синтез" not in html
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/test_session_render.py -k no_synthesis -v` → FAIL KeyError 'synthesis'.

- [ ] **Step 3: Implement — make synthesis conditional (mirror render_widget line 367).**

`render_md` (was line 148):
```python
    if s.get("synthesis"):
        out += ["", "## Синтез", _e(s["synthesis"])]
```
`render_html` (was line 497):
```python
    if s.get("synthesis"):
        body.append(f'<section class=synth><h3>Синтез</h3><p>{_e(s["synthesis"])}</p>'
                    + (f'<p class=lose><em>Чем платишь: {_e(s["what_you_lose"])}</em></p>'
                       if s.get("what_you_lose") else "") + "</section>")
```

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_session_render.py -v` → PASS.

- [ ] **Step 5: Commit** (owner go) — `git add scripts/session_render.py tests/test_session_render.py` + trailers.

### Task 1.2: C4 — cap judge generation with `num_predict` (thread through llm_local)

**Files:**
- Modify: `scripts/llm_local.py` (`generate`, `_raw_generate`, `_raw_generate_openrouter`)
- Modify: `scripts/relevance_judge.py:111`
- Test: `tests/test_llm_local.py` (append or create)

- [ ] **Step 1: Write the failing test**

```python
def test_generate_passes_num_predict(monkeypatch):
    import llm_local
    captured = {}
    def fake_raw(prompt, model, temperature, timeout, num_predict=None):
        captured["num_predict"] = num_predict
        return "2"
    monkeypatch.setattr(llm_local, "_raw_generate", fake_raw)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    llm_local.generate("p", model="m", temperature=0.1, num_predict=4)
    assert captured["num_predict"] == 4
```

- [ ] **Step 2: Run to verify it fails** — FAIL (generate has no num_predict param).

- [ ] **Step 3: Implement — thread `num_predict` through.**

`_raw_generate`:
```python
def _raw_generate(prompt, model, temperature, timeout, num_predict=None):
    opts = {"temperature": temperature}
    if num_predict is not None:
        opts["num_predict"] = num_predict
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": opts}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()).get("response", "")
```
`_raw_generate_openrouter` — add `num_predict=None` param, and `if num_predict is not None: body["max_tokens"] = num_predict` (build dict then dumps).
`generate` signature → `def generate(prompt, model=None, temperature=0.3, timeout=120, num_predict=None, allow_cloud=True):` and pass `num_predict` into both raw calls. (`allow_cloud` added in Task 3.2 — include the param now with default True to avoid a second signature churn.)

- [ ] **Step 4: relevance_judge line 111** →
```python
    response = llm_local.generate(prompt, model=model, temperature=0.1, num_predict=4, allow_cloud=False)
```
(`allow_cloud=False` keeps the judge local — see Task 3.2.)

- [ ] **Step 5: Run to verify it passes** — `pytest tests/test_llm_local.py -v` → PASS.

- [ ] **Step 6: Offline invariant** → green.

- [ ] **Step 7: Commit** (owner go) — explicit paths + trailers.

### Task 1.3: C5 + H10 — mtime-cache normalized corpus chunks and lexical units

**Files:**
- Modify: `scripts/engine/fidelity.py` (`_iter_chunks` / `_corpus_norm_text`)
- Modify: `scripts/engine/lexical.py` (`_split_units`)
- Test: `tests/test_fidelity_cache.py` (new)

- [ ] **Step 1: Write the failing test**

```python
def test_corpus_norm_text_cached_by_mtime(tmp_path, monkeypatch):
    import engine.fidelity as F
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    corp = adv / "build" / "corpus.jsonl"
    corp.write_text('{"text":"the quick brown fox jumps","tier":"P1"}\n', encoding="utf-8")
    calls = {"n": 0}
    real_open = open
    import builtins
    def counting_open(*a, **k):
        if a and str(a[0]).endswith("corpus.jsonl"): calls["n"] += 1
        return real_open(*a, **k)
    monkeypatch.setattr(builtins, "open", counting_open)
    F._corpus_norm_text(str(adv)); F._corpus_norm_text(str(adv))
    assert calls["n"] == 1                      # second call served from cache
    corp.write_text('{"text":"a new sentence entirely","tier":"P1"}\n', encoding="utf-8")
    import os as _os; _os.utime(corp, (9e9, 9e9))  # bump mtime
    F._corpus_norm_text(str(adv))
    assert calls["n"] == 2                       # mtime change → re-read
```

- [ ] **Step 2: Run to verify it fails** — FAIL (no cache, calls["n"]==2 on first assert).

- [ ] **Step 3: Implement mtime cache in fidelity.py** (module-level dict keyed by `(path, mtime)`):

```python
_NORM_CACHE = {}   # (path, mtime) -> list[(src, norm_chunk)]

def _corpus_norm_text(advisor_dir):
    path = corpus_path(advisor_dir)
    if not os.path.isfile(path):
        return []
    key = (path, os.path.getmtime(path))
    hit = _NORM_CACHE.get(key)
    if hit is not None:
        return hit
    chunks = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try: rec = json.loads(line)
            except Exception: continue
            chunks.append((str(rec.get("source") or rec.get("citation") or "corpus.jsonl"),
                           _norm(rec.get("text") or "")))
    _NORM_CACHE[key] = chunks
    return chunks
```
Rewrite `best_match` to iterate the cached, tier-aware structure. Add a tier-carrying cache `_CHUNK_CACHE[(path,mtime)] -> list[dict]` for `_iter_chunks` consumers (best_match needs tier), OR extend `_corpus_norm_text` tuples to `(src, norm, tier)` and have `best_match` use it. Keep ONE cache; `_iter_chunks` becomes a thin wrapper yielding from the cached list.

- [ ] **Step 4: Same pattern in `lexical.py` `_split_units`** — module dict `_UNITS_CACHE[(path, mtime)]`.

- [ ] **Step 5: Run to verify it passes** + offline invariant green.

- [ ] **Step 6: Commit** (owner go) — explicit paths + trailers.

### Task 1.4: H6 — one `marker_status()`; both call sites delegate

**Files:**
- Modify: `scripts/engine/fidelity.py` (add `marker_status`)
- Modify: `scripts/engine/__init__.py:76-89` (`Engine.fidelity_check` delegates)
- Modify: `scripts/mcp_server.py:63-73` (`_fidelity_check` delegates)
- Test: `tests/test_marker_status_single_source.py` (new)

- [ ] **Step 1: Write the failing test**

```python
def test_marker_status_is_single_source(tmp_path):
    from engine.fidelity import marker_status
    adv = tmp_path / "adv"; (adv/"build").mkdir(parents=True)
    (adv/"build"/"corpus.jsonl").write_text(
        '{"text":"fortune favors the bold indeed","tier":"P1"}\n', encoding="utf-8")
    r = marker_status("fortune favors the bold indeed", str(adv))
    assert r["status"] == "🔵" and r["verbatim"] is True
    assert marker_status("nope not present here", str(adv))["status"] == "🟡"
```

- [ ] **Step 2: Run to verify it fails** — FAIL (marker_status missing).

- [ ] **Step 3: Implement `marker_status` in fidelity.py**:
```python
def marker_status(quote: str, advisor_dir: str) -> dict:
    """Единственный источник маркера по тиру дословного матча (P1/P2→🔵, S1/S2→🟢, иначе 🟡)."""
    m = best_match(quote, advisor_dir)
    if not m:
        return {"status": "🟡", "verbatim": False, "source": ""}
    tier, src = m
    if tier in ("P1", "P2"): return {"status": "🔵", "verbatim": True, "source": src}
    if tier in ("S1", "S2"): return {"status": "🟢", "verbatim": True, "source": src}
    return {"status": "🟡", "verbatim": False, "source": ""}
```
`mcp_server._fidelity_check` → `from engine.fidelity import marker_status; return marker_status(quote, _resolve(advisor_dir))`.
`Engine.fidelity_check` → build `FidelityResult(**marker_status(quote, advisor_dir))`.

- [ ] **Step 4: Run to verify it passes** + offline invariant green (existing fidelity tests must still pass — this is behavior-preserving).

- [ ] **Step 5: Commit** (owner go).

---

## PHASE 2 — moat semantics (DESIGN-GATED — do not code before owner picks the rule)

### Task 2.0: DESIGN DECISION gate (owner) — how strict is verbatim?

Present to owner, wait for choice (this changes what earns 🔵 and requires re-emitting calibration fixtures):
- **Option A (recommended): word threshold + negation-crop guard.** Keep substring, but (H2) require `len(quote.split()) >= 3` AND reject a match whose normalized span begins or ends immediately adjacent to a negation token (`not|no|never|n't|не|ни|нет`) that is present in the source sentence but dropped by the crop. Least disruptive; kills "remember" and "only to do but".
- **Option B: sentence-boundary.** 🔵 only if the quote spans whole sentences (bounded by `.?!;`/corpus edge on both sides). Strongest, but rejects legitimate sub-sentence quotes.
- **Option C: doc-only.** Don't change the gate; fix the README claim to "verbatim substring modulo punctuation/case" (H1) and accept crops.

Do NOT proceed to 2.1/2.2 until the owner picks. Below assumes **Option A**.

### Task 2.1: H2 — word-count threshold (≥3 words) for 🔵/🟢 eligibility

**Files:** Modify `scripts/engine/fidelity.py:15,69,102`; Test `tests/test_fidelity_threshold.py` (new)

- [ ] **Step 1: Failing test**
```python
def test_single_word_not_blue(tmp_path):
    from engine.fidelity import best_match
    adv = tmp_path/"adv"; (adv/"build").mkdir(parents=True)
    (adv/"build"/"corpus.jsonl").write_text('{"text":"remember your mortality daily","tier":"P1"}\n', encoding="utf-8")
    assert best_match("remember", str(adv)) is None          # one word → not 🔵
    assert best_match("remember your mortality", str(adv)) is not None  # ≥3 words → ok
```
- [ ] **Step 2: Verify fail.**
- [ ] **Step 3: Implement** — replace char-based short-circuit with word-based:
```python
MIN_QUOTE_WORDS = 3
# in best_match / verbatim_in_corpus:
q = _norm(quote)
if len(q.split()) < MIN_QUOTE_WORDS:
    return None
```
Keep `MIN_QUOTE_CHARS` removed or subsumed. Update the docstring comment at line 13-14.
- [ ] **Step 4: Verify pass** + offline invariant.
- [ ] **Step 5: Re-emit calibration fixtures if any 🔵 count shifted** — `HEPHAESTUS_ENGINE=... OLLAMA_HOST=... python3 scripts/eval.py --emit-scores > tests/fixtures/scores/<advisor>.semantic.json` for affected advisors ONLY if a golden test now fails; commit fixture change separately with the reason.
- [ ] **Step 6: Commit** (owner go).

### Task 2.2: C1 — negation-crop guard (Option A)

**Files:** Modify `scripts/engine/fidelity.py` (`best_match` match test); Test `tests/test_fidelity_negation_crop.py` (new)

- [ ] **Step 1: Failing test** (reproduces the audit's "only to do but" case)
```python
def test_negation_crop_not_blue(tmp_path):
    from engine.fidelity import best_match
    adv = tmp_path/"adv"; (adv/"build").mkdir(parents=True)
    (adv/"build"/"corpus.jsonl").write_text(
        '{"text":"it is not only to do but to be that matters","tier":"P1"}\n', encoding="utf-8")
    # crop that drops the leading negation flips meaning → must NOT be 🔵
    assert best_match("only to do but to be", str(adv)) is None
    # honest full-context quote keeps 🔵
    assert best_match("not only to do but to be", str(adv)) is not None
```
- [ ] **Step 2: Verify fail.**
- [ ] **Step 3: Implement** — in the match loop, after finding `q in norm_chunk`, reject if the char immediately preceding the match position in the chunk is a word char AND the token immediately before the match is a negation token (meaning the crop severed a negation). Concrete helper:
```python
_NEG = {"not", "no", "never", "nt", "не", "ни", "нет"}
def _crop_severs_negation(q, chunk):
    i = chunk.find(q)
    if i <= 0:
        return False
    prefix = chunk[:i].split()
    return bool(prefix) and prefix[-1] in _NEG
```
Use it: `if q in ct and not _crop_severs_negation(q, ct):` before accepting a match.
- [ ] **Step 4: Verify pass** + offline invariant + existing fidelity tests green.
- [ ] **Step 5: Commit** (owner go).

### Task 2.3: H1 — README honesty on "word-for-word"

Owner-gated wording (see Phase 4 Task 4.1) — the code now matches the claim modulo punctuation/case; state that explicitly.

---

## PHASE 3 — security / correctness

### Task 3.1: H5 — read-side path-traversal guard on advisor_dir

**Files:** Modify `scripts/mcp_server.py` read paths that call `_resolve(advisor_dir)`; Test `tests/test_read_traversal.py` (new)

- [ ] **Step 1: Failing test**
```python
def test_read_tool_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    monkeypatch.setattr(srv, "_root", lambda: str(tmp_path))
    # a read tool given advisor_dir escaping root must fail-closed (🟡 / error), not read /etc
    out = srv._fidelity_check("some quote here", "../../../../etc")
    assert out["status"] == "🟡"   # nothing read outside root
```
- [ ] **Step 2: Verify fail** (currently `_resolve` allows escape).
- [ ] **Step 3: Implement** — add a read-guard: `_resolve_read(p)` = `_resolve_under_root` semantics but returns the root-clamped path or `None`; read tools that accept `advisor_dir` resolve via it and treat `None` as "no corpus" (🟡 / empty). Apply to `_fidelity_check` and other advisor_dir readers (`_advisor_dirs` is internal/safe; focus on host-arg entry points: `_fidelity_check`, `_cite`, cross-attribution readers).
- [ ] **Step 4: Verify pass** + offline invariant.
- [ ] **Step 5: Commit** (owner go).

### Task 3.2: H4 — keep the relevance judge local unless explicitly allowed cloud

**Files:** Modify `scripts/llm_local.py` (`generate` honors `allow_cloud`); `scripts/relevance_judge.py` already passes `allow_cloud=False` (Task 1.2); Test `tests/test_judge_local_default.py` (new)

- [ ] **Step 1: Failing test**
```python
def test_judge_stays_local_even_with_openrouter(monkeypatch):
    import llm_local
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    hit = {"cloud": False, "local": False}
    monkeypatch.setattr(llm_local, "_raw_generate_openrouter", lambda *a, **k: hit.__setitem__("cloud", True) or "2")
    monkeypatch.setattr(llm_local, "_raw_generate", lambda *a, **k: hit.__setitem__("local", True) or "2")
    llm_local.generate("p", model="m", temperature=0.1, allow_cloud=False)
    assert hit["local"] and not hit["cloud"]
```
- [ ] **Step 2: Verify fail** (currently routes to cloud on LLM_BACKEND).
- [ ] **Step 3: Implement** — in `generate`, gate the openrouter branch on `allow_cloud and os.getenv("LLM_BACKEND",...)=="openrouter"`. Default `allow_cloud=True` preserves generator behavior; judge passes `False`. Optionally honor `JUDGE_LLM_BACKEND` for an explicit opt-in in relevance_judge.
- [ ] **Step 4: Verify pass** + offline invariant.
- [ ] **Step 5: Commit** (owner go).

### Task 3.3: H8 — numpy-optional test collection

**Files:** Modify `tests/test_index_fingerprint.py` (+ any test importing numpy transitively); CI: add no-numpy leg.

- [ ] **Step 1: Reproduce** — `python3 -c "import tier_full"` in an env without numpy; confirm ImportError at collection.
- [ ] **Step 2: Implement** — top of numpy-dependent tests: `np = pytest.importorskip("numpy")`; guard the semantic-tier import behind it. Ensure the pure-stdlib offline invariant collects with numpy absent.
- [ ] **Step 3: CI leg** — add a job step `pip install pytest` (no numpy) then run the offline invariant; expect skips, not collection errors.
- [ ] **Step 4: Verify** offline invariant green both with and without numpy.
- [ ] **Step 5: Commit** (owner go).

### Task 3.4: H9 — tests for the claim-proving harness

**Files:** Create `tests/test_eval.py`

- [ ] **Step 1: Write tests** for `eval.py` `fidelity_eval`, `challenge_rate_eval`, `parse_session` on synthetic inputs (no LLM/network — feed frozen structures). Assert `fidelity_eval` counts 🔵/🟢/🟡 correctly and `parse_session` is robust to a missing-synthesis session (ties to C3). Mirror the frozen-fixtures pattern from `tests/fixtures/scores/`.
- [ ] **Step 2: Run** → PASS; offline invariant green.
- [ ] **Step 3: Commit** (owner go).

---

## PHASE 4 — doc honesty (OWNER-GATED wording — draft, show, apply only on "да")

Each task DRAFTS the wording and STOPS for owner approval before writing (firewall + antisycophancy lesson: INSTRUCTIONS/claim text is high-risk).

### Task 4.1: H1 — README/MANUAL "word-for-word modulo punctuation/case + sentence-context"
### Task 4.2: H3 — state judge independence requires ollama/api; surface judge level in `doctor`
### Task 4.3: H11 — generate the rules TOC (0-17) from INSTRUCTIONS with a CI lock; fix tool counts (60); fill CHANGELOG `[Unreleased]` from `git log` since last tag
### Task 4.4: H12 — rewrite the tiers section: SIMPLE default; FULL opt-in; RRF-vs-alpha honestly (reconcile SKILL.md:36 with GLOSSARY.md:211)

For each: draft diff → owner reviews → apply → `python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py` → commit (owner go).

---

## PHASE 5 — medium / low verify-first backlog

Not pre-coded (would be placeholder-guessing). Each is a `verify → confirm/refute → fix-or-close` task with its exact locus. Execute after Phases 0-4, one commit per cluster (owner-gated):

- **M1 eval verbatim weaker than prod-gate** — `eval.py` verbatim metric should call `engine.fidelity.best_match` instead of its own chunk-join. Verify divergence with a synthetic quote that joins across chunks; fix to delegate.
- **M2 dead/dormant code** — `multi_query.py` (no prod consumer + cyrillic filter kills lang); `exp_*`/`diagnose_*` one-offs in `scripts/` → move to `scripts/experiments/` or delete; `graph.marker_of` LLM-kernel 🔵 path (loaded gun, unconnected) → assert unreachable + test; `remote.py` references missing contract → fix or remove.
- **M3 gate calibration on small n** — document n=12 provenance of cosine>0.65 auto-keep; SIMPLE-tier + live ollama gate inertness — add a test pinning behavior; `quote_bank` "ИЛИ" in SKILL.md:96 outside runtime gate (one private advisor's 1/12 quote not in corpus) → verify + reconcile.
- **M4 tests/CI** — 10 of 60 tools never dispatched → add dispatch smoke tests; add socket sandbox to make the offline invariant total; add Win/Mac CI legs; pin CI deps.
- **M5 install** — `install.bat` py-launcher mismatch vs README/QUICKSTART; `install.py` swallows subprocess failures yet prints "✅ Готово" → propagate exit codes; root `.mcp.json` broken outside plugin context; `install.py` copies private `council/` into the installed skill → exclude (ties to C6 forbidden set).
- **M6 content** — PD catalog missing Machiavelli while "из коробки" promised; CHANGELOG ground/frame lens mix; SKILL.md rule duplication (−30-40% target) + gitignored-evidence/private "Гефест" refs.
- **M7 misc** — `config_set` no validation (threshold 0 kills all abstention) → clamp + test; retrieve/cite not jobbed under 120s sync timeouts.
- **Low (one-liners)** — `firewall_check.sh` not in CI + narrow secret patterns; unbounded `_JOBS`/`_PENDING_VERDICTS` growth; JSON-RPC no line limit; raw handle in `ingest_telegram`; dead `tier_for(line_no)` param; LSP `HybridEngine.retrieve`; `sys.path.insert`×62 (leave — established pattern); no `.gitattributes` (CRLF); `server.json` → nonexistent release (404 after public flip — fill at release time, ties to runbook); persona/recipes typos; Delphi "exactly this" overclaim; `datetime.utcnow()` deprecated; `eval.py` shadows builtin.

---

## Self-Review

**Spec coverage:** all 6 criticals (C1 Task2.2, C2 closed-via-C1 note, C3 Task1.1, C4 Task1.2, C5 Task1.3, C6 Phase0); all 12 highs (H1 4.1, H2 2.1, H3 4.2, H4 3.2, H5 3.1, H6 1.4, H7 M-note, H8 3.3, H9 3.4, H10 1.3, H11 4.3, H12 4.4); mediums/lows in Phase 5. H7 (legacy build_advisor no-tier) folded into M-backlog — flag: raise to Phase 3 if legacy corpora are found shipping (verify `build_advisor.py` usage first).

**Placeholder scan:** code-bearing tasks (Phase 0-3) carry concrete code + tests; Phase 4-5 are deliberately verify-first (not placeholders — each names file:locus + the check). Acceptable because pre-coding doc/medium fixes would be guessing.

**Type consistency:** `marker_status` returns the same dict shape `_fidelity_check` returned (`status`/`verbatim`/`source`); `generate(..., num_predict, allow_cloud)` signature is consistent across Tasks 1.2 and 3.2 (introduced once, in 1.2).

**Ordering:** C6 first (blocks publish); moat-semantics gated behind an explicit owner design decision (2.0) because it changes what earns 🔵 and touches calibration fixtures.
