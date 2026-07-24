# Registry listings — where and how to list the server (owner runbook)

Status: owner-facing, not shipped in the runtime or the MCPB bundle. Every listing below
is a deliberate owner action performed **after** a `vX.Y.Z` release exists, not something
this repository publishes on its own.

## Moat rule for every listing

The moat is local-only execution with a bring-your-own private corpus. It survives a public
listing only if two invariants hold on every registry:

1. **The server runs on the user's machine (stdio), never on a registry's infrastructure.**
   Do not opt into any "hosted"/"remote deployment" mode where a third party would run the
   server — that would require handing them the corpus. List as a local / stdio server.
2. **Only public-domain content is ever packaged.** The MCPB bundle already excludes the
   private advisor corpus (`.mcpbignore` + `ci_bundle_guard.py`). A listing points at that
   same bundle or at the GitHub repo; it never adds a new content path.

If a registry cannot list a purely local stdio server without a hosted runtime, skip it.

## 1. Official MCP Registry (registry.modelcontextprotocol.io)

Already runbooked — see [`mcp-registry-publish-runbook.md`](mcp-registry-publish-runbook.md).
Summary: after the tag workflow uploads the hash-complete `server.json` release asset, the
owner runs `mcp-publisher login github` + `mcp-publisher publish` from that downloaded
manifest (GitHub OAuth proves the `io.github.ilyautov/*` namespace). This is the canonical
listing; the two below are third-party aggregators.

## 2. Glama (glama.ai)

Model: Glama indexes public GitHub repositories. Two owner paths, both free, no hosted runtime:

- **Submit**: fill Glama's form-based submission (server name, description, repo URL, install
  snippet, transport = `stdio`, tool count, one-line capability). Manually reviewed.
- **Claim**: authenticate to Glama with the GitHub account that owns the repo. For a personal
  repo (`ilyautov/consilium-principis`) GitHub auth alone is enough. For an org-owned repo,
  add a root `glama.json` first:

  ```json
  {
    "$schema": "https://glama.ai/mcp/schemas/server.json",
    "maintainers": ["ilyautov"]
  }
  ```

Glama does not run the server; it reads the repo. Moat-safe as long as the repo stays
public-domain-only (already enforced by the firewall + bundle guards).

## 3. Smithery (smithery.ai)

Model: Smithery supports **hosted** (`hosted_shttp` / `external_shttp`) **and local `stdio`**
deployment types, and can publish a local stdio server from an existing MCPB artifact.

Use the **local / stdio** path only — never hosted (hosted would run the server, and therefore
the corpus, on Smithery's infrastructure; see the moat rule above).

Two owner options:

- **Publish the MCPB artifact.** Point Smithery at the released
  `releases/download/vX.Y.Z/consilium-principis.mcpb`. The user's Smithery CLI pulls and runs
  it locally on their own machine; nothing executes on Smithery's infra.
- **Repo + `smithery.yaml`.** If listing from the repo, add a `smithery.yaml` declaring a
  stdio start command. Template (do **not** commit as a live root file until the listing is
  intended — keep it here as copy-paste, mirroring how the official registry publish stays
  owner-gated):

  ```yaml
  startCommand:
    type: stdio
    configSchema:
      type: object
      properties: {}
    commandFunction: |
      (config) => ({
        command: "python3",
        args: ["scripts/mcp_server.py"]
      })
  ```

  Requires Python 3.10+ on the user's machine (same dependency as every other host). Confirm
  the current `smithery.yaml` schema against Smithery's docs before listing — the format has
  changed across CLI versions.

If Smithery's local/stdio listing ever stops being possible without a hosted runtime, drop
Smithery and keep the official Registry + Glama.

## 4. Gemini CLI extensions (geminicli.com/extensions)

Model: users install with `gemini extensions install https://github.com/ilyautov/consilium-principis`.
The root `gemini-extension.json` bundles the stdio MCP server, which runs locally — moat-safe, no
hosted runtime. Windows users edit `python3` → `py` (the Gemini manifest has no per-OS override).

Owner step: to appear in the Gemini extensions gallery, register/submit the repo per Gemini CLI's
current process (check `geminicli.com/extensions`). Keep `gemini-extension.json`'s `version` in sync
with the release — the version guard (`test_versions_in_sync`) enforces it against the other manifests.

## 5. skills.sh (`npx skills add`)

Model: a markdown-skill registry (`npx skills find` / `add`) that installs into 30+ agents from a
`skills/<name>/SKILL.md` layout. Our value is the **MCP server**, not markdown, so the only thing
published here is the thin onboarding funnel `skills/consilium-connect/SKILL.md` — it tells the user
a local server is required and points at `CONNECT-HOSTS`. Never expose the operating-layer skill this
way: without the server it would reference tools that do not exist.

Users install the funnel with:

```bash
npx skills add ilyautov/consilium-principis/skills/consilium-connect
```

Owner step: submit the repo/skill to the skills.sh directory per its current process. This is a
discovery channel, not a functional listing — do not describe it as "the council in your agent".

## Order of operations

1. Cut and release `vX.Y.Z` (tag-triggered workflow builds and uploads the MCPB + `server.json`).
2. Confirm the MCPB release URL resolves (`curl --fail --head …`).
3. Publish to the official MCP Registry (runbook 1).
4. Claim/submit on Glama (2) and, if desired, list the local/stdio server on Smithery (3).
5. Every listing points at the released artifact or the public repo — never a new content path.
