# Shipping-quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Consilium Principis robust under concurrent local use, safe and verifiable to install on Windows, reproducible to release as MCPB, and trustworthy as a bilingual open-source project.

**Architecture:** A small neutral atomic-file module becomes the common persistence primitive. Runtime hardening keeps MCP contracts stable while validating malformed input and bounding background work. Distribution work is isolated into installer/Windows, release/supply-chain, and public-contract workstreams; all converge through explicit CI and package smoke tests.

**Tech Stack:** Python 3.10+ standard library, pytest, GitHub Actions, npm-locked `@anthropic-ai/mcpb`, JSON-RPC over stdio.

## Global Constraints

- Keep the core stdlib-only, offline-first, and compatible with Python 3.10+.
- Do not alter public MCP tool names or required JSON fields.
- Preserve fail-closed fidelity and provenance behaviour.
- All runtime MCP diagnostics go to stderr; stdout carries JSON-RPC only.
- New local personal artefacts must default to `0700` directories and `0600` files on POSIX.
- New commit messages are English Conventional Commits.
- English is canonical for code, MCP schemas, manifests, commits, technical docs, and release notes; Russian is maintained user-facing translation.
- Do not translate corpus text, quotations, or source-language metadata.
- No host/platform may be documented as supported until an automated smoke test exists.

---

## Dependency and parallelism map

```
Task 1 atomic files ─┬─ Task 2 runtime hardening
                     └─ Task 3 installer + Windows
Task 4 release/supply-chain ──────────────────────────┐
Task 5 public contracts/docs ──────────────────────────┼─ Task 6 integration gates
Task 2 ────────────────────────────────────────────────┤
Task 3 ────────────────────────────────────────────────┘
```

Run Tasks 1, 4, and 5 in parallel in separate worktrees. After Task 1 is reviewed and integrated, run Tasks 2 and 3 in parallel. Task 6 runs only on the integration worktree.

### Task 1: Atomic persistence and corpus publication

**Files:**
- Create: `scripts/file_atomic.py`
- Modify: `scripts/corpusbuild/pipeline.py`, `scripts/corpusbuild/buildlock.py`
- Test: `tests/test_file_atomic.py`, `tests/test_corpus_pipeline.py`

**Interfaces:**
- Produces `atomic_write_text(path, text, *, encoding="utf-8") -> None`.
- Produces `atomic_write_json(path, obj, *, ensure_ascii=False, indent=2, sort_keys=False) -> None`.
- Both functions publish only after `flush`, `os.fsync`, and `os.replace`; an exception preserves the prior destination and removes the temporary file.

- [ ] **Step 1: Write failing atomic-write tests.**

```python
def test_atomic_write_text_preserves_old_content_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "state.txt"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(file_atomic.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("boom")))

    with pytest.raises(OSError, match="boom"):
        file_atomic.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []
```

Add a JSON round-trip test asserting a trailing newline and a corpus build test that injects the same `os.replace` failure and observes the complete previous corpus byte-for-byte.

- [ ] **Step 2: Run the targeted tests and verify RED.**

Run: `python3 -m pytest tests/test_file_atomic.py tests/test_corpus_pipeline.py -q`

Expected: failure because `scripts.file_atomic` and its functions do not exist.

- [ ] **Step 3: Implement the neutral atomic helper.**

```python
def atomic_write_text(path, text, *, encoding="utf-8"):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
```

Implement `atomic_write_json` with `json.dumps(...)+"\n"` and delegate to `atomic_write_text`. Do not import `governance.py` or domain-specific `atomic.py`.

- [ ] **Step 4: Publish corpus and build lock only through the helper.**

Replace direct final-file writes in `corpusbuild.pipeline` and `buildlock` with the new helpers. Preserve JSONL formatting and existing lock fields exactly; never delete a previous corpus before the replacement succeeds.

- [ ] **Step 5: Run GREEN and commit.**

Run: `python3 -m pytest tests/test_file_atomic.py tests/test_corpus_pipeline.py tests/test_buildlock.py -q`

Expected: PASS.

Commit:

```bash
git add scripts/file_atomic.py scripts/corpusbuild tests/test_file_atomic.py tests/test_corpus_pipeline.py
git commit -m "fix: publish corpus artefacts atomically"
```

### Task 2: Harden MCP input, jobs, private state, and ingestion

**Files:**
- Modify: `scripts/mcp_server.py`, `scripts/federation/queue.py`, `scripts/collect_common.py`, `scripts/lifecycle.py`
- Test: `tests/test_mcp_server_stdio.py`, `tests/test_mcp_server_bounds.py`, `tests/test_federation_queue.py`, `tests/test_collect_strip.py`, `tests/test_lifecycle_tools.py`

**Consumes:** Task 1 `scripts.file_atomic` for any new runtime JSON write.

**Interfaces:**
- Invalid request returns JSON-RPC `-32600`; invalid JSON returns `-32700`; the stdio loop continues.
- `tools/call` with non-object `params` or `arguments` returns `-32602`.
- Network jobs are bounded and coalesced by canonical operation key.
- `job_status` never returns an absolute path or raw exception string.

- [ ] **Step 1: Add failing protocol and job-admission tests.**

```python
def test_stdio_recovers_after_null_request_then_initializes():
    responses = serve_lines(["null\n", json.dumps(INITIALIZE) + "\n"])
    assert responses[0]["error"]["code"] == -32600
    assert responses[1]["result"]["serverInfo"]["name"] == "consilium-principis"

def test_duplicate_ingest_coalesces_to_one_job(monkeypatch, tmp_path):
    first = mcp_server._start_network_job("ingest:/canonical/path", lambda: None, "ingest")
    second = mcp_server._start_network_job("ingest:/canonical/path", lambda: None, "ingest")
    assert second["job_id"] == first["job_id"]
```

Add tests for invalid JSON (`-32700`), scalar/list requests, non-dict `params`/`arguments`, full semaphore rejection, release after failure, source collision suffixes, and POSIX mode bits.

- [ ] **Step 2: Run RED.**

Run: `python3 -m pytest tests/test_mcp_server_stdio.py tests/test_mcp_server_bounds.py tests/test_federation_queue.py tests/test_collect_strip.py tests/test_lifecycle_tools.py -q`

Expected: failures showing the existing server exits or accepts unbounded/overwriting behaviour.

- [ ] **Step 3: Validate requests before field access.**

At the top of `_handle_rpc`, reject non-`dict` messages. Require `jsonrpc == "2.0"` and a string method; for `tools/call` require object `params` and object `arguments`. Return `_rpc_error(request_id, -32600, "Invalid Request")` or `_rpc_error(request_id, -32602, "Invalid params")`. On a JSON decoding exception in `_serve_stdio`, emit `_rpc_error(None, -32700, "Parse error")` and continue.

- [ ] **Step 4: Bound and sanitize background jobs.**

Add a private semaphore and map keyed by `seed` or canonical ingest destination. Acquire before starting a thread, return the existing `job_id` for duplicate keys, return a stable capacity error when full, and release both key and semaphore in `finally`. Store `"job failed; see server stderr"` in public job state and send `repr(exc)` only to stderr.

- [ ] **Step 5: Preserve local state and sources.**

In `SqliteBackend`, create/tighten its parent to `0700` and database/WAL/SHM to `0600` on POSIX. Make `land_to_sources` reserve `slug.txt`, then `slug-2.txt`, with exclusive creation; update manifest/provenance using the final filename. Apply the same no-overwrite rule to clean-source pairs and default Telegram ingestion.

- [ ] **Step 6: Run GREEN and commit.**

Run: `python3 -m pytest tests/test_mcp_server_stdio.py tests/test_mcp_server_bounds.py tests/test_federation_queue.py tests/test_collect_strip.py tests/test_lifecycle_tools.py -q`

Expected: PASS.

Commit:

```bash
git add scripts/mcp_server.py scripts/federation/queue.py scripts/collect_common.py scripts/lifecycle.py tests/
git commit -m "fix: harden MCP runtime state handling"
```

### Task 3: Make installer and Windows support crash-safe

**Files:**
- Modify: `scripts/mcp_install.py`, `scripts/board.py`, `install.bat`, `install.sh`, `install.command`, `.github/workflows/ci.yml`
- Test: `tests/test_mcp_install.py`, `tests/test_install.py`, `tests/test_mcp_server_stdio.py`

**Consumes:** Task 1 `atomic_write_json`.

**Interfaces:**
- Existing `config_path`, `server_command`, `merge_entry`, and `install` remain compatible.
- Add `windows_config_paths(...)`, `config_paths(...)`, and `install_record_path(...)` as internal testable helpers.
- A successful non-dry-run install writes `.consilium/last_mcp_install.json`, never containing secrets.

- [ ] **Step 1: Write failing installer and Windows tests.**

```python
def test_windows_paths_include_classic_and_store_configs(tmp_path):
    paths = mcp_install.windows_config_paths(
        appdata=str(tmp_path / "AppData"),
        localappdata=str(tmp_path / "LocalAppData"),
        glob_fn=lambda _: [str(tmp_path / "LocalAppData/Packages/Claude_123/LocalCache/Roaming/Claude/claude_desktop_config.json")],
    )
    assert paths[0].endswith("AppData/Claude/claude_desktop_config.json")
    assert any("Packages/Claude_123" in path for path in paths)
```

Add tests for interrupted config replacement, dry-run zero side effects, explicit path bypassing discovery, secret-free record, and failed multi-target install not replacing the prior record.

- [ ] **Step 2: Run RED.**

Run: `python3 -m pytest tests/test_mcp_install.py tests/test_install.py tests/test_mcp_server_stdio.py -q`

Expected: failures for unknown helper/record and direct-write recovery behaviour.

- [ ] **Step 3: Implement safe config discovery and install record.**

Use `file_atomic.atomic_write_json` after the existing backup. On Windows include classic `%APPDATA%/Claude/claude_desktop_config.json` plus discovered `%LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json`, deduplicated. Keep one `path` response for compatibility and add optional `paths`/`backups`. After all targets succeed, atomically record only timestamp, server name, platform, paths, command, and args at `.consilium/last_mcp_install.json`.

- [ ] **Step 4: Implement safe launchers and CI smoke coverage.**

Make `install.bat` choose `py -3` then `python` only after `-c "import sys; assert sys.version_info >= (3, 10)"` succeeds; honour `CONSILIUM_NO_PAUSE=1`. Make POSIX launchers provide the same clear Python 3.10+ check. Add a `windows-latest` job running pytest with offline environment plus `install.bat --print`; use pinned action SHAs supplied by Task 4.

- [ ] **Step 5: Run GREEN and commit.**

Run: `python3 -m pytest tests/test_mcp_install.py tests/test_install.py tests/test_mcp_server_stdio.py -q`

Expected: PASS.

Commit:

```bash
git add scripts/mcp_install.py scripts/board.py install.bat install.sh install.command .github/workflows/ci.yml tests/
git commit -m "fix: harden MCP installation across platforms"
```

### Task 4: Produce a verifiable MCPB release pipeline

**Files:**
- Create: `.github/workflows/release.yml`, `scripts/release_validate.py`, `tests/test_release_validate.py`, `package.json`, `package-lock.json`
- Modify: `.mcpbignore`, `.github/workflows/ci.yml`, `docs/dev/mcp-registry-publish-runbook.md`

**Interfaces:**
- `python3 scripts/release_validate.py --tag vX.Y.Z --artifact PATH --registry-manifest server.json` exits zero only for a complete, hash-consistent release.
- `server.json` is outside the MCPB archive, eliminating the self-referential checksum cycle.

- [ ] **Step 1: Write a synthetic-bundle validator test suite.**

```python
def test_validator_accepts_matching_registry_hash(tmp_path):
    artifact = make_bundle(tmp_path, entries={"manifest.json": MANIFEST, "SKILL.md": "# Skill", "scripts/mcp_server.py": ""})
    registry = write_registry(tmp_path, version="0.1.0", sha256=sha256(artifact))
    result = run_validator("v0.1.0", artifact, registry)
    assert result.returncode == 0, result.stderr
```

Add independent failing cases for placeholder/mismatch checksum, version/tag mismatch, `server.json` inside ZIP, forbidden paths, missing entry point, and wrong release URL.

- [ ] **Step 2: Run RED.**

Run: `python3 -m pytest tests/test_release_validate.py -q`

Expected: failure because validator does not exist.

- [ ] **Step 3: Implement deterministic validation and locked packaging.**

Add `server.json` to `.mcpbignore`. Add private dev dependency `@anthropic-ai/mcpb@2.1.2` with a committed lockfile. The validator reads version sources, checks tag/URL/64-hex SHA, inspects ZIP entries, calls the existing bundle denylist, and prints one stderr error per failed invariant without changing files.

- [ ] **Step 4: Add release and supply-chain workflows.**

Create tag-triggered `release.yml` with least-privilege `contents: write`, pinned action SHAs, `npm ci`, manifest validation, bundle pack/guard, release validation, and `gh release create` with `GH_TOKEN` scoped to that step. Pin all existing CI actions to full SHAs; add Dependabot updates for `pip` and `github-actions`; add a repository/skill consistency check and `py_compile` all tracked Python scripts.

- [ ] **Step 5: Run GREEN and commit.**

Run:

```bash
python3 -m pytest tests/test_plugin_manifests.py tests/test_bundle_guard.py tests/test_release_validate.py -q
npm ci
npx mcpb validate manifest.json
npx mcpb pack . /tmp/consilium-principis.mcpb
unzip -Z1 /tmp/consilium-principis.mcpb | python3 scripts/ci_bundle_guard.py -
```

Expected: every command exits 0.

Commit:

```bash
git add .github .mcpbignore package.json package-lock.json scripts/release_validate.py tests/test_release_validate.py docs/dev/mcp-registry-publish-runbook.md
git commit -m "build: add verifiable MCPB release pipeline"
```

### Task 5: Establish public contracts, English canonical docs, and contributor UX

**Files:**
- Create: `PRIVACY_POLICY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`, `.github/ISSUE_TEMPLATE/config.yml`, `.github/ISSUE_TEMPLATE/bug.yml`, `.github/ISSUE_TEMPLATE/source-dispute.yml`, `.github/ISSUE_TEMPLATE/feature.yml`, `.github/dependabot.yml`, `tests/test_public_docs_contract.py`
- Modify: `README.md`, `README.ru.md`, `QUICKSTART.md`, `CONNECT-MCP.md`, `docs/CONNECT-HOSTS.md`, `CONTRIBUTING.md`, `CHANGELOG.md`

**Interfaces:**
- Public docs make no untested host/platform claim and contain no hard-coded MCP tool count.
- EN/RU entry points agree on installation path and support level.
- `PRIVACY_POLICY.md` names every local data class and external data flow.

- [ ] **Step 1: Write failing public-contract tests.**

```python
def test_public_docs_do_not_claim_untested_windows_support():
    documents = public_docs_text()
    assert "works out of the box" not in documents.lower()
    assert "работает из коробки" not in documents.lower()

def test_connect_docs_do_not_hard_code_tool_count():
    assert not re.search(r"\b(?:60|61)\s+(?:MCP )?tools?\b", public_docs_text(), re.I)
```

Add checks for existing local Markdown links, no private corpus paths in public docs, the reproducible `board.py mcp-config --json` path, and absence of the stale “three modes” wording.

- [ ] **Step 2: Run RED.**

Run: `python3 -m pytest tests/test_public_docs_contract.py tests/test_readme_honest_claims.py -q`

Expected: failures caused by present stale tool-count, Windows, or tier wording.

- [ ] **Step 3: Publish the language and privacy contracts.**

Update EN and RU README/Quickstart/host docs together. State SIMPLE/FULL as tiers and hybrid as opt-in; present Windows and untested hosts honestly; prefer generated `mcp-config --json`. Add the language policy to `CONTRIBUTING.md`: English commits/code/schemas/canonical technical docs, maintained RU entry points, and original-language sources. Document local corpora, decisions, consults, federation SQLite, audit logs, source downloads, Ollama, optional OpenRouter, and MCP-host trust boundary in the privacy policy.

- [ ] **Step 4: Add community entry points and automated truthfulness checks.**

Add support, conduct, governance, and issue forms. The source-dispute form must request the advisor/source, exact quote, claimed marker, expected marker, and a reproducible command/session. Add Dependabot settings. Keep security reports directed to `SECURITY.md`, not public issue forms.

- [ ] **Step 5: Run GREEN and commit.**

Run:

```bash
python3 -m pytest tests/test_public_docs_contract.py tests/test_readme_honest_claims.py tests/test_selfdoc_fresh.py -q
python3 scripts/gen_selfdoc.py --check
python3 scripts/build_manual.py --check
```

Expected: every command exits 0.

Commit:

```bash
git add README.md README.ru.md QUICKSTART.md CONNECT-MCP.md docs/CONNECT-HOSTS.md CONTRIBUTING.md CHANGELOG.md PRIVACY_POLICY.md SUPPORT.md CODE_OF_CONDUCT.md GOVERNANCE.md .github/ISSUE_TEMPLATE .github/dependabot.yml tests/test_public_docs_contract.py
git commit -m "docs: establish public project contracts"
```

### Task 6: Integrate and verify the shipping-quality release candidate

**Files:**
- Modify only when integration reveals a real conflict.
- Test: all new targeted tests plus the complete existing suite.

**Consumes:** Reviewed commits from Tasks 1–5.

- [ ] **Step 1: Merge reviewed worktree commits in dependency order.**

Merge Task 1 before Tasks 2 and 3. Merge Tasks 4 and 5 independently. Resolve only textual conflicts; do not change behaviour to “make merge pass” without a new failing test.

- [ ] **Step 2: Run all local quality gates.**

```bash
git diff --check
python3 -m py_compile $(git ls-files '*.py')
sh scripts/firewall_check.sh
python3 -m pytest tests/ -q
npm ci
npx mcpb validate manifest.json
npx mcpb pack . /tmp/consilium-principis.mcpb
unzip -Z1 /tmp/consilium-principis.mcpb | python3 scripts/ci_bundle_guard.py -
```

Expected: every command exits 0. Run the same full test suite with `HEPHAESTUS_ENGINE=/nonexistent` and `OLLAMA_HOST=http://127.0.0.1:59999` if the shell environment did not inherit those values.

- [ ] **Step 3: Verify release metadata without publishing.**

Build the final artefact, calculate SHA-256, set it only through the documented release preparation procedure, and run:

```bash
python3 scripts/release_validate.py \
  --tag v$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])") \
  --artifact /tmp/consilium-principis.mcpb \
  --registry-manifest server.json
```

Expected: exit 0. Do not create or push a tag in this task; publishing requires explicit user authorization.

- [ ] **Step 4: Perform final review and commit only integration fixes.**

Request an independent final review. If no integration changes were needed, do not create an empty commit. Otherwise use an English Conventional Commit such as `fix: reconcile release hardening checks`.
