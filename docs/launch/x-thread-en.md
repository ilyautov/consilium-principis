# X/Twitter launch thread — Consilium Principis (EN)

Beat structure: pain → fabricated-quote problem → the council → the differentiated aha (proves or refuses) → char-by-char verification → also-disagreement/Monte Carlo → free/local → install → CTA.

Each tweet is written to fit under 280 characters. Visual notes are suggestions, not requirements.

---

**1/**
You ask an AI for advice on a hard decision. It gives you one confident answer.

Sounds great — until it invents a quote to sound smarter, and you'd have no way to know.

[GIF: chatbot outputting a slick, fully invented "Marcus Aurelius" quote]

---

**2/**
This isn't rare. Ask any LLM to argue like Sun Tzu or Marcus Aurelius and it will happily hand you a quote they never said — fluent, plausible, and fake. No source, no way to check.

[Image: side-by-side of a real quote vs. a fabricated one, visually identical]

---

**3/**
So I built a council instead of a chatbot: Consilium Principis, a Claude Code skill. AI personas of real thinkers — Sun Tzu, Marcus Aurelius, Machiavelli, Epictetus (+ anyone you add) — grounded in their actual public-domain texts.

[Image: council table UI, four advisors seated]

---

**4/**
Here's the part every other AI council skips: every verbatim quote gets checked character-by-character against the real corpus before it's shown to you. Match → 🔵. No match → it doesn't ship as a quote.

[GIF: 🔵 badge appearing next to a verified quote, char-diff flashing]

---

**5/**
And when the corpus just doesn't cover your question, the advisor doesn't bluff — it says so. Honest silence instead of a fabricated answer. That's the whole pitch: a council that proves its quotes or admits it can't.

[GIF: on-screen refusal — "I don't have grounds to answer this from Epictetus's work"]

---

**6/**
Every competing "AI council" story is the same: N models deliberate, peer-review each other, hand you a synthesis + confidence score. None of them show you verification. None show you refusal. This is provable, not just plausible.

---

**7/**
Two more things: the lenses actually disagree with each other instead of converging into one mushy consensus. And if your question is quantifiable, you get a deterministic Monte Carlo simulation (📐), not vibes.

[Image: two advisors visibly disagreeing in the same council reply]

---

**8/**
Runs on the Claude Code agent you already have — no extra API keys, no added cost. It's a skill, not a service. Your real sessions never leave your machine.

---

**9/**
Free, open source, MIT licensed. Install:
`/plugin marketplace add ilyautov/consilium-principis`
`/plugin install consilium-principis@consilium-marketplace`

---

**10/**
Try it on your next real decision — then try asking something none of your sources actually cover, and watch it refuse instead of bluff. That moment is the whole point.

github.com/ilyautov/consilium-principis

[GIF: full sequence — verified 🔵 quote, then a clean refusal on an out-of-corpus question]
