# Contributing to Consilium Principis

> **English** · [Русский](CONTRIBUTING.md)

Thanks for your interest. This is a small project held together by a few invariants; respect them and
your PR lands fast. Read the two red rules below before your first commit.

## 🚫 Two rules you must not break

### 1. Public domain only. Never copyrighted text.

The project's value is grounding personas in **genuine, legally free** texts. Only public-domain
material goes into the repository (Sun Tzu, Marcus Aurelius, Epictetus, Machiavelli, etc., usually
from [Project Gutenberg](https://www.gutenberg.org)).

- **Do not add** copyrighted books/translations, not even excerpts. Modern figures are each assembled
  by the user from **their own legal materials, locally** — that is non-negotiable and never merged.
- Your personal board (`advisors/`), sessions (`council/`), and local registries are **personal data**;
  they are in `.gitignore` and must not land in commits. Check `git status` before you push.

### 2. Fail-closed fidelity contour. Do not weaken the gate.

"The LLM reasons, the code decides." The 🔵 marker (verbatim quote) is issued **only** on code
verification, and abstaining under doubt is a feature, not a bug. A PR that makes the system cite
something unverified, softens abstention, or lets topically-close-but-non-answering text slip through
as 🔵 will be rejected. If you touch anything near the fidelity gate, attach a test proving honesty
did not regress.

## How the work is done

**TDD, every time.** Red test → minimal implementation → green → commit. Tests come before behavior,
not after. Bug fixes start with a test that reproduces the bug.

### Language and sources

English is the canonical language for commits, code, schemas, and the technical documentation
referenced as the norm. The supported Russian entry points (`README.ru.md`, `QUICKSTART.md`, and the
connection docs) are updated together with the corresponding English description: they never
retroactively translate the canon, nor promise a different install path or support level.

Corpus texts stay in their source language. Do not translate or "improve" them inside the corpus: a
translation may sit alongside as a gloss, but never replaces the source used for quote verification.

Use English Conventional Commits, e.g. `docs: clarify privacy boundary` or
`fix: reject empty source marker`.

**The offline invariant is sacred.** The whole suite must pass with no network, no ollama, no external
engine, and no keys (that is how an outside user and CI see it). Run it exactly like this:

```bash
OLLAMA_HOST=http://127.0.0.1:59999 python3 -m pytest tests/ -q
```

Or shorter: `make test`. A test that hits the network without a DI-injected fake will not pass CI.
The one known env-fragile exception is `test_ssrf_check_passes_public_blocks_private` (depends on
local DNS); a divergence there can be ignored.

**Nothing extra.** DRY, YAGNI. Do not refactor the unrelated in the same PR.

## Local setup

```bash
git clone https://github.com/ilyautov/consilium-principis
cd consilium-principis
python3 -m pip install pytest numpy      # core is stdlib; this is for tests and semantics
python3 install.py                       # self-check (copies into ~/.claude/skills/)
make test                                # offline suite
```

Only **Python 3.10+** is required. Smart cross-lingual search is optional
([ollama](https://ollama.com) + `bge-m3`); without it the contour runs on the lexical floor.

## Self-documentation must not drift

Part of the docs is generated from code (`docs/selfdoc/index.json` → `docs/MANUAL.md`, runtime tool
`explain_self`). If you add/rename a tool, rule, or test, regenerate and commit it together with the
change, or the freshness guard fails CI:

```bash
python3 scripts/gen_selfdoc.py && python3 scripts/build_manual.py
```

## Pre-PR checklist

- [ ] Zero copyrighted text; zero personal data (`advisors/`, `council/`, `.env`, `*.local.json`)
- [ ] `make test` green offline (except the env-fragile SSRF test)
- [ ] New behavior covered by a test (written BEFORE the implementation)
- [ ] If you touched the fidelity gate, a test proves honesty did not weaken
- [ ] Selfdoc regenerated if tools/rules/tests changed
- [ ] English Conventional Commit, no secrets in the diff or history

## Report a vulnerability

Not via a public issue — see [SECURITY.md](SECURITY.md).
