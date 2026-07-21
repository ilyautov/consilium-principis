# MCP Hardening Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six new security and resource-amplification findings.

**Architecture:** Validate all MCP data at the boundary; preserve valid response shapes. Keep prompt-data escaping in the judge module and concurrency ownership in its existing state module.

**Tech Stack:** Python stdlib, pytest, POSIX shell.

## Global Constraints

- No dependency or public-tool additions.
- Every behavior change begins RED then GREEN.
- Reject malformed/oversized public inputs before allocation, engine, or SQLite access.
- Preserve user untracked files; use an isolated worktree for execution.

### Task 1: Bound untrusted MCP payloads

**Files:** `scripts/mcp_server.py`; `tests/test_mcp_server.py`; `tests/test_federation_mcp.py`; `tests/test_host_judge_protocol.py`.

- [ ] Write failing tests: a >byte-cap retrieve/cite query never invokes retrieval; cite list >8 never materializes all items; overlong/non-string session ID, worker IDs/models, and >64 roles error before backend.
- [ ] Run focused tests and confirm RED.
- [ ] Add named byte/count constants and a common bounded-string validator. Apply it before retrieval/dedupe and to all federation entry points; account replicated session ID and question bytes together.
- [ ] Run focused MCP/federation/host-judge tests and `git diff --check`; commit `fix: bound MCP query and federation payloads`.

### Task 2: Isolate judge data and repair breaker ownership

**Files:** `scripts/relevance_judge.py`; `scripts/ingest_telegram.py`; `tests/test_relevance_judge.py`; matching Telegram tests.

- [ ] Write failing tests: newline/control-character handle cannot reach corpus metadata; injected query/source remains inside escaped data blocks; only one half-open judge probe is admitted; stale failure cannot reopen a recovered breaker.
- [ ] Run tests and confirm RED.
- [ ] Canonicalize handle once before fetch/storage. Escape source/query delimiters and render both inside untrusted-data blocks. Add generation plus half-open ownership under `_CB_LOCK`.
- [ ] Run judge/ingest/gate tests and `git diff --check`; commit `fix: isolate judge inputs and half-open breaker`.

### Task 3: Bound execution and verify integration

**Files:** `scripts/mcp_server.py`; `tests/test_mcp_server_bounds.py`.

- [ ] Write failing tests: global active-build cap refuses excess execution; duplicate build for a resolved advisor returns/coalesces the existing job.
- [ ] Run test and confirm RED.
- [ ] Add a small execution semaphore plus resolved-advisor single-flight lifecycle cleanup without changing job-status contracts.
- [ ] Run targeted tests, then `HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest -q`; commit `fix: bound build execution`.

