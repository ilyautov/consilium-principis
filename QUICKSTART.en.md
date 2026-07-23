**English** · [Русский](QUICKSTART.md)

# Quick start

> Release: [v0.1.2](https://github.com/ilyautov/consilium-principis/releases/download/v0.1.2/consilium-principis.mcpb)
> — the `.mcpb` is a single-file extension for **Claude Desktop** (Settings → Extensions → install from
> file); for Claude Code the paths below are enough, no bundle needed.

Consilium gives your AI assistant a personal board of thinkers grounded in their texts. These are
AI representations, not the people themselves. The fidelity contour verifies a 🔵 quote against the
local corpus word for word, labels a 🟡 inference, and abstains outside the corpus.

Choose one path. The first is the easiest.

## What you need

| Requirement | Why | Required? |
|---|---|---|
| **Python 3.10+** | SIMPLE lexical search and the fidelity contour (standard library only) | **yes** |
| `ollama` + `bge-m3` | FULL semantic, cross-language search | no |
| Accounts, keys, or APIs | not used | **no** |

An empty new board is normal. The board is personal: choose whom to add. Public-domain thinkers can
be seeded in one step; build modern advisors only from material you are entitled to use.

## Path 1: ask Claude to install it

1. Open **Claude Code**.
2. Give it this link: `https://github.com/ilyautov/consilium-principis`.
3. Ask: “Install this skill for me.” Claude clones the repository, runs `python3 install.py`, copies
   the skill to `~/.claude/skills/`, and runs `doctor`. Restart Claude Code afterwards.
4. Say “where do I start?”, “what can you do?”, or “convene a board about [question]”.

Other hosts are not verified merely because they can read a config. Check the experimental host
matrix in [`docs/CONNECT-HOSTS.en.md`](https://github.com/ilyautov/consilium-principis/blob/master/docs/CONNECT-HOSTS.en.md) and generate a config locally:

```bash
python3 scripts/board.py mcp-config --json
```

## Path 2: click once or run one command

1. Get the project folder (clone or ZIP) and open it.
2. Run the installer:
   - macOS: double-click [`install.command`](install.command) (first time: right-click → Open);
   - Windows: double-click [`install.bat`](install.bat);
   - Linux/macOS terminal: `./install.sh` (a wrapper around `install.py`; it never installs Python itself);
   - any terminal: `python3 install.py`; on Windows: `py install.py`.
3. The installer copies the skill to `~/.claude/skills/`, detects the retrieval tier, and runs a
   self-check. Restart Claude Code and say “where do I start?”.

Windows is experimental, not a fully tested support target. The python.org installer provides
`py.exe` and `python.exe`, not `python3.exe`; the Microsoft Store `python3` alias opens the Store.
Use `py`, not `python3`. If the plugin cannot find Python, set `CONSILIUM_PYTHON=py` before starting
Claude Code.

## Path 3: use the command line

From the project folder:

```bash
python3 scripts/board.py doctor
python3 scripts/board.py seed-council
python3 scripts/board.py recipes
```

Build an advisor from sources in one flow:

```bash
python3 scripts/board.py validate-manifest advisors/<name>
python3 scripts/board.py build-advisor advisors/<name>
python3 scripts/eval.py advisors/<name>
```

For the complete source, manifest, and validation recipe, see
[`advisors/README.md`](advisors/README.md) and [`docs/onboarding-recipe.en.md`](https://github.com/ilyautov/consilium-principis/blob/master/docs/onboarding-recipe.en.md).

## Update / uninstall

- **Update:** run the install again (`python3 install.py` or the Path 2 installer) — the machinery is
  overwritten while **your board (`advisors/`, `golden/`) is preserved** (merge, not wipe).
- **Uninstall:** installed as a plugin — `/plugin uninstall consilium-principis` in Claude Code.
  Installed via script — delete the folder `rm -rf ~/.claude/skills/consilium-principis` (Windows:
  remove `%USERPROFILE%\.claude\skills\consilium-principis`). The skill writes nothing outside it.

## Next steps

- Convene a board: “convene a board about [question]”.
- Calculate a decision: “let’s calculate which is better, X or Y”. The board builds a decision map
  and runs deterministic Monte Carlo over your inputs.
- Add an advisor or lens: ask in natural language, or use `board.py build-advisor`. Guard against an
  echo chamber with `python3 scripts/diversity_check.py advisors/<a> advisors/<b> ...`.
- Enable FULL retrieval: `python3 scripts/board.py setup-full`.
- Connect an MCP host: start with `python3 scripts/board.py mcp-config --json`. On Windows use
  `py -3 scripts/board.py mcp-config --json`; if `py` is unavailable, confirm that `python` is
  Python 3.10+ before using it. Do not use the Store `python3` alias.

The board replies in your language automatically; force it with `CONSILIUM_LANG=ru` or
`CONSILIUM_LANG=en` in the environment.

The fidelity contour travels with every answer, at any retrieval tier: 🔵 the author's words (P1/P2)
· 🟢 verbatim commentary (S1, attributed) · 🟡 an inference · 📐 a calculation (your model, not a
quote) · abstention outside the corpus.

Detailed MCP instructions are in [`CONNECT-MCP.en.md`](CONNECT-MCP.en.md); the status of each host
is in [`docs/CONNECT-HOSTS.en.md`](https://github.com/ilyautov/consilium-principis/blob/master/docs/CONNECT-HOSTS.en.md).
