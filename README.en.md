**English** · [Русский](README.md)

<div align="center">

<img src="assets/logo-consilium-principis.png" width="300" alt="Consilium Principis" />

# Consilium Principis

**You ask one AI — you get one confident answer. Sometimes it's off. And to sound smart, it'll even invent a quote.**

**A personal board of directors made of great minds — for your decisions.** Several thinkers at one table, each through their own lens: they argue with you and with each other. And unlike "ask an AI to roleplay a sage," they **prove the quote or honestly stay silent** — no fabrication.

Every 🔵 quote is checked against the author's genuine text **word-for-word**; what's not
in the corpus, the advisor **does not say**. This can be verified, not just taken on faith.

[![CI](https://github.com/ilyautov/consilium-principis/actions/workflows/ci.yml/badge.svg)](https://github.com/ilyautov/consilium-principis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![no extra keys · no extra cost](https://img.shields.io/badge/no%20extra%20keys%20%C2%B7%20no%20extra%20cost-success)
![MCP ready](https://img.shields.io/badge/MCP-ready-purple)

</div>

---

## What this is

**Consilium Principis is a skill for Claude Code (and an MCP server).** You install it in your AI
agent, and for any decision question it convenes a **board of AI personas of real thinkers** — Sun
Tzu, Marcus Aurelius, Machiavelli, Epictetus, and whoever else you add. Each speaks through their
own lens, from their own texts, arguing with you and with each other; at the end — a synthesis and
one concrete next step. A quantifiable question ("which is more worthwhile — X or Y") the board
doesn't eyeball — it breaks it into numbers and runs a Monte Carlo.

How this differs from "ask an AI to roleplay a sage": **verbatim quotes are checked against the
author's genuine corpus word-for-word, and outside the corpus the advisor honestly stays
silent instead of making things up** (fail-closed). This is a decision tool, not a roleplay game or
an aphorism generator. It needs no extra keys or payment — it runs on the agent you already have;
the honesty contour itself needs no network. Full offline only with local models.

## How it differs from other councils

The "several AIs deliberate" mechanic is already common. What sets Consilium apart isn't the number
of voices, but that a claim can be **re-verified** (and where it can't, the council honestly stays silent):

| | "Roleplay a sage" (one AI) | LLM-Council-style board | **Consilium** |
|---|:---:|:---:|:---:|
| Different lenses, disagreement as a feature | ± | ✅ | ✅ |
| Verbatim quote with a source | ✗ | ✗ | ✅ |
| **Quote checked verbatim against the source** | ✗ | ✗ | **✅** |
| **Honestly silent outside the corpus (fail-closed)** | ✗ | ✗ | **✅** |
| Quantifiable question → Monte Carlo (📐) | ✗ | ✗ | ✅ |
| No extra keys or payment | ± | ✗ | ✅ |

<sub>The topic isn't snake-oil: a "personal board of directors" is a mainstream HBR concept; the bet
on grounding and citation transparency was validated by Delphi ($16M from Sequoia for exactly this),
and disagreement-as-a-feature by academia (multi-persona debate, the ALCE benchmark). We differ from
the grift by rigor: a verifiable quote and an honest refusal — not "invent an aphorism in the spirit
of a great mind."</sub>

## How it looks

You ask in plain words:

> **"I'm juggling four directions at once. What should I focus on?"**

And instead of one smooth, hedge-everything answer, you get a **session** where each advisor looks from their own vantage point — and they disagree:

> **Sun Tzu** (the "Strategist" lens) 🟡 "Whoever is strong everywhere is strong nowhere. Of the four fronts, pick the one where you have the advantage, throw your weight there; hold the rest at a minimum."
>
> **Machiavelli** 🟡 "Spread thin, you're weak on every front and vulnerable on all of them. The question isn't 'what to grow' but 'what you're willing to give up' — that is the decision."
>
> **Marcus Aurelius** 🔵 "Let it be thy earnest and incessant care as a Roman and a man to perform whatsoever it is that thou art about" *(Meditations, trans. Long)* — do the thing in front of you wholly; four things at once is scattering.
> ↳ and ask him something that isn't in his texts — **he'll honestly stay silent instead of inventing a quote.**

→ Next comes the **synthesis** (where they actually agree) and **one concrete next step**. Disagreement here is a feature: you see the decision from angles you'd have missed on your own. And if the question is quantifiable ("which is more worthwhile — X or Y"), the board will offer not to argue by eye but to **calculate** (see 📐 below).

<sub>The example is illustrative. 🟡 = a thought in the author's spirit (the model reasons through their lens), 🔵 = a verbatim line with a source in the corpus. All examples are public-domain figures (Sun Tzu, Aurelius, Machiavelli, Epictetus); who sits at YOUR table is your call. Your real sessions are written to `council/` locally — and never go into git (see [technical design](docs/MANUAL.md)).</sub>

## What you can ask

No need to learn commands — say **"what can you do?"** and the board will show a menu. For example:

- **"What could go wrong with my launch?"** — a premortem: where it'll break, what to shore up in advance
- **"What would Aurelius say about burnout?"** — a single advisor, strictly from his texts
- **"Have Sun Tzu and Machiavelli argue about X"** — pit two viewpoints against each other
- **"Which is more worthwhile — going back to a salaried job or sticking with my own thing?"** — 📐 a decision map: break it into numbers and calculate (not argue by eye)
- **"Help me win this argument"** — a position breakdown like a chess engine: your moves, counters, an honest verdict
- **"Am I contradicting myself?"** — a mirror: what you say vs. what you actually choose

## Why you can trust this

This isn't "a chatbot playing sage." Every word is tagged by a **protective contour**:

The real proof isn't in the tone but in verifiability: **a verbatim quote (🔵) is checked against
the author's genuine corpus by code, word-for-word**, and carries a source. If the exact
line isn't found, the advisor honestly stays silent (fail-closed) instead of making it up. This is
what separates a decision tool from "roleplay a sage": every claim can be re-checked.

| Marker | What it means |
|:---:|---|
| 🔵 | **verbatim quote** from the author's genuine corpus — verified word-for-word, with a source |
| 🟢 | **verbatim, but from commentary/interpretation** (not in the author's own voice) — with the commentator named |
| 🟡 | **in the spirit of the author**, but not their exact words — honestly marked |
| 📐 | **calculation**: your own numbers, run through Monte Carlo — not truth, not a quote, just your own model run N times |
| *abstention* | question outside the corpus → the advisor **stays silent instead of making things up** |

Plus **different lenses, not a chorus**: each advisor keeps their own angle, and their disagreement is a working part, not a bug (you see the decision from sides you'd otherwise collapse into one). The contour runs on any machine — no internet, no keys, no cost. Only search precision can get weaker — never honesty. Under the hood, honesty is held up by a two-phase relevance gate (a model judges the candidates, code applies the threshold) — topically-close-but-not-actually-answering material won't slip through as 🔵.

## Calculate, not just discuss — the 📐 decision map

The board has two modes. The first is a **session** (discuss, challenge, synthesize). The second
kicks in on a **quantifiable** decision question ("which is more worthwhile", "is it worth it", "X
or Y"): instead of an eyeballed answer, the board breaks the choice down into a **decision map** —
options, quantities (your own numbers, elicited as three-point "worst / typical / best" estimates,
to avoid anchoring), formulas. Then — **deterministic Monte Carlo** (code does the math, zero LLM
in the calculation, same seed → same result): P(best option), a tornado sensitivity chart, what
actually drives the outcome. A "do nothing" option is mandatory. Breaking it down with a premortem
("a year passed, it failed — why?") and a 2×2 on the key uncertainties is also something the board
does. Everything under the 📐 label — sitting **next to** 🔵/🟢/🟡, never blended in: this isn't
wisdom, it's your own model, run numerically. And if you log the decision — later the board will
check the **forecast against what actually happened** (the outcome loop: calibrating your model,
not "right/wrong guess").

**By default — plainly human:** the board answers **in your language** and gives a clean bottom line without extra numbers. A 🔵 quote stays in the original (so it can be verified) + a translation alongside it. Need the full breakdown — probabilities, robustness of the position, source-by-source markup — say "show me the details."

## Installation

### Via Claude Code plugin (recommended)

In Claude Code:

> `/plugin marketplace add ilyautov/consilium-principis`
> `/plugin install consilium-principis@consilium-marketplace`

Claude Code will spin up the MCP server and register the skill. Then say **"where do I start"** —
the concierge will check readiness and assemble a starter board (Marcus Aurelius + Epictetus, public-domain).

### Or a plain install

**The simplest way — let Claude install it for you.** Open Claude Code and give it the link:

> "Install this skill for me: `https://github.com/ilyautov/consilium-principis`"

Claude will clone the repository, run `python3 install.py` (a copy lands in `~/.claude/skills/`,
self-check included) and report back. No keys, no terminal. Then say **"where do I start"** — it'll
assemble a starter board (Marcus Aurelius + Epictetus, public-domain) in a couple of minutes.

Didn't work on the first try — give Claude this verbatim:
```bash
git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
cd ~/consilium-principis && python3 install.py
```

Prefer buttons or a terminal — [`QUICKSTART.md`](QUICKSTART.md): a click-to-install
([`install.command`](install.command) / `.bat`) and the manual path.

**Cowork / Claude Desktop / any MCP host** — connect it as an MCP server and get the whole cycle
(build, sessions, widgets) via tools, without leaving your agent: [`CONNECT-MCP.md`](CONNECT-MCP.md)
(`python3 scripts/board.py mcp-config` fills in the path for you).

**All you need:** Python 3.10+. For smart cross-language search — optionally
[ollama](https://ollama.com) + `bge-m3` (the board will walk you through setting it up). The contour works without it too.

## Your board, your call

**An empty board out of the box is normal.** Who sits at the table is your call; the board is personal.
Public-domain sages (the Stoics, Sun Tzu…) are assembled with one phrase. Modern thinkers come
from materials you bring yourself.

> ⚖️ **Boundary.** Consilium is a fidelity **engine, not a content distributor** — it ships the machinery,
> you bring the sources. The skill does not download copyrighted books: public domain — freely; copyright —
> only your own legal copies, which stay on your machine. The sages we ship pre-assembled are public-domain
> figures long deceased; anyone modern you build yourself. Your board (`advisors/`) and your profile are
> personal data — they never go into the repository.

## How it's built

Under the hood is corpus search with three modes (from plain Python to semantic) and graceful
degradation. The protective contour is a separate layer on top: it checks every quote against its
source and doesn't depend on which search mode is active. So honesty is the same on any machine.
Details — [`SKILL.md`](SKILL.md) and [`docs/`](docs/superpowers/specs/).

## Technical design

The full technical manual (what this is, architecture, tool/rule reference, how to extend it):
[`docs/MANUAL.md`](docs/MANUAL.md). It's generated from code (`scripts/gen_selfdoc.py` →
`scripts/build_manual.py`); at runtime the same information is available via the MCP tool `explain_self`.

## Contributing and security

PRs are welcome — but two rules are non-negotiable: **only public-domain texts** (no copyrighted
material, not even excerpts) and **never weaken the fail-closed contour** (🔵 only via code
verification). How to set up, run the offline suite, and open a PR — [`CONTRIBUTING.md`](CONTRIBUTING.md).
Found a way to bypass the fidelity contour or a data leak — that's a first-class vulnerability,
report it privately via [`SECURITY.md`](SECURITY.md). Change history — [`CHANGELOG.md`](CHANGELOG.md).

---

<div align="center">
<sub>Consilium Principis · early access (v0.1.0) · <a href="LICENSE">MIT</a> · <a href="CONTRIBUTING.md">Contributing</a> · <a href="SECURITY.md">Security</a></sub>
</div>
