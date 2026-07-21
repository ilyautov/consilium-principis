# Review Follow-up Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all ten confirmed findings from the review of `HEAD~32..HEAD` while retaining valid MCP request behavior.

**Architecture:** Keep current module boundaries. `mcp_server.py` validates public RPC inputs and job admission; fidelity, diversity, judge state, diagnostics, and the firewall remain in their domain modules. Every change starts with a focused regression test.

**Tech Stack:** Python 3 standard library, pytest, POSIX shell.

## Global Constraints

- Do not alter or stage the three user-owned untracked files already in the worktree.
- Valid MCP calls retain their response shapes; invalid or oversized input returns `{"error": ...}` before expensive work.
- Add no dependencies. Use `tmp_path` and `monkeypatch`, not real corpus/network/workers.
- Run `git diff --check` and relevant pytest modules after each task. Report the existing public-DNS test separately if it blocks the full suite.

---

### Task 1: Preserve citation and source-path integrity

**Files:**

- Modify: `scripts/engine/fidelity.py:35-56`
- Modify: `scripts/mcp_server.py:135-148`
- Modify: `scripts/doctor.py:270-310`
- Modify: `scripts/firewall_check.sh:21`
- Test: `tests/test_fidelity_negation_crop.py`, `tests/test_mcp_server.py`, `tests/test_doctor.py`, new `tests/test_firewall_check.py`

**Interfaces:**

- `_crop_severs_negation(q: str, raw_text: str) -> bool` returns true when a normalized match must not be verified.
- `_is_sensitive_path(rp: str) -> bool` rejects protected runtime paths.
- `check_corpus_tier_fields(root: str) -> dict` reports qualified advisor or lens paths.

- [ ] **Step 1: Write failing tests**

Append this fidelity regression:

```python
def test_cross_sentence_negation_not_blue(tmp_path):
    from engine import fidelity
    adv = _mk_advisor(tmp_path, "He did not endorse war. Pursue peace and mercy.")
    assert fidelity.marker_status("endorse war pursue peace", adv)["status"] == "🟡"
```

Add an MCP test that creates `tmp_path / ".consilium" / "swallow.log"`, patches `mcp_server._root`, and asserts `_load_source_text(path=".consilium/swallow.log")` raises `ValueError`. Add a doctor fixture at `lenses/legacy/build/corpus.jsonl` with a record without `tier`; assert the check is false and contains `lenses/legacy`. Add a shell test using a clean temporary git repository with only allowed advisors; assert `sh scripts/firewall_check.sh` exits zero and prints `firewall-check: OK`.

- [ ] **Step 2: Verify red**

Run:

```bash
python3 -m pytest tests/test_fidelity_negation_crop.py tests/test_mcp_server.py tests/test_doctor.py tests/test_firewall_check.py -q
```

Expected: the cross-sentence quote is 🔵, runtime log is accepted, the lens is missed, and clean firewall exits nonzero.

- [ ] **Step 3: Implement the minimal corrections**

In `_crop_severs_negation`, replace the last line `return found` with `return not found`: a whole-chunk normalized match absent from every raw sentence is a cross-boundary match and fails closed. Extend `_SENSITIVE_RE` with `r"|(^|/)\.consilium(/|$)"`. Iterate `("advisors", "lenses")` in the doctor, adding qualified paths such as `lenses/legacy` to its detail. Make the private-advisor discovery non-fatal:

```sh
PRIV=$(ls advisors 2>/dev/null | grep -v '^README.md$' | grep -ivE "^($PD_ALLOW)$" || true)
```

- [ ] **Step 4: Verify green and commit**

```bash
python3 -m pytest tests/test_fidelity_negation_crop.py tests/test_mcp_server.py tests/test_doctor.py tests/test_firewall_check.py tests/test_cite_early_exit.py -q
git diff --check
git add scripts/engine/fidelity.py scripts/mcp_server.py scripts/doctor.py scripts/firewall_check.sh tests/test_fidelity_negation_crop.py tests/test_mcp_server.py tests/test_doctor.py tests/test_firewall_check.py
git commit -m "fix: close review integrity regressions"
```

### Task 2: Bound public fan-out and payload size

**Files:**

- Modify: `scripts/mcp_server.py:287-340,1355-1435`
- Modify: `scripts/serving_gate_eval.py:75-125`
- Test: `tests/test_mcp_server.py`, `tests/test_diversity_check_tool.py`, `tests/test_federation_mcp.py`, `tests/test_serving_gate_eval.py`

**Interfaces:**

- `retrieve.top_k`: integer `1..32`.
- `diversity_check.advisor_dirs`: 2–32 unique resolved directories.
- Federation: at most 64 roles, 32 replicas, 4096 characters per scalar text field, and 256 KiB of expanded question text.
- `n_samples`: integer `1..5`.

- [ ] **Step 1: Write failing tests**

Patch `engine.retrieval.retrieve` and assert `_retrieve("q", "advisors/a", top_k=33)` returns an error without calling it; `top_k=32` reaches it. Give diversity 33 repeated valid paths and assert rejection before `check`; give two equivalent spellings of one path and assert the deduplicated list fails minimum-two. In federation tests use a 4097-character question and repeated questions totaling more than 256 KiB; both must error before `_fed_backend`. In serving-gate tests assert `n_samples=6` and `"3"` raise `ValueError`, while 5 invokes the judge five times.

- [ ] **Step 2: Verify red**

```bash
python3 -m pytest tests/test_mcp_server.py tests/test_diversity_check_tool.py tests/test_federation_mcp.py tests/test_serving_gate_eval.py -q
```

Expected: oversize input reaches expensive collaborators.

- [ ] **Step 3: Implement named boundary guards**

Place these next to current federation constants:

```python
_RETRIEVE_MAX_TOP_K = 32
_DIVERSITY_MAX_ADVISORS = 32
_FED_MAX_FIELD_CHARS = 4096
_FED_MAX_EXPANDED_TEXT_CHARS = 256 * 1024
```

Before `retrieval.retrieve`, reject booleans, non-integers, and values outside `1.._RETRIEVE_MAX_TOP_K`. Resolve diversity paths, canonicalize using `os.path.realpath`, deduplicate in input order, then require `2.._DIVERSITY_MAX_ADVISORS`. Require string `role`, `advisor_dir`, and `question` fields at most `_FED_MAX_FIELD_CHARS`; after replica clamping, reject total `sum(len(question) * replicas)` above `_FED_MAX_EXPANDED_TEXT_CHARS`. At serving-gate entry raise `ValueError("n_samples must be an integer from 1 to 5")` unless a non-boolean int in that range is provided.

- [ ] **Step 4: Verify green and commit**

```bash
python3 -m pytest tests/test_mcp_server.py tests/test_mcp_server_stdio.py tests/test_diversity_check_tool.py tests/test_federation_mcp.py tests/test_serving_gate_eval.py tests/test_relevance_gate.py -q
git diff --check
git add scripts/mcp_server.py scripts/serving_gate_eval.py tests/test_mcp_server.py tests/test_diversity_check_tool.py tests/test_federation_mcp.py tests/test_serving_gate_eval.py
git commit -m "fix: bound MCP fan-out and eval samples"
```

### Task 3: Make background work and judge state concurrency-safe

**Files:**

- Modify: `scripts/mcp_server.py:1232-1272`
- Modify: `scripts/relevance_judge.py:28-145`
- Test: `tests/test_mcp_server_bounds.py`, `tests/test_relevance_judge.py`

**Interfaces:**

- `_start_job(fn, label)` returns an error without starting a thread at active capacity.
- Terminal jobs remain evictable; running records remain observable through completion.
- Breaker mutations use `_CB_LOCK`; the network call occurs outside the lock.

- [ ] **Step 1: Write failing tests**

Fill `_JOBS` with exactly `_MAX_JOBS` running entries, patch `threading.Thread.start`, call `_start_job`, and assert an error with zero starts. Remove a running record before its delayed function returns and assert no `KeyError`. Add a barrier-based judge test that forces `_CB_FAILS` concurrent failures then verifies callers admitted after opening return zero without entering `llm_local.generate`.

- [ ] **Step 2: Verify red**

```bash
python3 -m pytest tests/test_mcp_server_bounds.py tests/test_relevance_judge.py -q
```

Expected: a job starts above capacity or worker completion dereferences a removed record; breaker state is unsynchronized.

- [ ] **Step 3: Implement admission and locking**

Under `_JOBS_LOCK`, evict terminal records before allocation. If capacity remains full, return:

```python
{"error": "слишком много активных фоновых задач; дождись job_status"}
```

Remove fallback eviction of a running record. In the worker use `job = _JOBS.get(jid)` and update only when it remains. Add `_CB_LOCK = threading.Lock()`; lock admission, failure increment/opening, and success reset independently, never around `llm_local.generate`.

- [ ] **Step 4: Verify green and commit**

```bash
python3 -m pytest tests/test_mcp_server_bounds.py tests/test_relevance_judge.py tests/test_lifecycle_tools.py tests/test_relevance_gate.py -q
git diff --check
git add scripts/mcp_server.py scripts/relevance_judge.py tests/test_mcp_server_bounds.py tests/test_relevance_judge.py
git commit -m "fix: bound background jobs and lock judge breaker"
```

### Task 4: Integrated verification

**Files:** no production changes expected.

- [ ] **Step 1: Run focused verification**

```bash
git diff --check
python3 -m pytest tests/test_fidelity_negation_crop.py tests/test_mcp_server.py tests/test_mcp_server_bounds.py tests/test_diversity_check_tool.py tests/test_federation_mcp.py tests/test_relevance_judge.py tests/test_serving_gate_eval.py tests/test_doctor.py tests/test_firewall_check.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run the complete suite with evidence**

```bash
review_tmp=$(mktemp -d /private/tmp/consilium-review.XXXXXX)
python3 -m pytest -q > "$review_tmp/pytest.log" 2>&1
review_status=$?
tail -n 20 "$review_tmp/pytest.log"
exit "$review_status"
```

If the pre-existing public-DNS test blocks, rerun excluding only `tests/test_lifecycle_tools.py::test_ssrf_check_passes_public_blocks_private`; record its exact status and do not claim the full suite is green.

- [ ] **Step 3: Inspect final scope**

```bash
git status --short
git log --oneline -4
git diff HEAD~3..HEAD --check
```

Confirm planned source/test files are committed and the three pre-existing untracked user files remain untouched.

