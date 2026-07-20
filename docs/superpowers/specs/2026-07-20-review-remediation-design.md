# Review Remediation Design

**Goal:** Remove every High, Medium, and Low finding identified in the review of `HEAD~32..HEAD` without changing valid MCP workflows.

## Scope

The remediation covers citation integrity, MCP resource limits, background-job lifecycle, private runtime paths, diagnostics, and the CI firewall guard. It does not refactor unrelated server code or alter successful request/response schemas.

## Citation integrity

`engine.fidelity.best_match` must fail closed when a normalized quote match crosses a raw sentence boundary. A quote is eligible for a verified marker only when the normalized match can be attributed to one sentence; this prevents sentence joining from removing a preceding negation. A regression fixture combines a negated sentence and an unrelated following sentence.

## MCP limits and asynchronous jobs

The public MCP boundary validates and caps every newly exposed fan-out parameter:

- `retrieve.top_k` accepts only integer values from 1 through 32.
- `diversity_check.advisor_dirs` is canonicalized, deduplicated, and capped before pair generation.
- Federation validates scalar field types and sizes, as well as the aggregate expanded-task payload, before queue creation.
- `serving_gate_eval.n_samples` accepts only a small positive integer range.

Background jobs have a bounded number of active workers. A new request is rejected or reported as full when capacity is exhausted; an active job record is never evicted, and worker completion handles a missing record defensively.

## Private data and diagnostics

All source-reading paths reject `.consilium` as a protected runtime directory, including `swallow.log`. The doctor corpus-tier check scans both `advisors/` and citeable `lenses/` so a missing tier cannot be reported as healthy.

## CI reliability

The firewall guard treats an empty set of private advisors as a valid clean-CI condition while retaining its detection of literal and glob-sensitive private paths.

## Concurrency

The relevance-judge circuit breaker serializes only its internal state transitions. Network calls remain outside the lock; callers re-check admission under the lock so a newly opened breaker prevents additional long calls.

## Testing and compatibility

Each defect gets a focused regression test written before its implementation. Existing valid requests retain their shapes and behavior; only malformed or resource-abusive inputs receive a deterministic validation error. Targeted tests cover every touched module, followed by the project suite; the pre-existing public-DNS test is isolated and reported separately if external DNS prevents a full run.

## Non-goals

- No new dependency or public MCP tool.
- No migration of old valid persisted session data.
- No broad reorganization of `mcp_server.py` beyond the affected helpers.
