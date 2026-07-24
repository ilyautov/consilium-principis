**English** · [Русский](README.ru.md)

<div align="center">

<img src="assets/logo-consilium-principis.png" width="300" alt="Consilium Principis" />

# Consilium Principis

**You ask one AI, you get one confident answer. Sometimes it's off. And to sound smart, it'll even invent a quote.**

<img src="assets/demo-refusal-en.gif" width="760" alt="Consilium refuses a fabricated quote and confirms a real one word-for-word" />

<sub>Live: a made-up "Aurelius quote" is refused; a real line is confirmed 🔵 word-for-word with its source. The verdict is computed by code on every run, not scripted.</sub>

**A personal board of directors made of great minds, for your decisions.** Several thinkers at one table, each through their own lens: they argue with you and with each other. And unlike "ask an AI to roleplay a sage," they **prove the quote or honestly stay silent**. No fabrication.

Every 🔵 quote is checked by code against the author's genuine text, **word-for-word**. What isn't
in the corpus, the advisor **does not say**. You can verify it, not just take it on faith.

[![CI](https://github.com/ilyautov/consilium-principis/actions/workflows/ci.yml/badge.svg)](https://github.com/ilyautov/consilium-principis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![no extra keys · no extra cost](https://img.shields.io/badge/no%20extra%20keys%20%C2%B7%20no%20extra%20cost-success)
![MCP ready](https://img.shields.io/badge/MCP-ready-purple)

</div>

---

## What this is

**Consilium Principis is a skill for Claude Code (and an MCP server).** You install it in your AI
agent, and for any decision question it convenes a **board of AI personas of real thinkers**: Sun
Tzu, Marcus Aurelius, Machiavelli, Epictetus, and whoever else you add. Each speaks through their
own lens, from their own texts, arguing with you and with each other. At the end you get a synthesis
and one concrete next step. A quantifiable question ("which is more worthwhile, X or Y") the board
doesn't eyeball. It breaks it into numbers and runs a Monte Carlo.

This isn't "ask an AI to roleplay a sage." Verbatim quotes (🔵) are checked against the author's
genuine corpus word-for-word, and outside the corpus the advisor honestly stays silent instead of
making things up (fail-closed). A decision tool, not a roleplay game or an aphorism generator.

One honest thing about who's at the table: these are **AI representations of thinkers, built from
their public texts, not the people themselves**. Nobody is "speaking from beyond the grave." An
advisor holds the author's lens and leans on their words, but it stays a model, and we say so
plainly instead of hiding it behind a polished delivery.

It needs no extra keys or payment: it runs on the agent you already have. The honesty contour itself
needs no network. Full offline is available only with local models.

## How it differs from other councils

The "several AIs deliberate" mechanic is already common. What sets Consilium apart isn't the number
of voices. It's that a claim can be **re-verified**, and where it can't, the council honestly stays silent:

| | "Roleplay a sage" (one AI) | LLM-Council-style board | **Consilium** |
|---|:---:|:---:|:---:|
| Different lenses, disagreement as a feature | ± | ✅ | ✅ |
| Verbatim quote with a source | ✗ | ✗ | ✅ |
| **Quote checked verbatim against the source** | ✗ | ✗ | **✅** |
| **Honestly silent outside the corpus (fail-closed)** | ✗ | ✗ | **✅** |
| Quantifiable question → Monte Carlo (📐) | ✗ | ✗ | ✅ |
| No extra keys or payment | ± | ✗ | ✅ |

<sub>The topic isn't snake-oil. A "personal board of directors" is a mainstream HBR concept; the bet
on grounding and citation transparency was validated by Delphi ($16M from Sequoia for exactly this),
and disagreement-as-a-feature by academia (multi-persona debate, the ALCE benchmark). We differ from
the grift by rigor: a verifiable quote and an honest refusal, not "invent an aphorism in the spirit
of a great mind."</sub>

## How it looks

<div align="center">

<sub>The refusal + word-for-word verification is in the demo up top. More scenarios — wrong-mouth attribution, Monte Carlo, cross-lingual: **[demo gallery →](docs/demo/gallery.md)**</sub>

</div>

You ask in plain words:

> **"I'm juggling four directions at once. What should I focus on?"**

And instead of one smooth, hedge-everything answer, you get a **session** where each advisor looks from their own vantage point, and they disagree:

> **Sun Tzu** (the "Strategist" lens) 🟡 "Whoever is strong everywhere is strong nowhere. Of the four fronts, pick the one where you have the advantage, throw your weight there; hold the rest at a minimum."
>
> **Machiavelli** 🟡 "Spread thin, you're weak on every front and vulnerable on all of them. The question isn't 'what to grow' but 'what you're willing to give up'. That is the decision."
>
> **Marcus Aurelius** 🔵 "Let it be thy earnest and incessant care as a Roman and a man to perform whatsoever it is that thou art about" *(Meditations, trans. Long)*. Do the thing in front of you wholly; four things at once is scattering.
> ↳ and ask him something that isn't in his texts, and **he'll honestly stay silent instead of inventing a quote.**

Next comes the **synthesis** (where they actually agree) and **one concrete next step**. Disagreement here is a feature: you see the decision from angles you'd have missed on your own. And if the question is quantifiable ("which is more worthwhile, X or Y"), the board will offer not to argue by eye but to **calculate** (see 📐 below).

<sub>The example is illustrative, and the advisors are AI representations built from texts, not the authors themselves. 🟡 = a thought in the author's spirit (the model reasons through their lens), 🔵 = a verbatim line with a source in the corpus. All examples are public-domain figures (Sun Tzu, Aurelius, Machiavelli, Epictetus); who sits at YOUR table is your call. Your real sessions are written to `council/` locally, and never go into git (see [technical design](docs/MANUAL.md)).</sub>

## What you can ask

No need to learn commands. Say **"what can you do?"** and the board will show a menu. For example:

- **"What could go wrong with my launch?"** a premortem: where it'll break, what to shore up in advance
- **"What would Aurelius say about burnout?"** a single advisor, strictly from his texts
- **"Have Sun Tzu and Machiavelli argue about X"** pit two viewpoints against each other
- **"Which is more worthwhile, going back to a salaried job or sticking with my own thing?"** 📐 a decision map: break it into numbers and calculate (rather than argue by eye)
- **"Help me win this argument"** a position breakdown like a chess engine: your moves, counters, an honest verdict
- **"Am I contradicting myself?"** a mirror: what you say vs. what you actually choose

## Why you can trust this

This isn't "a chatbot playing sage." Every word is tagged by a **protective contour**.

The real proof isn't in the tone but in verifiability: **a verbatim quote (🔵) is checked against
the author's genuine corpus by code, word-for-word**, and carries a source. If the exact line isn't
found, the advisor honestly stays silent (fail-closed) instead of making it up. That's what
separates a decision tool from "roleplay a sage": every claim can be re-checked.

| Marker | What it means |
|:---:|---|
| 🔵 | **verbatim quote** from the author's genuine corpus, verified word-for-word, with a source |
| 🟢 | **verbatim, but from commentary/interpretation** (not in the author's own voice), with the commentator named |
| 🟡 | **in the spirit of the author**, but not their exact words, honestly marked |
| 📐 | **calculation**: your own numbers, run through Monte Carlo; not truth, not a quote, just your own model run N times |
| *abstention* | question outside the corpus → the advisor **stays silent instead of making things up** |

Plus **different lenses, not a chorus**: each advisor keeps their own angle, and their disagreement is a working part, not a bug (you see the decision from sides you'd otherwise collapse into one). The contour runs on any machine, no internet, no keys, no cost. Only search precision can get weaker; honesty never does. Under the hood, honesty is held up by a two-phase relevance gate (a model judges the candidates, code applies the threshold): topically-close-but-not-actually-answering material won't slip through as 🔵. The judge is *independent* only with a local (ollama) or API backend; on the default keys-free path the host model self-judges (an interested party), which `doctor` labels honestly — and the verbatim 🔵 gate never depends on it.

## Calculate, not just discuss: the 📐 decision map

The board has two modes. The first is a **session** (discuss, challenge, synthesize). The second
kicks in on a **quantifiable** decision question ("which is more worthwhile", "is it worth it", "X
or Y"): instead of an eyeballed answer, the board breaks the choice down into a **decision map**,
that is options, quantities (your own numbers, elicited as three-point "worst / typical / best"
estimates, to avoid anchoring), and formulas. Then comes **deterministic Monte Carlo** (code does
the math, zero LLM in the calculation, same seed gives the same result): P(best option), a tornado
sensitivity chart, what actually drives the outcome. A "do nothing" option is mandatory. Breaking it
down with a premortem ("a year passed, it failed, why?") and a 2×2 on the key uncertainties is also
something the board does. Everything sits under the 📐 label, **next to** 🔵/🟢/🟡 but never blended
in: this isn't wisdom, it's your own model, run numerically. And if you log the decision, later the
board will check the **forecast against what actually happened** (the outcome loop: calibrating your
model, not "right or wrong guess").

**By default, plainly human:** the board answers **in your language** and gives a clean bottom line without extra numbers. A 🔵 quote stays in the original (so it can be verified), with a translation alongside it. Need the full breakdown (probabilities, robustness of the position, source-by-source markup), just say "show me the details."

## Installation

### Via Claude Code plugin (recommended)

In Claude Code:

> `/plugin marketplace add ilyautov/consilium-principis`
> `/plugin install consilium-principis@consilium-marketplace`

Claude Code will spin up the MCP server and register the skill. Then say **"where do I start"**, and
the concierge will check readiness and assemble a starter board (Marcus Aurelius and Epictetus, public-domain).

### Or a plain install

**The simplest way, let Claude install it for you.** Open Claude Code and give it the link:

> "Install this skill for me: `https://github.com/ilyautov/consilium-principis`"

Claude will clone the repository, run `python3 install.py` (a copy lands in `~/.claude/skills/`,
self-check included) and report back. No keys, no terminal. Then say **"where do I start"**, and it'll
assemble a starter board (Marcus Aurelius and Epictetus, public-domain) in a couple of minutes.

Didn't work on the first try? Give Claude this verbatim:
```bash
git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
cd ~/consilium-principis && python3 install.py
```

Prefer buttons or a terminal? See [`QUICKSTART.en.md`](QUICKSTART.en.md): a click-to-install ([`install.command`](install.command) / `.bat`) and the manual path.

### Or the Claude Desktop bundle

The [release](https://github.com/ilyautov/consilium-principis/releases/latest) ships a single-file
`.mcpb` bundle — a Claude Desktop extension. Download it, then in Claude Desktop open **Settings →
Extensions → install from file**. Claude Code users don't need it; the paths above are enough. Wiring
details for other MCP hosts are in [`CONNECT-MCP.en.md`](CONNECT-MCP.en.md).

To **update**, re-run the install (it merges, preserving your `advisors/` board). To **uninstall**:
if you installed as a plugin, run `/plugin uninstall consilium-principis` in Claude Code; if you
installed via script, delete `~/.claude/skills/consilium-principis`.

**Claude Desktop or another MCP host:** the server exposes its cycle (build, sessions, widgets) as
tools. Host compatibility varies; see the tested-status table in
[`docs/CONNECT-HOSTS.en.md`](docs/CONNECT-HOSTS.en.md), then generate the portable configuration from the checkout with
`python3 scripts/board.py mcp-config --json`.

**All you need:** Python 3.10+. For smart cross-language search, optionally
[ollama](https://ollama.com) with `bge-m3` (the board will walk you through setting it up). The contour works without it too.

### Windows

Windows is not yet an end-to-end tested support target. `install.bat` and the mcpb bundle contain a
Windows launcher path, but please treat it as experimental and report the result through
[Support](SUPPORT.md). Two Windows-specific things worth knowing:

- **In a terminal, use `py install.py`** (not `python3 install.py`). The python.org installer ships `py.exe` and `python.exe`, but no `python3.exe`; the `python3.exe` you may see under the Microsoft Store is an App Execution Alias stub that just opens the Store instead of running.
- **Plugin can't find Python?** Set `CONSILIUM_PYTHON=py` in your environment before launching Claude Code. The plugin's server command defaults to `python3` and honors this override. (The Claude Desktop path needs nothing — `board.py mcp-config` writes the exact interpreter for you.)
- **MCP configuration:** run `py -3 scripts/board.py mcp-config --json` (or `py -3 scripts/board.py mcp-install` for Claude Desktop). If `py` is absent, use `python` only after confirming it is Python 3.10+; do not use the Store `python3` alias. See [`CONNECT-MCP.en.md`](CONNECT-MCP.en.md) for the exact fallback.

## Your board, your call

**An empty board out of the box is normal.** Who sits at the table is your call; the board is personal.
Public-domain sages (the Stoics, Sun Tzu) are assembled with one phrase. Modern thinkers come
from materials you bring yourself.

> ⚖️ **Boundary.** Consilium is a fidelity **engine, not a content distributor**: it ships the machinery,
> you bring the sources. The skill does not download copyrighted books. Public domain is taken freely;
> copyright means only your own legal copies, which stay on your machine. The sages we ship pre-assembled
> are public-domain figures long deceased; anyone modern you build yourself. Your board (`advisors/`) and
> your profile are personal data; they never go into the repository.

## How it's built

Search has two support tiers: **SIMPLE** is the standard-library lexical floor; **FULL** adds
Ollama with `bge-m3` for semantic cross-language search. **Hybrid** retrieval is opt-in, not a
third support tier. The protective contour is separate: it checks every quote against its source
regardless of the selected tier. Details in [`SKILL.md`](SKILL.md) *(in Russian)* and the generated [`docs/MANUAL.md`](docs/MANUAL.md) *(in Russian)*.

## Technical design

The full technical manual (what this is, architecture, tool/rule reference, how to extend it) lives
in [`docs/MANUAL.md`](docs/MANUAL.md). It's generated from code (`scripts/gen_selfdoc.py` →
`scripts/build_manual.py`); at runtime the same information is available via the MCP tool `explain_self`.

## FAQ

**What is Consilium Principis?**
Consilium Principis is an open-source AI advisory board — a skill for Claude Code and an MCP server —
that convenes a panel of AI personas of real thinkers (Sun Tzu, Marcus Aurelius, Machiavelli,
Epictetus, and any you add) to reason through a decision. Its distinguishing feature is a fidelity
contour: every verbatim quote is verified against the author's genuine text, or the advisor abstains.

**How does it verify quotes?**
Each 🔵 quote is checked by code against the author's public-domain corpus, word-for-word. If a claim
isn't found in the source text, the advisor does not present it as a quote — it stays silent
(fail-closed) rather than inventing one. You re-verify it, not take it on faith.

**How is this different from asking an AI to roleplay a sage?**
A roleplay chatbot will happily fabricate a plausible-sounding quote. Consilium either proves the
quote against the real text or declines to attribute it. Disagreement between advisors is a feature,
not a bug: each speaks through a different lens.

**Does it need an API key or extra payment?**
No. It runs on the AI agent you already have (Claude Code). The verification contour needs no network;
full offline operation is available only if you add local models.

**Which thinkers are included, and can I add my own?**
Public-domain figures (the Stoics, Sun Tzu, Machiavelli) are assembled from their own texts with one
phrase. You can add any advisor yourself from public-domain or your own legal materials, which stay on
your machine — the repository ships only the machinery, never copyrighted sources.

**Is it free and open-source?**
Yes. It is MIT-licensed and open-source. Install with `/plugin marketplace add ilyautov/consilium-principis`.

## Contributing and security

PRs are welcome, but two rules are non-negotiable: **only public-domain texts** (no copyrighted
material, not even excerpts) and **never weaken the fail-closed contour** (🔵 only via code
verification). How to set up, run the offline suite, and open a PR is in [`CONTRIBUTING.en.md`](CONTRIBUTING.en.md).
Found a way to bypass the fidelity contour or a data leak? That's a first-class vulnerability,
report it privately via [`SECURITY.md`](SECURITY.md). Support and project governance are in
[`SUPPORT.md`](SUPPORT.md) and [`GOVERNANCE.md`](GOVERNANCE.md); change history is in
[`CHANGELOG.md`](CHANGELOG.md).

---

<div align="center">
<sub>Consilium Principis · early access (v0.1.3) · <a href="https://github.com/ilyautov/consilium-principis/releases/download/v0.1.3/consilium-principis.mcpb">release artifact</a> · <a href="LICENSE">MIT</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="SECURITY.md">Security</a></sub>
</div>
