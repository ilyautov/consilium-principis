# Shipping-quality design

## Goal

Make Consilium Principis safe to operate and distribute as an MCP skill: preserve local data integrity under concurrent work, make installation and Windows support verifiable, publish a reproducible MCPB release, and provide clear English-first open-source contracts with maintained Russian user documentation.

## Scope and constraints

- Python 3.10+; keep the core stdlib-only and offline-first.
- Preserve the existing fail-closed fidelity, provenance, and privacy model.
- Do not claim support for an MCP host or platform without an automated smoke test.
- Runtime MCP stdout remains JSON-RPC only; diagnostics go to stderr.
- User-local artefacts remain outside Git and are private by default.
- All new commit messages are written in English and use the existing Conventional Commit style.
- Canonical public technical material is English. Russian remains a maintained user-facing translation where it exists or is needed for onboarding.
- Original source texts and quotations remain in their original language; no translation changes a corpus or provenance record.

## 1. Reliable local state and MCP boundary

Introduce one small persistence utility for JSON/text artefacts. It writes a temporary file in the destination directory, flushes and fsyncs it, applies private file permissions where the artefact is personal, and publishes it with `os.replace`. Read-modify-write operations use a per-file lock.

Use the utility for `board_config.json`, decision cards, consult records, the Claude Desktop config merge, and new installer records. Build a corpus and its semantic index in a staging generation, then atomically publish the completed generation so retrieval never observes a partial JSONL, `.npy`, or metadata file.

Validate every JSON-RPC request before accessing fields. A request that is not an object, or a `tools/call` request whose `params`/`arguments` are not objects, returns JSON-RPC `-32600` and the stdio server continues serving requests.

Replace unbounded background network threads with a bounded shared executor. Keep the existing per-advisor build single-flight behaviour, add single-flight keys for seed/ingest destinations, and return a busy/queued status instead of creating duplicate work. Source ingestion rejects a filename collision unless the caller explicitly supplies a distinct safe name.

Create personal runtime directories with `0700` and their files with `0600` on POSIX. Existing files are tightened safely when opened. This covers federation state, personal advisors, decision/consult journals, and diagnostic audits.

## 2. Installation, MCP hosts, and Windows

The installer uses the atomic persistence utility when merging a desktop configuration, keeps the existing timestamped backup, and reports its recovery path. It writes a secret-free install record that allows `doctor` to independently confirm the installed runtime and stdio MCP `initialize` handshake.

Installers and launchers select a real Python 3.10+ interpreter. On Windows they detect the `py` launcher and reject Microsoft Store alias stubs; they provide a clear manual remediation, without automatically installing software. The Windows discovery code checks both classic and Store Claude Desktop configuration locations, reporting exactly which config was changed.

Keep a single canonical runtime copy for installation so a host configuration does not break merely because a source checkout moves. Preserve the present no-pip, stdlib-first installation model.

Add `windows-latest` CI coverage for the supported launcher path, config generation/merge, and a stdio `initialize`/`tools/list` smoke test. Retain Linux and macOS coverage.

## 3. Reproducible release and supply chain

Add a tag-triggered release workflow. It runs the ordinary test suite, compiles every tracked Python script, executes repository/skill/release consistency checks, creates the MCPB artefact, runs the bundle guard against the exact artefact, smoke-tests its MCP server, calculates SHA-256, attaches the artefact and checksum to the GitHub Release, and only then permits registry metadata to reference the release asset.

`server.json` never ships with a checksum placeholder. The release validator fails if the placeholder is present, version fields disagree, a release asset URL is inconsistent with the tag, or public documentation carries a stale MCP-tool count.

Pin third-party GitHub Actions to full commit SHAs. Add Dependabot updates for GitHub Actions and pip dependencies. Keep dependency locking proportional to the stdlib-first project: development requirements are version- and hash-locked for CI; optional dependencies remain explicitly separated.

Add local, dependency-free repository checks for the skill/runtime layout, plugin and MCP metadata, relevant Markdown links, generated tool count, version consistency, dangerous tracked files, and compilation of every Python script. Secret scanning and dependency audit workflows are additive and must use least-privilege permissions.

## 4. Documentation, language, and community contracts

Document a language policy:

- English is canonical for code, identifiers, API/MCP schemas, manifests, release notes, commit messages, contributor rules, and technical documentation.
- Russian is a maintained translation for end-user entry points and onboarding.
- Source texts, quotes, bibliographic titles, and language metadata preserve the original source language.
- The PD catalogue uses stable language-neutral IDs and structured metadata (`title`, `original_language`, `translator`, `license`, provenance) rather than translating source facts into identifiers.

Make the implementation enforce the mechanical parts: version, installation commands, supported-host status, release links, and tool counts must be equal across EN/RU surfaced documents. A change to a canonical statement requires its Russian counterpart in the same pull request or an explicit translation-debt marker that CI permits only for a defined short list of non-user-facing files.

Add `PRIVACY_POLICY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, and a concise `GOVERNANCE.md`. Privacy documentation describes local corpora, decisions, federation SQLite, audit logs, external source fetches, Ollama endpoints, explicit OpenRouter opt-in, and the MCP-host trust boundary. Add issue forms for bugs, source/attribution disputes, documentation, and features; security reports remain directed to the private security channel. Add a `NOTICE` only for shipped assets or corpora that require attribution.

Host support is presented as a matrix: supported means CI smoke-tested; experimental means adapter available but not yet tested; unsupported means documented no-claim. Thin adapters may be added only when they do not fork the core SKILL/MCP logic.

## Error handling and compatibility

- All new validations fail closed: unsafe paths, malformed RPC, incomplete generations, inconsistent metadata, and absent checksums stop the operation without publishing partial state.
- Existing user data is not migrated or overwritten silently. A recovery path is reported for a failed config update.
- The release workflow does not introduce a mandatory cloud service at runtime.
- Public MCP tool names and JSON schemas stay backward compatible; added diagnostic fields are optional.

## Test strategy

- Test-first regressions for malformed RPC, interrupted/competing atomic writes, concurrent retrieval/build, index publication, filename collisions, job limits, private permissions, and sanitized async errors.
- Unit tests for Python discovery and Windows config-path selection, with Windows CI smoke coverage.
- Installer tests prove an interrupted write retains a valid previous config and a backup.
- Bundle/release tests reject placeholders, stale versions, missing runtime files, wrong checksums, and stale tool counts.
- Documentation checks cover language-policy invariants and EN/RU mechanical parity.
- Preserve the full offline `make test` suite as the final gate and add targeted commands for every new linter and package smoke test.

## Parallel implementation boundaries

The work is split into isolated worktrees so changes do not overlap:

1. Runtime reliability: atomic persistence, MCP validation, corpus/index generation, job bounds, permissions, and tests.
2. Installation and Windows: installer/config merge, interpreter/path discovery, install record, Windows CI, and tests.
3. Release and supply chain: repository linters, action pins, Dependabot, release workflow, MCPB validation, and tests.
4. Public contracts: language policy, EN/RU parity checks, privacy/community documents, issue forms, support matrix, and tests.

Each worktree must use test-driven changes, English Conventional Commit messages, a focused commit, and a reviewer pass before integration. The integration branch runs all linters, bundle smoke tests, Windows CI through GitHub, and the full offline test suite.

## Non-goals

- Do not translate corpora or alter cited source text.
- Do not add automatic package-manager installation, an HTTP server, telemetry, or a mandatory cloud backend.
- Do not claim Codex, Cursor, Gemini, or a Windows path as supported until its end-to-end smoke test exists.
- Do not replace the existing fidelity model or redesign public MCP tools as part of this hardening work.
