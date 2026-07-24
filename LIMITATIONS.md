**English** · [Русский](LIMITATIONS.ru.md)

# Known limitations

Consilium-Principis is a decision tool with a fidelity contour, not an oracle. The design
deliberately fails **closed** — when it cannot verify, it abstains rather than fabricates. That
choice has honest consequences. This page states them plainly.

## 1. Advisors are representations, not the people

Each advisor is an **AI representation of a thinker built from their public-domain texts** — it
holds the author's lens and grounds every verbatim line in their words, but it remains a model.
It is not the person, and it does not "revive" anyone. The opening curtain of a session carries
this disclaimer. Do not present an advisor as the genuine individual. (This is enforced by
Rule 16 of the server's INSTRUCTIONS and mirrored in `SKILL.md`.)

## 2. Verification depends on the host honoring the protocol

When Consilium runs as an MCP server, **you (the calling model/host) do the reasoning**; the
server supplies grounded context and verification tools. Marking a quote 🔵 (author's own words)
is permitted **only** when the `fidelity_check` / `cite` gate returned 🔵 for that exact string.
The moat therefore rests on the host obeying the protocol.

What this does **not** put at risk: safety is fail-closed. A host that skips the gate cannot
manufacture a 🔵 — it simply has no verified citation, so it must abstain or fall back to 🟡
(extrapolation). A non-compliant host loses *verification*, not *safety*: it can miss a citation,
it cannot fabricate one.

## 3. Presentation is host-dependent (widget vs prose)

In a host that exposes widget tools (e.g. Cowork's `mcp__visualize__show_widget`), a council
verdict is meant to render as a **widget**, not prose. If the host skips the widget step, the
verdict falls back to plain text/markdown. This is a **cosmetic** degradation — the fidelity
markers (🔵/🟢/🟡/📐) and abstention are carried in the content either way; only the rendering
changes.

## 4. The FULL (semantic) tier needs a pre-built index

The semantic tier (bge-m3 via ollama) reads a **pre-built index**. On the request hot-path,
`retrieve` / `cite` will **not** build a large index inline — embedding a big corpus can exceed
a host's transport timeout. When the index is missing or stale, retrieval **degrades to the
lexical floor** (the SIMPLE tier: char-n-gram matching), and says so on stderr, until you build
the index in the background:

```
build_advisor <advisor>     # one-shot: manifest gate → corpus → index → kernels
doctor                      # checks the machine, reports readiness
build_index <advisor>       # rebuild the semantic index only
```

Consequence: on a **large** corpus **without** a built index, recall is lexical-floor quality,
not semantic. Build the index first to get FULL-tier quality. (Direct/CLI calls to
`tier_full.retrieve` do still auto-build a missing index — the hot-path guard applies to the
production retrieve path used by MCP hosts.)

## 5. Cross-language retrieval

The lexical floor is same-language (character-n-gram overlap): query in the **language of the
corpus** for it to work. The semantic tier (bge-m3) is language-robust; cross-language retrieval
translates the *query* into the corpus language and never touches the corpus. A 🔵 quote is
always **verbatim in the corpus's original language** — a translated quote is no longer verbatim
and drops to 🟡. A translation may sit beside the quote as a gloss, but the gloss itself is not
🔵.

## 6. Calibration has a cold start

Advisor weighting ("who has been right *for you*"), calibrated delivery, and the outcome loop
only become meaningful once you have logged decisions and their outcomes. Until that journal
exists, the board applies defaults and cannot yet tell you whose counsel has served you well.
