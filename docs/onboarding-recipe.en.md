**English** · [Русский](onboarding-recipe.md)

> **Onboarding recipe** (documentation, not a separate skill). Moved out of
> `install-skill/SKILL.md` on 2026-07-21: as a nested skill it landed deeper than
> Claude Code looks (`~/.claude/skills/*/SKILL.md`), so it never registered.

# Installing personal-board (Consilium) for a non-technical user

The skill's goal: the user says "assemble me a board" and within a few minutes has a working
council with at least one **grounded** advisor — no hand-editing JSON, no `pip install`, no
terminal. The SIMPLE tier has no dependencies: lexical retrieval and the fidelity contour
(verbatim quote verification) are pure Python standard library.

**How this differs from "a chatbot playing a sage" (and why the contour is the point):** an
advisor quotes ONLY verbatim from a verified corpus (🔵); everything else it marks as an inference
(🟡); on a question outside the corpus it honestly abstains instead of confabulating. This contour
works **on any tier, even the zero-install SIMPLE floor** — only retrieval quality degrades, not
honesty. So the "minimum kit" is an honest minimum, not a crippled one.

**Honest framing (say it on first contact):** the advisors are AI representations of thinkers based
on their public texts, **not the people themselves**. Do not pass an advisor off as the genuine
person or "revive them from the dead" — it holds the author's lens and leans on their words, but
remains a model.

**Two tiers (the skill picks at `board_init`):**
- **SIMPLE (floor)** — lexical retrieval + verbatim quote gate. Needs only Python 3.10+. Zero setup beyond the skill.
- **FULL** — semantic retrieval (bge-m3 via ollama). Needs a live ollama on the user's machine. Optional, for a large corpus.

**An empty board out of the box is normal.** `advisors/` is your personal data (gitignored); the
skill does not ship it. You assemble the council yourself — Step 3 walks you through it. Who to seat
is the user's choice.

---

## Step 0 — DETERMINE THE ENVIRONMENT (critical, don't skip)

What you can do yourself versus only guide depends on the environment. Be honest about the boundary:
do NOT promise what the environment physically cannot do.

Check: `pwd && uname -a && whoami`.

### You are in Claude Code (or a local CLI where bash = the user's real machine)

The user's home directory on their OS (macOS/Windows/Linux), not a container. You do EVERYTHING
yourself: install the skill, run `board_init`, build advisors (Step 3), run `eval`. Go 1→4.

### You are in Cowork (bash = an isolated Linux sandbox)

Sign: `uname -a` shows a Linux container, a home directory like `/home/...` or `/sessions/...`, a
username that doesn't match the real one.

**IMPORTANT — this is where we beat MCP servers:** our floor is pure Python; it needs no host
config, no ollama, no keys. So in Cowork you CAN fully assemble a working board (floor) **right in
the user's mounted folder**: `collect_* → build_advisor → persona.md → eval` all run in the sandbox.
What the sandbox CANNOT do:
- enable the **FULL tier** (ollama lives on the host) — you stay on the floor (the contour still works);
- **register the skill in the user's Claude client** for future sessions (that's on the host).

So in Cowork: build a floor board in the mounted folder here and now; for the FULL tier and a
permanent skill install, walk the user over to Claude Code / a local run. Don't pretend you enabled
semantics or registered the skill on the host if you're in the sandbox — say so plainly.

---

## Step 1 — Get the skill onto the user's machine

A sensible folder: `~/personal-board` (macOS/Linux) or `%USERPROFILE%\personal-board` (Windows).
In Cowork, the user's mounted folder.

> ⚠️ **In Cowork do NOT clone straight into the mounted folder** — the host FUSE mount doesn't
> support git file-locking (`unable to unlink '.git/config.lock': Operation not permitted`). Clone
> into the sandbox and copy WITHOUT `.git`:
> `git clone … /tmp/pb && rm -rf /tmp/pb/.git && cp -R /tmp/pb/. <folder>/`.
> You rarely need to clone again — the skill folder is just mounted.

**Installing the skill (for future sessions, locally):** copy the skill directory to where Claude
picks it up (Claude Code: `~/.claude/skills/<name>/`, or as a plugin). At minimum, work straight
from the skill folder: every script is self-contained (consumers only add `scripts/` to the path;
the engine is a package with relative imports).

Python check (needs 3.10+): `python3 --version` (Windows: `py -3 --version`). Missing → see Troubleshooting.

---

## Step 2 — Determine the tier (board_init)

`board_init` measures each advisor's corpus size, checks whether semantics is available, and writes
`board_config.json` (per-advisor tier + calibrated thresholds + chunk_chars). It breaks nothing and
is safe to re-run.

First check ollama (FULL tier). From the skill folder:
```bash
python3 -c "import sys; sys.path.insert(0,'scripts'); from engine.semantic import SemanticEngine; print('semantic:', SemanticEngine.available())"
```
- `True` → semantics available: `python3 scripts/board_init.py advisors --semantic-available true`
- `False` → floor: `python3 scripts/board_init.py advisors --semantic-available false`
  (This is NOT an error. The contour works, 🔵 quotes are verified verbatim — only retrieval accuracy drops. Want FULL? Install ollama + `ollama pull bge-m3`, then re-run this step.)

On a fresh empty board, board_init just shows 0 advisors — that's normal, go to Step 3.

---

## Step 3 — Build the first advisor (the heart; replaces "keys" in an MCP)

> ⚡ **Fast path (chassis, prefer it):**
> - Empty board → `python3 scripts/board.py seed-council` — a starter council of PD sages (Aurelius +
>   Epictetus) in one command: fetch → vetted manifest → validation → corpus → kernels → index.
> - Your own advisor → put sources in `sources/`, mark up the tier manifest, then
>   `board.py validate-manifest advisors/<slug>` (are the markers actually in the text?) →
>   `board.py build-advisor advisors/<slug>` (corpus + kernels + index in one step, graceful without ollama).
> - Don't know what to show the user → `board.py recipes` (a "what the council can do" menu).
> The manual recipe below details the same steps (useful when you need control or a non-standard case).

This is a conversational recipe. Ask: **who does the user want on the board?** (a thinker, living or
not). The grounding route then depends on who it is:

**A. Public domain (deceased, classical texts)** — Aurelius, Machiavelli, Seneca, Sun Tzu…
`collect_pd` pulls from Gutenberg/Wikisource (PD hosts are auto-confirmed). You find the URL.
```bash
python3 scripts/collect_pd.py advisors/<slug> --url <gutenberg-url> --name <source-slug>
```

**B. Living / modern** — essays, talks, posts. `collect_web` / `collect_transcript` (personal-use
gate). OR the user places **legal copies** of books in `advisors/<slug>/sources/`.
> ⚖️ **Legal boundary (load-bearing):** Consilium is an engine, not a distributor. The skill does NOT
> download copyrighted books. Public domain — freely via `collect_pd`. Copyright — only legal copies
> the user provides, in `sources/` (which is gitignored; we don't commit or redistribute others'
> texts). We seed ready-made only PD figures long deceased; a modern advisor the user assembles from
> their own legal copies (bring-your-own-corpus, not "clone anyone you like").

**C. Language.** The corpus is always in the author's AUTHENTIC language (translating the corpus
would kill verbatim). At retrieval the query is translated into the corpus language (language-
agnostic; we don't target one language). A native speaker of the user's language (their authentic
corpus is in it) → a single-language pair, best accuracy for free.

### Recipe (what you do per advisor)

1. **Collect the source** (A/B above) → `advisors/<slug>/sources/`.
2. **Build the corpus:**
   ```bash
   python3 scripts/build_advisor.py advisors/<slug> --name "<Name>" --max-quotes 40
   ```
   → `corpus.jsonl` + `quote_candidates.md` (candidates are NOISY — they include the editor's introduction; take verbatim only from the BODY).
3. **Write `advisors/<slug>/persona.md`** — not from scratch: `scaffold-persona` drops a ready skeleton, fill it in:
   ```bash
   python3 scripts/board.py scaffold-persona advisors/<slug> --name "<Name>"
   ```
   - frontmatter: `name, aliases, domains, lenses, consent_status, role_framing` (diversity judges by `lenses`/`domains` — fill them in, it's required).
   - `role_framing` — **third person** (reduces sycophancy): the advisor holds its lens and will sooner challenge than flatter.
   - sections: `## Constitution` (first person, the voice's core) · `## How it argues` · `## What it won't do (never_do)` + `never_quote` (explicitly list this figure's known FAKE quotes) · `## Quote bank` (🔵) · `## Where it challenges` (against the user's task).
4. **VERIFY EVERY quote in the bank against the contour** (this IS the moat — don't skip):
   ```bash
   python3 -c "import sys; sys.path.insert(0,'scripts'); from engine.fidelity import best_match; print(best_match('<exact quote>', 'advisors/<slug>'))"
   ```
   Returned `('P1'|'P2', source)` → mark it 🔵. `('S1'|'S2', …)` → that's **commentary** (not the author's words): at most 🟢 with the commentator's name, NEVER 🔵 in the advisor's voice. `('B'|'A', …)` (front-matter/apocryphal) or `None` → the quote is no good: fix it to the exact BODY text of the author or drop it. **NEVER mark unverified text or commentary as 🔵.** (Language-corpus trick for retrieval: search with a query in the corpus language.)
5. **Tier + config:** `python3 scripts/board_init.py advisors --semantic-available <true|false>`.
6. **If FULL tier** (large corpus + ollama): build the semantic index —
   ```bash
   python3 scripts/tier_full.py advisors/<slug>
   ```
7. **Verify:** a golden set in `scripts/golden/<slug>.{retrieval,abstention}.jsonl` (model it on the existing ones) + `python3 scripts/eval.py advisors/<slug>`.

Want more voices — repeat the recipe. Against an echo chamber: `python3 scripts/diversity_check.py`
(keeps the advisors from collapsing into one timbre).

---

## Step 4 — Verification (by demonstration, not self-report)

> Standard: success is proven by a **live run**, not by "I did everything."

1. **Which tier is active:** `python3 scripts/doctor.py` — prints FULL/SIMPLE and confirms the contour works on the floor.
2. **Contour + honesty:** `python3 scripts/eval.py advisors/<slug>` — should give `🔵 verified X/X (100%)`, CORRECTNESS with no violations, ABSTENTION with 0 hallucinations. If 🔵 isn't 100% — the bank has an unverified quote (go back to Step 3.4).
3. **A real call:** convene the advisor on a real user question — the answer should carry 🔵/🟡, and a question outside the corpus should get an honest abstention. That's the proof.

---

## Troubleshooting

**"Python not installed" / `command not found: python3`:** install Python 3.10+ from python.org. Windows — tick "Add python.exe to PATH", then a new terminal.

**Semantics unavailable / no ollama:** this is NOT a blocker. You stay on the floor — the contour and 🔵 quotes work, only retrieval accuracy drops. Want FULL: `ollama pull bge-m3`, a live ollama on :11434, re-run Step 2.

**A quote returned `None` (not 🔵):** it isn't verbatim in the corpus. Check against the source (`grep -nF "…" advisors/<slug>/sources/*.txt`), fix it to the exact text or remove it. Don't force 🔵 — that breaks the whole point.

**Quote candidates are junk (chapter titles, editor's introduction):** take verbatim only from the BODY of the work, not the translator's preface.

**Retrieval is thematically close but not exact (cross-language):** a known effect on a large, uniform cross-language corpus. The contour (🔵/abstention) doesn't suffer from it — accuracy does. Fix: retrieve with a query in the corpus language; or a native-language advisor for the user's language.

**Empty board:** that's expected on a fresh install. Build an advisor via Step 3.

**`git clone` fails in Cowork (`Operation not permitted` / `config.lock`):** FUSE mount. Clone into `/tmp`, copy without `.git` (see Step 1).

---

## Cheat sheet: what depends on the environment (anti-overpromise)

- **Claude Code / local CLI** → you do everything yourself: install the skill, build the board, FULL tier (if ollama is present), eval.
- **Cowork** → you can fully build a FLOOR board in the mounted folder (pure Python). You CANNOT: enable the FULL tier (ollama is on the host) or register the skill in the Claude client for the future — walk the user to a local run. State the boundary honestly.
