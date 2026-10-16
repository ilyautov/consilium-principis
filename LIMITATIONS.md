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

## 7. Subscription backends depend on third-party CLIs

The Claude Code, Codex and Kimi Code backends drive those CLIs in non-interactive mode. Their flags
and output formats are verified against claude 2.1.296, codex-cli 0.161.0 and kimi 2.0.0; a newer
CLI can change them, and a broken call fails closed (the judge falls back to the next level, a
federation worker drops out and returns its replica to the queue). A call takes roughly 5–30
seconds, so a council over subscriptions runs as a background worker, not inside one MCP call.
An exhausted quota or a logged-out CLI makes that backend drop out; the worker report names it.
Driving your own subscription from your own machine for your own decisions is the intended use;
check each provider's terms before scripting it further. Kimi Code is excluded from the relevance
judge by default (`CONSILIUM_ALLOW_KIMI_JUDGE=1` opts in), and Kimi Code was verified live only up to
the provider: the flags are accepted and an exhausted quota is reported as such, but no answer came
back because the test account had no quota left. Whether the no-tools agent profile (`tools: []`)
really disables Kimi's tools is read from Kimi's own source, not observed.

## 8. A multi-model council checks quotes, not their relevance, at assembly

When several models play the advisors (federation), the server re-checks every quote word-for-word
against the right advisor's corpus, so a model cannot hand itself a 🔵. It does not yet judge
whether a verbatim line is *on topic*: a real but loosely related line can arrive as 🔵. Treat 🔵
in federation output as "these are the author's words", not "this is the best line for your
question". Different models give more varied answers; the research does not show they give more
accurate ones.

## 9. The verdict is only as good as the scores

`council_verdict` computes the label, the spread and the caps from the advisors' scorecards; the
host cannot soften a cap. But the scores themselves are model judgments. A 7.5 is a summary of the
council's reasoning, not a probability of success.

## 10. Translations have their own copyright

The seeded authors died centuries ago, but a translation is a separate work. All seeded editions
were published before 1931 and are public domain in the US. In "life + 70" countries (EU, UK,
Russia) Lionel Giles's 1910 *Art of War* (Giles died in 1958) stays protected until the end of
2028. The catalog preview warns about it; build the corpus locally for personal use and do not
redistribute it there before 2029.
