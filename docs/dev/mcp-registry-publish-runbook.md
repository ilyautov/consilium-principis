# MCP Registry — automated release and publication runbook

Status: the repository ships a tag-driven MCPB release workflow. Registry publication
is a separate, owner-authorized post-release action because it uses GitHub OAuth and
changes the public registry.

The registry is in preview; check the current
`modelcontextprotocol.io/registry/quickstart` before publishing.

## Release contract

- The MCPB artifact is `consilium-principis.mcpb`.
- `server.json` is deliberately outside the MCPB archive: otherwise its
  `fileSha256` would have a self-referential checksum cycle.
- A successful GitHub release attaches **both** `consilium-principis.mcpb` and the
  generated, hash-complete `server.json` asset.
- The source-tree `server.json` retains its explicit checksum sentinel. The workflow
  copies it to `dist/server.json`, computes the artifact SHA-256 there, and validates
  that exact file before it is uploaded.

## Triggering and rerunning releases

- Pushing a release tag is the normal release path.
- Manual dispatch requires an existing immutable `vX.Y.Z` Git tag. It checks out and
  verifies that exact tag, then reconciles its GitHub release: a missing release is
  created, while an existing release's two assets must compare byte-for-byte with the
  newly built assets.
- Manual dispatch never overwrites release assets or moves a tag. Treat the failed
  `v0.1.1` release run as historical evidence, not as a release to overwrite.

## Before creating a tag

1. Update every version source and the release URL in source `server.json` to the
   intended `vX.Y.Z`. Do not replace the checksum sentinel in the source file.
2. Run the normal test and packaging checks. The release workflow additionally uses
   the lockfile through `npm ci`, validates `manifest.json`, packs the MCPB, runs the
   denylist guard, validates the generated registry manifest, and creates the release.
3. Create and push the version tag through the approved release process. This tag push
   is the normal release trigger. Do not use a global MCPB installation or manually
   calculate/edit the release checksum.

## Obtain the validated external registry manifest

After the tag workflow has succeeded, download the release asset—not the source-tree
placeholder:

```bash
release_tag=vX.Y.Z
release_dir=$(mktemp -d)
gh release download "$release_tag" --repo ilyautov/consilium-principis \
  --pattern server.json --dir "$release_dir"
```

`$release_dir/server.json` is the exact hash-complete manifest validated by the
workflow and uploaded alongside the MCPB. Confirm the MCPB release URL resolves
before registry publication:

```bash
curl --fail --head \
  "https://github.com/ilyautov/consilium-principis/releases/download/vX.Y.Z/consilium-principis.mcpb"
```

## Publish to MCP Registry (owner action)

Use the downloaded manifest in an otherwise empty working directory:

```bash
cd "$release_dir"
mcp-publisher login github
mcp-publisher publish
```

The OAuth login proves ownership of the `io.github.ilyautov/*` namespace. Never run
`mcp-publisher publish` with the source-tree `server.json`, because it carries the
checksum sentinel and must fail validation.

Verify the listing after publication:

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.ilyautov/consilium-principis"
```

## Open packaging decision

The bundle ships code and public data, but not a ready-built private advisor corpus.
Choose before release whether first-run fail-closed abstention is acceptable, whether
to package public-domain seed corpora, or whether to defer the MCPB listing until the
host's unpacked directory has been verified writable.
