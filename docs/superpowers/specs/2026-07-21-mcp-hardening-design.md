# MCP Hardening Follow-up Design

**Goal:** Eliminate the six fresh review findings without changing valid MCP workflows.

## Boundaries

All public fan-out inputs are validated before allocation or backend access: retrieval and cite queries have a UTF-8 byte limit; cite accepts at most eight bounded strings; federation identifiers, worker metadata, and role arrays are bounded; the aggregate federation budget includes repeated identifiers as well as questions.

## Judge isolation

Telegram handles are canonicalized before storage in corpus metadata. The relevance judge treats query and source as untrusted delimited data, escapes delimiters, and tells the model to ignore embedded instructions.

## Concurrency

Background jobs use a small execution semaphore and one in-flight build per resolved advisor. The relevance breaker uses a generation counter with one half-open probe; stale responses cannot overwrite newer breaker state.

## Testing

Each input and concurrency invariant receives a failing hermetic regression test before implementation. Existing valid request shapes remain unchanged; only malformed or resource-abusive input receives an error response.

## Non-goals

- No dependency or public MCP tool.
- No broad server refactor.
- No migration of federation database contents.
