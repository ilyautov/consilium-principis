---
name: consilium-connect
description: >
  Onboarding funnel for Consilium-Principis — a personal board of AI personas of real thinkers
  (Sun Tzu, Marcus Aurelius, Epictetus, Machiavelli, plus your own legal figures) with a
  fail-closed fidelity contour, grounded in public-domain texts. This skill does NOT contain the
  advisor engine — that lives in a local MCP server. Use it to wire up that server in your agent,
  then convene the board. Trigger with: "connect consilium", "set up the board", "council of
  advisors setup". In Russian: «подключить консилиум», «настроить совет».
---

# Consilium-Principis — connect the server (onboarding)

**Important, read first.** This markdown skill is a *funnel*, not the product. The advisor logic —
the fidelity contour (🔵 verbatim / 🟢 commentary / 🟡 extrapolation / 📐 calculation), fail-closed
abstention, the quote gate, the council choreography, and every tool — lives in a **local MCP
server** (`scripts/mcp_server.py`), not in this file. Installed on its own via `npx skills add`,
this skill has no tools to call yet. Its whole job is to get you to the server.

Do not fabricate advisor answers or pretend the tools exist. If the MCP server is not connected,
say so and walk the user through connecting it.

## What to do

1. **Get the code.** Clone or install the project:

   ```bash
   git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
   cd ~/consilium-principis
   python3 install.py        # or run in place; Python 3.10+
   ```

2. **Wire the MCP server into this agent.** Generate a machine-correct config snippet:

   ```bash
   python3 scripts/board.py mcp-config --json   # on Windows: py -3 ...
   ```

   Then paste it into your host's MCP configuration. Host-by-host recipes (Claude Code, Claude
   Desktop, Cursor, Codex, Gemini CLI, Kimi CLI, and any universal MCP host) are in
   [`docs/CONNECT-HOSTS.md`](https://github.com/ilyautov/consilium-principis/blob/master/docs/CONNECT-HOSTS.md).

3. **Convene.** Once the server is connected, say **"where do I start"**. The server's
   INSTRUCTIONS (delivered over the MCP `initialize` handshake) take over: it checks readiness
   (`doctor`) and seeds a starter board (`seed_council`: Marcus Aurelius and Epictetus,
   public-domain). If your host does not forward `initialize` instructions automatically, ask the
   agent to call the `doctor` and `seed_council` tools explicitly.

## Why a separate MCP server

The moat is local execution with a bring-your-own private corpus: nothing runs on anyone else's
infrastructure, and only public-domain content is ever packaged. A markdown-only skill cannot carry
that guarantee — it can only point you at the server that enforces it.
