# Awesome-list PR entries

Exact one-line entries to submit as PRs, plus PR body copy. Verify each repo's current category headings and any emoji/legend conventions right before submitting — both lists get reorganized periodically, and the entry may need to move under a specific category (e.g. "Knowledge & Memory", "Agent Frameworks", "Plugins").

---

## awesome-mcp-servers

Typical entry format: `- [name](url) - description`

**Entry:**
```
- [consilium-principis](https://github.com/ilyautov/consilium-principis) - A council of AI personas grounded in real thinkers' public-domain texts (Sun Tzu, Marcus Aurelius, Machiavelli, Epictetus). Verifies every quote character-by-character against the source corpus and honestly refuses to answer when the corpus doesn't cover the question, instead of fabricating a citation.
```

Shorter alternate, if the list enforces a strict line-length cap:
```
- [consilium-principis](https://github.com/ilyautov/consilium-principis) - Council of AI advisors grounded in public-domain texts; verifies quotes character-by-character and refuses to bluff when it can't cite a source.
```

**PR body:**
> Adds Consilium Principis, an MCP server (+ Claude Code skill) that runs a council of AI personas grounded in real public-domain texts. Its differentiator vs. other multi-agent "council" servers is verifiable grounding: every verbatim quote is checked character-by-character against the source corpus, and the advisor stays silent (fail-closed) rather than fabricate a citation when the corpus doesn't cover the question. Free, open source, MIT licensed.

---

## awesome-claude-code

Typical entry format: `- [Name](url) - Description` (check current section — likely under a "Plugins" or "Slash-Commands & Skills" heading given this ships as a Claude Code skill + plugin marketplace entry).

**Entry:**
```
- [Consilium Principis](https://github.com/ilyautov/consilium-principis) - Claude Code skill that convenes a council of AI personas of real thinkers (Sun Tzu, Marcus Aurelius, Machiavelli, Epictetus, plus your own), grounded in public-domain texts. Verifies quotes character-by-character against the source and honestly stays silent instead of fabricating when the corpus doesn't cover the question.
```

Shorter alternate:
```
- [Consilium Principis](https://github.com/ilyautov/consilium-principis) - AI advisory council skill grounded in public-domain texts; proves its quotes character-by-character or honestly refuses to bluff.
```

**PR body:**
> Adds Consilium Principis, a Claude Code skill + MCP server that runs a council of AI personas grounded in real thinkers' public-domain writings. Unlike other "AI council" tools, it verifies every verbatim quote character-by-character against the source corpus and fails closed — the advisor honestly declines to answer rather than inventing a citation when the corpus doesn't cover the question. Install via `/plugin marketplace add ilyautov/consilium-principis`; free, open source, MIT licensed.

---

## Notes for whoever submits

- Both entries should be alphabetized into their target section per each repo's existing convention — do not append to the end of the file.
- Confirm the exact repo URL and default branch name are correct at submission time (this doc assumes `github.com/ilyautov/consilium-principis`, matching the public plugin marketplace source).
- If either list requires a CONTRIBUTING.md checklist (e.g. a specific commit message format, or running a lint script), follow that repo's template — it isn't reproduced here.
