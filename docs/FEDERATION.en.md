**English** · [Русский](FEDERATION.md)

# Federated council (Tier 2): several models in the seats

**What it is.** An optional mode where the council's roles are played not by one host model but by
several separate clients, each on its own model: Claude Code, Codex, Kimi Code, or an API key you
bring. A coordinator puts the roles in a queue, workers claim them, play the advisor on their own
model and return a raw candidate. The server assembles the council.

**Why.** One model wearing several hats makes correlated mistakes; different models catch each
other's blind spots. The server keeps the divergence instead of collapsing it into one "best"
answer: where the replies agree, divergence is low; where they split, it is flagged and you see the
argument. Our own A/B gate (2026-07-14) found a real but modest gain that shrinks as the base model
gets stronger. Treat federation as insurance against correlated error, not as a promise of higher
accuracy.

**The fidelity contour stays on the server.** A worker returns an argument and candidate quotes but
never sets 🔵/🟢/🟡 itself. On assembly the server re-checks each quote against the corpus of the
advisor whose role was played (`advisor_dir` comes from the coordinator, not the worker). A fake 🔵
is downgraded. Assembly checks that a quote is verbatim, not that it is the most relevant line (see
[LIMITATIONS §8](../LIMITATIONS.md)).

## Workers on your subscriptions

Instead of opening Codex yourself and telling it to "claim a role", the server can start workers
from the subscription CLIs you already use: `scripts/federation/sub_worker.py`, or the MCP tool
`federation_run_subscriptions`, starts one thread per installed CLI (`claude -p`, `codex exec`,
`kimi -p`). Each subscription takes exactly one replica of each role, so a fast CLI cannot take all
replicas and collapse the council into one model. Quotes are fetched by our retrieve; the server
sets 🔵.

How a call is isolated (`scripts/cli_backends.py`): argv without a shell; an empty temporary working
folder; tools off (`--tools ""`, `--sandbox read-only`, Kimi with a no-tools agent profile); MCP servers off, so the
CLI cannot start our own server and recurse; no saved sessions; secrets other than the CLI's own
auth are not passed through. A failing subscription (quota, logout, timeout) drops out and its
replica goes straight back to the queue, and the worker report names the reason.
`federation_cancel_subscriptions` stops background workers of a session.

From a terminal:

```bash
python3 scripts/federation/sub_worker.py --open --session s1 \
  --question "Should I quit my job to start a business?" \
  --advisors advisors/marcus-aurelius,advisors/machiavelli --backends claude,codex
```

Live smoke run, 2026-10-16 (Claude + Codex, Marcus Aurelius and Machiavelli, real corpora): `diversity:
full`, divergence 0.84–0.91. Claude wrote precise English search phrases and the server confirmed
🔵 lines from the authors' texts. Codex first put the author's name and book title into its search,
retrieval hit prefaces and bibliographies, and the gate downgraded them (no false 🔵). After the
prompt asked for "a phrase the author might write, without names or titles", Codex also reached 🔵
lines in the body text.

## Frame: personal, attended, for your own decisions

- Your subscriptions serve your own decisions; they are not a backend for someone else's service.
- Workers are sessions you started on your own machine.
- The default is single-machine: a local queue in `.consilium/federation.sqlite3`, never committed.
- No account pooling, no automation on anyone else's behalf. Your question goes to the providers of
  the subscriptions you chose and spends their quota ([privacy policy](../PRIVACY_POLICY.md)).

## Manual workers and leases

Any MCP client pointed at the same checkout can be a worker: `federation_claim(worker_id, roles)` →
play the `advisor_dir` → `federation_submit(worker_model=…)`, with `federation_heartbeat` while
playing. An expired lease (300 s by default) returns the role to the queue the next time anyone
claims; retries exhausted → the replica is marked dead. A role nobody played is marked
`host_single_brain` and the council `diversity: reduced`: degradation is visible, never silent.
