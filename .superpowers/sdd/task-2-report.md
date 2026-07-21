# Task 2 — Isolate judge data and repair breaker ownership

## Scope

- `scripts/ingest_telegram.py`
- `scripts/relevance_judge.py`
- `tests/test_ingest_telegram.py`
- `tests/test_relevance_judge.py`

## Behaviour covered

- `ingest()` canonicalizes the Telegram handle once, before both fetch and corpus metadata storage.
- Query and source are rendered only in their own escaped untrusted-data blocks; embedded block delimiters are neutralized.
- The breaker grants exactly one half-open request after cooldown.
- Generation ownership prevents an old failed request from reopening a breaker that a newer request recovered.

## Verification

The targeted RED/GREEN judge and Telegram tests pass, together with the related gate and host-protocol suite in deterministic offline mode:

```sh
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 \
  PYTHONPATH=scripts pytest -q \
  tests/test_relevance_judge.py tests/test_ingest_telegram.py \
  tests/test_relevance_gate.py tests/test_gate_simple_tier_inert.py \
  tests/test_host_judge_protocol.py
# 144 passed
git diff --check
```

The environment variables are required by the existing gate tests to force their documented offline lexical mode; without them a locally available semantic engine changes their intended assertions.

## Review follow-up: RED/GREEN

Added two regression tests before changing production code:

- `test_ingest_telegram_job_label_and_result_hide_raw_handle` proves that a CR/LF-containing handle cannot enter the externally visible job label or completed status/result.
- `test_normal_success_does_not_discard_prior_inflight_failures` starts three failures, lets an ordinary success finish first, then verifies those pre-existing failures still open the breaker.

RED command and result:

```sh
HEPHAESTUS_ENGINE=/nonexistent OLLAMA_HOST=http://127.0.0.1:59999 \
  PYTHONPATH=scripts pytest -q \
  tests/test_mcp_server.py::test_ingest_telegram_job_label_and_result_hide_raw_handle \
  tests/test_relevance_judge.py::TestJudgeCircuitBreaker::test_normal_success_does_not_discard_prior_inflight_failures
# 2 failed
```

GREEN command and result (same command after the minimal fixes):

```text
2 passed
```
