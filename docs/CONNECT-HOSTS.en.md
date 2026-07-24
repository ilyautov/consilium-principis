**English** · [Русский](CONNECT-HOSTS.md)

# Connect to MCP hosts

> Release: [v0.1.3](https://github.com/ilyautov/consilium-principis/releases/download/v0.1.3/consilium-principis.mcpb)

The advisor logic, fidelity contour, quote gate, and decision map live in
`scripts/mcp_server.py`. It returns server instructions during the standard MCP `initialize`
handshake. That describes the protocol; it does not prove compatibility with every client. CI checks
the server and stdio protocol, not a live run of each host. Treat every host recipe below as an
experimental starting point until it has a host-specific smoke test.

General MCP setup, security, and dependencies are in [`../CONNECT-MCP.en.md`](../CONNECT-MCP.en.md).

## Host status matrix

| Host | Skill / wrapper | MCP server | Live verification |
|---|---|---|---|
| Claude Code | plugin (`/plugin marketplace add`) | yes | ⚠ experimental: no host-specific CI smoke |
| Claude Code | manual (`claude mcp add`) | yes | ⚠ experimental: no host-specific CI smoke |
| Claude Desktop | no separate skill format; MCP server exposes functionality | yes | ⚠ experimental: no host-specific CI smoke |
| Cursor | no | yes (per Cursor documentation) | ⚠ unverified on this host; confirm locally |
| Codex / OpenAI-style CLI | no | ⚠ version-dependent; see below | ⚠ unverified |
| Gemini CLI | no | ⚠ extensions/MCP configuration; see below | ⚠ unverified |
| Kimi CLI (Moonshot) | no | yes (per Kimi CLI docs, `~/.kimi/mcp.json`) | ⚠ unverified |
| Universal MCP host | no plugin format outside Claude Code | yes | ⚠ host-dependent |

“Skill” means a convenience wrapper for automatic registration and commands. The MCP server is a
separate protocol and does not require a skill format.

## Claude Code

### Plugin path

In Claude Code:

```text
/plugin marketplace add ilyautov/consilium-principis
/plugin install consilium-principis@consilium-marketplace
```

The plugin starts the server and registers the thin skill layer. Afterwards say “where do I start?”;
the concierge checks `doctor` and can seed a public-domain starter board.

### Manual MCP path

For a local checkout, register the server directly:

```bash
claude mcp add consilium-principis -- python3 ~/consilium-principis/scripts/mcp_server.py
```

Or generate a machine-specific snippet:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

## Claude Desktop

Claude Desktop does not install Claude Code plugin manifests, but it can use the MCP server directly.
On macOS its configuration file is:

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add a `consilium-principis` entry inside the existing `mcpServers` object. Prefer the generated
configuration:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
python3 ~/consilium-principis/scripts/board.py mcp-install
# append --dry-run to preview the change
```

Restart Claude Desktop completely after configuration or server-code changes; stdio servers do not
hot reload. Desktop and Cowork are not individually smoke-tested, so this configuration is not a
claim that Cowork is supported.

## Cursor

Cursor is unverified in this project. Its MCP settings are expected to accept an `mcpServers` entry
with `command` and `args`, either in a project `.cursor/mcp.json` or global settings. Generate the
server path locally instead of copying an absolute path:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

If Cursor does not forward `initialize` instructions to the model, explicitly ask it to call
`doctor` and then `seed_council`.

## Codex / OpenAI-style CLI

This integration is unverified. MCP configuration changed between Codex CLI versions, so consult the
documentation for the installed version. A typical configuration is:

```toml
[mcp_servers.consilium-principis]
command = "python3"
args = ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
```

Generate the command and path locally first. It is also unverified whether a given version forwards
server instructions automatically; if it does not, call `doctor` and `seed_council` explicitly.

## Gemini CLI

This integration is unverified. Gemini CLI may expose MCP servers through its extension or settings
configuration. Use the generated `mcpServers` snippet as a local starting point, confirm the syntax
against your version, and do not publish the result as supported until it has been smoke-tested.

The repository root ships a ready **extension manifest**, `gemini-extension.json`, that bundles the
MCP server, so Gemini can install it in one command straight from GitHub:

```bash
gemini extensions install https://github.com/ilyautov/consilium-principis
```

The extension runs `python3 ${extensionPath}/scripts/mcp_server.py` locally. On Windows change
`python3` to `py`: the Gemini manifest has no per-OS command override (its only variables are
`${extensionPath}`/`${workspacePath}`/`${/}`). The chrome defaults to Russian (a measured design
choice); for the English recipe menu add `"env": {"CONSILIUM_LANG": "en"}` to the server entry —
answers already follow the question's language, so this only switches the deterministic CLI chrome.
The manual path is an `mcpServers` entry:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

## Kimi CLI (Moonshot)

Unverified on this host. Kimi Code CLI reads MCP configuration from `~/.kimi/mcp.json` in a
format compatible with other MCP clients (an `mcpServers` key with `command`/`args`, optional
`env`) and supports stdio servers:

```json
{
  "mcpServers": {
    "consilium-principis": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
    }
  }
}
```

Generate the machine-specific path instead of hardcoding an absolute one:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config --json
```

Kimi CLI can also take the configuration ad hoc, without editing `~/.kimi/mcp.json`:

```bash
kimi --mcp-config-file /path/to/mcp.json
# or inline: kimi --mcp-config '{"mcpServers": { ... }}'
```

As with other non-Claude hosts, it is unverified whether Kimi forwards the `initialize`
instructions to the model. If the council is unaware of its protocol after connecting, ask it to
call `doctor` and then `seed_council`. On Windows use `py -3` instead of `python3`.

## Universal MCP host

Consilium uses stdio JSON-RPC MCP (`initialize` → `tools/list` → `tools/call`). A host that supports
MCP may accept the generated snippet, but each host has its own configuration and permission model:

```bash
python3 scripts/board.py mcp-config
python3 scripts/board.py mcp-config --json
```

Do not manually replace the generated interpreter path. The generator resolves
`scripts/mcp_server.py` from its own source location, which avoids a host's unspecified working
directory.

## Windows: use generated configuration

On Windows, `python3` is often unavailable in `PATH`. The configuration generator writes the exact
path to the running interpreter. Invoke it and the Desktop auto-merge with the Windows launcher:

```powershell
py -3 scripts/board.py mcp-config --json
py -3 scripts/board.py mcp-install
```

If `py` is unavailable, use `python` only after checking it is Python 3.10+:

```powershell
python -c "import sys; assert sys.version_info >= (3, 10)"
```

Do not use the Microsoft Store `python3` alias. Windows CI covers the launcher, configuration
selection, and stdio handshake, but not a live run in a specific host; treat the path as experimental.

## One command into 30+ agents (skills.sh)

`npx skills add` (the skills.sh registry, "npm for agent skills") distributes markdown skills into
dozens of hosts — Cursor, Windsurf, Cline, Codex, and others. Our **engine is an MCP server**, not
markdown, so skills.sh installs a thin **onboarding skill**, `consilium-connect`, rather than the
engine itself: it states plainly that a local server is required and walks you through connecting it
(sections above).

```bash
npx skills add ilyautov/consilium-principis/skills/consilium-connect
```

This is a discovery funnel: the agent receives "here is how to connect Consilium", not a working
council without the server. Full value comes from the connected MCP server (`doctor` →
`seed_council`).

## After connecting

Say “where do I start?” in any host. If the host does not automatically consume the server's
`initialize` instructions, request `doctor` followed by `seed_council` instead.
