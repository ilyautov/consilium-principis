**English** · [Русский](CONNECT-MCP.md)

# Connect Consilium as an MCP server

> Release: [v0.1.0](https://github.com/ilyautov/consilium-principis/releases/download/v0.1.0/consilium-principis.mcpb)

Use Consilium either as a Claude Code skill or as an MCP server. The server exposes the board
lifecycle, fidelity checks, source-backed retrieval, decision calculations, and self-documentation.
The available MCP interface changes over time; inspect it with `tools/list` or `explain_self`.
Host-specific support remains experimental unless the host matrix says otherwise.

| Host | Connection | Result |
|---|---|---|
| **Claude Code** | skill (`python3 install.py`) | the host can run the local scripts; say “where do I start?” |
| **Claude Desktop / another MCP host** | MCP server | MCP interface; compatibility depends on the host |

See [`docs/CONNECT-HOSTS.en.md`](docs/CONNECT-HOSTS.en.md) for the tested-status matrix.

## Connect in three steps

### 0. Put the files on the same machine

The project folder must be on the machine that runs Claude Desktop or the MCP host, so personal
corpora stay local. Either download and unpack the project ZIP into `~/consilium-principis`, or run:

```bash
git clone https://github.com/ilyautov/consilium-principis ~/consilium-principis
```

### 1. Register the server

Ask a local agent to run this command, or run it in a terminal yourself:

```bash
python3 ~/consilium-principis/scripts/board.py mcp-install
```

On Windows:

```powershell
py -3 ~/consilium-principis/scripts/board.py mcp-install
```

If `py` is absent, first confirm that `python` is Python 3.10+:

```powershell
python -c "import sys; assert sys.version_info >= (3, 10)"
```

Then substitute `python` for `py -3`. Do not use the Microsoft Store `python3` alias. The installer
merges the Claude Desktop configuration without replacing neighboring servers, makes a backup, and
uses machine-specific paths. Add `--dry-run` to preview its changes. Fully restart Claude Desktop:
stdio servers do not hot reload.

### 2. Start in ordinary language

Say “where do I start?”. The board checks readiness and guides setup. If your host does not pass the
server's `initialize` instructions to the model, explicitly call `doctor` and then `seed_council`.

## Manual configuration

Generate a portable snippet from the checkout rather than editing an interpreter path by hand:

```bash
cd ~/consilium-principis
python3 scripts/board.py mcp-config
python3 scripts/board.py mcp-config --json
```

On Windows use:

```powershell
py -3 scripts/board.py mcp-config --json
```

The generated snippet follows this shape (see [`mcp.example.json`](mcp.example.json)):

```json
{ "mcpServers": { "consilium-principis": {
    "command": "python3",
    "args": ["/ABSOLUTE/PATH/TO/consilium-principis/scripts/mcp_server.py"]
} } }
```

For Claude Code CLI, registration can also be manual:

```bash
claude mcp add consilium-principis -- python3 ~/consilium-principis/scripts/mcp_server.py
```

Claude Desktop uses its configuration file (on macOS,
`~/Library/Application Support/Claude/claude_desktop_config.json`). Add the server inside the
existing `mcpServers` object; do not replace its neighboring entries. The server resolves project
paths from its own file location, not the host's working directory. A local `mcp.json` is ignored by
Git; only [`mcp.example.json`](mcp.example.json) belongs in the repository.

## Security boundary

The MCP server runs natively as a child process on your machine, outside a host sandbox, with your
user's filesystem and network permissions. That is necessary for local corpus construction and
public-domain retrieval. Keep the safety boundary in server code: only fetch lawful public-domain
material and write sources under `advisors/*/sources/` and `principis_corpus/` as the project rules
require.

## Dependencies

- **Python 3.10+** is required.
- **SIMPLE** retrieval (lexical search plus the fidelity contour) needs only Python.
- **FULL** retrieval is optional: local `ollama` plus `bge-m3`; run `setup_full` for OS-specific
  guidance. Without it, Consilium degrades to SIMPLE while the fidelity contour remains intact.
- Hybrid retrieval is opt-in; it is not a third support tier.

For host-specific caveats and Windows details, see
[`docs/CONNECT-HOSTS.en.md`](docs/CONNECT-HOSTS.en.md).
