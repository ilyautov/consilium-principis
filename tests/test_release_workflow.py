"""Release workflow guards for externally verifiable MCPB assets."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_uploads_the_hash_validated_registry_manifest():
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert ('gh release create "$GITHUB_REF_NAME" dist/consilium-principis.mcpb dist/server.json '
            '--repo "$GITHUB_REPOSITORY" --generate-notes') in workflow


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
    assert "--require-hashes -r requirements/ci-no-numpy.txt" in windows
    assert "--hash=sha256:" in normal
    assert "--hash=sha256:" not in no_numpy
    assert "--hash=sha256:" in base
