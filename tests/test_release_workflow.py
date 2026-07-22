"""Release workflow guards for externally verifiable MCPB assets."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_uploads_the_hash_validated_registry_manifest():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'gh release create "$GITHUB_REF_NAME" dist/consilium-principis.mcpb dist/server.json --generate-notes' in workflow
