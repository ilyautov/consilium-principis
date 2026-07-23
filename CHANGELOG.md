# Changelog

Format — [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions — [SemVer](https://semver.org/). Dates in ISO (YYYY-MM-DD).

## [Unreleased]

## [0.1.2] — 2026-07-23

### Fixed
- Windows launcher writes UTF-8 reliably; the governance guard now rejects cross-drive paths.

### Changed
- CI dependencies and GitHub Actions were refreshed.
- Release publication is repeat-safe when a release already exists.

## [0.1.1] — 2026-07-23

### Added
- Reliable release pipeline: hash-locked CI dependencies, registry-manifest validation, MCPB
  packaging and smoke-test, and a guard against private/local artifacts entering the distribution.
- English canonical quick-start and MCP guides, with parity contracts for the Russian translations.
- **calibrated-consult** — opt-in overreliance-measurement mode: records your position BEFORE the
  council answers, mirrors it AFTER, calibrates against the outcome (MCP interface, Rule 17).
- **CONSILIUM_LANG** — force the council's response language.
- **.mcpbignore + ci_bundle_guard.py** — public-bundle content guard (secrets/copyright/personal
  data cannot leave via `mcpb pack`).
- Public contracts: privacy policy, support, conduct/governance, issue forms, and a
  documentation-honesty check.
- **Rule 18** — dissent / reframe-check / diversity / never_quote in the council INSTRUCTIONS.
- **diversity_check** — Step 0b (composition-diversity check) available to pure MCP hosts.
- **doctor check `corpus-tier-fields`** — catches a corpus without tier fields; explicit-tiering
  build path.

### Changed
- Unified `sys.path` idiom + AST guard against in-function import hacks.
- Single lifecycle module for CLI and MCP (deduplicated front-ends).
- Shared slug/path/root guards without copies; `retrieve` moved to `engine/retrieval.py` (dead gate
  copy removed).
- Extracted `mcp_decisions.py`; the `mcp_server` facade is preserved.

### Fixed
- Atomic corpus publications and guarded concurrent updates of private state.
- MCP installer: immutable user runtime, partial-install rollback, and a real stdio-handshake check
  via `doctor`.
- Permissions on personal sources and Telegram exports; Cowork honestly marked as an unverified
  integration path.
- **Fidelity (C1/H2):** 🔵 requires ≥3 words and rejects truncation that breaks a negation (before,
  a single word or a torn fragment could pass as 🔵).
- **Security (H5):** read-side path-traversal guard — every path (abs and rel) is clamped to the
  repo root (closes arbitrary-file-read via host-exposed tools).
- **Privacy (H4):** the relevance judge stays local even with `LLM_BACKEND=openrouter` (the corpus
  never leaks to the cloud).
- **Bulk path (C3/C4/C5):** render crash without synthesis; judge timeout (`num_predict`);
  O(cand×corpus) rescans (mtime cache).
- **DRY (H6):** a single `marker_status` — one source for the core invariant.
- **Negation (C2):** negation guard scoped to the sentence (contractions, distance, `without`).
- **Gate (M4):** the judge gates verbatim outside semantic mode; under hybrid it gates on raw cosine
  (`raw_score`), not the blend.
- **Judge (M9):** 20s timeout + circuit-breaker (3 misses/60s) against a hanging ollama;
  TTL-memoized availability; `EVAL_ENGINE` only in eval inputs (prefer does not leak into the
  engine cache).
- **Eval (M5/M6):** `safe_expr` OverflowError→SafeExprEvalError; judge median, tolerance ≥1/n,
  `--out` flag.
- **Tests (H8/H9/M7):** numpy-optional collection; eval-harness coverage; stdio e2e, FS sandbox,
  federation e2e, zero-modules, demo fixture; `html_to_text` fallback without bs4.
- **Observability (M8):** `_swallow` with logging — audit-critical sites no longer stay silent.
- **Doc honesty (H6/H11/H12/M10):** rule counters refreshed; tiers stated honestly (RRF opt-in,
  strictly worse than cross-lingual); narrative counters/links come from selfdoc with a drift guard;
  the SKILL.md mirror has no colliding rule numbers.
- **Lows:** ё→е normalization, AUC floor, `.env*` guards, basename match, `grep -F`, RPC paths,
  `_gate_verdict(None)`, inflated_n>0, horizon, synth OOC, in-sample.

### Security
- **Ingest (H1):** `out_path` clamped to `principis_corpus/`, overwriting an existing file forbidden.
- **Secrets (M1):** denylist in corpus read-paths (including `.git/*` and key backups) + a single
  read-clamp.
- **Caps (M2):** `mc_run` n≤100k; cite batch ≤8 requests (top_k≤32, limit≤16); federation plan≤64,
  replicas≤32, timeout≤60 (+ per-item replica clamp).
- **config_set (M3):** whitelist-only `_KNOWN_CONFIG` (fail-closed).

## [0.1.0] — 2026-07-08

First public early access. Baseline: council sessions + a fail-closed fidelity contour, working
offline on pure stdlib.

### Features
- **Council session** — advisors address the user, argue with each other, deliver a synthesis and
  one step to action; an interactive "live round table" as a separate mode.
- **Fidelity contour** — markers 🔵 (verbatim quote, checked against the source) / 🟢 (commentary) /
  🟡 (a thought in the author's spirit) / 📐 (calculation); **fail-closed abstention** — off-corpus
  an advisor stays silent rather than inventing. Two-phase relevance judge-gate (the model judges,
  the code applies the threshold).
- **Moat against camouflage** — topically-close-but-non-answering text does not pass as 🔵
  (borderline-gated judge).
- **📐 Decision map + Monte Carlo** — on a computable question the council breaks the choice into
  numbers (worst/typical/best triples against anchoring) and runs a deterministic Monte Carlo (zero
  LLM in the math, seed → reproducibility); a sensitivity tornado, a mandatory "do nothing" option,
  an outcome loop (checking the forecast against fact).
- **Three search tiers** — from pure Python (lexical, tuned for Russian morphology) to semantic
  (ollama + `bge-m3`) with soft degradation; the contour is equally honest on any tier.
- **Public-domain figure catalog** + guided council assembly from the public domain (cold-start).
- **MCP server** — the whole cycle (assembly, sessions, widgets) is available as tools in any MCP host.
- **Self-documentation** — `docs/MANUAL.md` is generated from code; runtime tool `explain_self`;
  freshness guards catch drift in CI.
- **Lenses** — methods/approaches layered over personas (e.g. the grounded lens "Strategist
  (Sun Tzu, Giles 1910, PD)").

### Guarantees
- The whole suite (1000+ tests) passes **offline** — no network, ollama, external engine, or keys.
- Personal data (board, sessions, registries, `.env`) is in `.gitignore` and not part of the
  distribution.

[Unreleased]: https://github.com/ilyautov/consilium-principis/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/ilyautov/consilium-principis/releases/tag/v0.1.2
[0.1.1]: https://github.com/ilyautov/consilium-principis/releases/tag/v0.1.1
[0.1.0]: https://github.com/ilyautov/consilium-principis/releases/tag/v0.1.0
