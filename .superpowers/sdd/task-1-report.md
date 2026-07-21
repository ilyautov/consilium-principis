# Task 1 report — Bound untrusted MCP payloads

## TDD evidence

RED (before implementation):

```text
pytest -q tests/test_mcp_server.py::test_retrieve_and_cite_reject_over_byte_cap_queries_before_retrieval tests/test_mcp_server.py::test_cite_rejects_more_than_eight_queries_without_iterating_items tests/test_federation_mcp.py::test_federation_rejects_invalid_identifiers_and_roles_before_backend tests/test_federation_mcp.py::test_federation_expanded_budget_counts_replicated_session_identifier tests/test_host_judge_protocol.py::test_host_cite_rejects_oversize_query_before_nonce_allocation
```

Result: `5 failed in 0.21s`, each because the new required boundary constant did not yet exist (`AttributeError`), confirming the intended safeguards were absent.

GREEN (after minimal implementation):

```text
pytest -q tests/test_mcp_server.py::test_retrieve_and_cite_reject_over_byte_cap_queries_before_retrieval tests/test_mcp_server.py::test_cite_rejects_more_than_eight_queries_without_iterating_items tests/test_federation_mcp.py::test_federation_rejects_invalid_identifiers_and_roles_before_backend tests/test_federation_mcp.py::test_federation_expanded_budget_counts_replicated_session_identifier tests/test_host_judge_protocol.py::test_host_cite_rejects_oversize_query_before_nonce_allocation
```

Result: `5 passed in 0.21s`.

Focused regression verification:

```text
OLLAMA_HOST=http://127.0.0.1:59999 pytest -q tests/test_mcp_server.py tests/test_federation_mcp.py tests/test_host_judge_protocol.py && git diff --check
```

Result: `100 passed in 1.86s`; `git diff --check` exited 0 with no output.

The temporary loopback `OLLAMA_HOST` makes the host-judge suite use its intended lexical test mode; this machine otherwise has a reachable semantic backend, which changes the suite's host-candidate fixtures independently of this task.

## Changes

- Added named UTF-8 byte/count caps and a shared bounded-string validator.
- Reject oversized/non-string retrieve and cite queries before retrieval; cite rejects lists over eight before iterating them and retains the normal empty-cite response fields on invalid input.
- Validated federation session/task/worker/token/model IDs and role arrays before backend access.
- Changed the federation expansion budget to bytes and counted all per-replica stored identifiers, including the session ID and question.

## Review follow-up — malformed input

RED (before review fix):

```text
pytest -q tests/test_federation_mcp.py::test_federation_rejects_lone_utf16_surrogate_before_backend tests/test_federation_mcp.py::test_federation_open_falls_back_for_infinite_default_replicas
```

Result: `2 failed in 0.16s`: a lone `"\\ud800"` reached `_fed_backend`, and `int(float("inf"))` raised `OverflowError`.

GREEN (after minimal review fix):

```text
pytest -q tests/test_federation_mcp.py::test_federation_rejects_lone_utf16_surrogate_before_backend tests/test_federation_mcp.py::test_federation_open_falls_back_for_infinite_default_replicas
```

Result: `2 passed in 0.09s`.

- The common validator rejects UTF-16 surrogate code points before backend calls or UTF-8 encoding can occur.
- Infinite `replicas_default` now follows the existing malformed-value fallback to `3`.
