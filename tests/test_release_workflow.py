"""Release workflow guards for externally verifiable MCPB assets."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_uploads_the_hash_validated_registry_manifest():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert ('gh release create "$RELEASE_TAG" dist/consilium-principis.mcpb dist/server.json '
            '--repo "$GITHUB_REPOSITORY" --generate-notes') in workflow


def test_release_requires_an_explicit_manual_tag_and_checks_out_that_tag():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:\n    inputs:\n      tag:" in workflow
    assert "description: Existing vX.Y.Z tag to build and publish/reconcile" in workflow
    assert "required: true" in workflow
    assert "type: string" in workflow
    assert "RELEASE_TAG: ${{ inputs.tag || github.ref_name }}" in workflow
    assert "ref: ${{ inputs.tag || github.ref_name }}" in workflow


def test_release_checks_out_and_verifies_the_requested_tag_commit():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'git rev-parse "refs/tags/$RELEASE_TAG^{commit}"' in workflow
    assert "git rev-parse HEAD" in workflow


def test_release_uses_its_resolved_tag_for_registry_and_validation():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'python3 - "$RELEASE_TAG"' in workflow
    assert '--tag "$RELEASE_TAG"' in workflow


def test_release_rerun_validates_immutable_existing_assets_without_repacking_them():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'if gh release view "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then' in workflow
    assert 'gh release download "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" \\' in workflow
    assert workflow.count("uses: actions/checkout@") == 2
    assert "python3 scripts/release_validate.py \\" in workflow
    assert '--artifact "$release_dir/consilium-principis.mcpb"' in workflow
    assert '--registry-manifest "$release_dir/server.json"' in workflow
    assert "cmp --silent" not in workflow
    assert "--clobber" not in workflow


def test_release_verifies_runtime_before_publishing():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "python -m pytest tests/ -q" in workflow
    assert "git ls-files '*.py' | xargs -r python -m py_compile" in workflow
    assert "python -m pytest tests/test_plugin_manifests.py -q" in workflow
    assert "Smoke-test packed MCP server" in workflow
    assert '"method": "initialize"' in workflow
    assert '"method": "tools/list"' in workflow


def test_release_write_token_is_limited_to_publish_job():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "build:" in workflow
    assert "publish:" in workflow
    assert workflow.count("contents: write") == 1
    assert "contents: read" in workflow


def test_ci_uses_hash_locked_dependency_sets():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    windows = (ROOT / ".github/workflows/windows.yml").read_text(encoding="utf-8")
    requirement_paths = [
        ROOT / "requirements/ci.txt",
        ROOT / "requirements/ci-no-numpy.txt",
        ROOT / "requirements/ci-base.txt",
    ]
    assert all(path.is_file() for path in requirement_paths)
    normal, no_numpy, base = (path.read_text(encoding="utf-8") for path in requirement_paths)

    assert "--require-hashes -r requirements/ci.txt" in ci
    assert "--require-hashes -r requirements/ci-no-numpy.txt" in ci
    assert "--require-hashes -r requirements/ci.txt" in windows
    assert "--hash=sha256:" in normal
    assert "--hash=sha256:" not in no_numpy
    assert "--hash=sha256:" in base
