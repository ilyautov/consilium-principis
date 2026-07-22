"""Hermetic release-validator tests built from synthetic MCPB archives."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "release_validate.py"
VERSION = "0.1.0"
TAG = f"v{VERSION}"
RELEASE_URL = (
    "https://github.com/ilyautov/consilium-principis/releases/download/"
    f"{TAG}/consilium-principis.mcpb"
)
MANIFEST = json.dumps(
    {
        "manifest_version": "0.3",
        "name": "consilium-principis",
        "version": VERSION,
        "server": {"type": "python", "entry_point": "scripts/mcp_server.py"},
    }
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_bundle(tmp_path, entries):
    artifact = tmp_path / "consilium-principis.mcpb"
    with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, contents in entries.items():
            bundle.writestr(name, contents)
    return artifact


def write_registry(
    tmp_path,
    *,
    version=VERSION,
    sha256_value=None,
    url=RELEASE_URL,
    name="io.github.ilyautov/consilium-principis",
    registry_type="mcpb",
    transport_type="stdio",
):
    registry = tmp_path / "server.json"
    registry.write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "packages": [
                    {
                        "registryType": registry_type,
                        "identifier": url,
                        "fileSha256": sha256_value,
                        "transport": {"type": transport_type},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return registry


def run_validator(tag, artifact, registry):
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--tag",
            tag,
            "--artifact",
            str(artifact),
            "--registry-manifest",
            str(registry),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def complete_entries():
    return {
        "manifest.json": MANIFEST,
        "SKILL.md": "# Skill\n",
        "scripts/mcp_server.py": "",
    }


def test_validator_accepts_matching_registry_hash(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(tmp_path, sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode == 0, result.stderr


def test_validator_rejects_placeholder_checksum(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(tmp_path, sha256_value="REPLACE-WITH-sha256-AT-RELEASE-TIME")

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "fileSha256 must be 64 lowercase hexadecimal characters" in result.stderr


def test_validator_rejects_mismatched_checksum(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(tmp_path, sha256_value="0" * 64)

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "does not match artifact SHA-256" in result.stderr


def test_validator_rejects_version_tag_mismatch(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(tmp_path, version="0.2.0", sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "registry version must equal tag version" in result.stderr


def test_validator_rejects_registry_manifest_inside_bundle(tmp_path):
    entries = complete_entries()
    entries["server.json"] = "{}"
    artifact = make_bundle(tmp_path, entries=entries)
    registry = write_registry(tmp_path, sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "bundle must not contain server.json" in result.stderr


def test_validator_rejects_forbidden_bundle_paths(tmp_path):
    entries = complete_entries()
    entries["nested/.env.production"] = "secret"
    artifact = make_bundle(tmp_path, entries=entries)
    registry = write_registry(tmp_path, sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "bundle contains forbidden paths: nested/.env.production" in result.stderr


def test_validator_allows_dot_prefixed_mcp_config(tmp_path):
    entries = complete_entries()
    entries[".mcp.json"] = "{}"
    artifact = make_bundle(tmp_path, entries=entries)
    registry = write_registry(tmp_path, sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode == 0, result.stderr


def test_validator_rejects_missing_manifest_entry_point(tmp_path):
    entries = complete_entries()
    entries.pop("scripts/mcp_server.py")
    artifact = make_bundle(tmp_path, entries=entries)
    registry = write_registry(tmp_path, sha256_value=sha256(artifact))

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "bundle is missing manifest entry point: scripts/mcp_server.py" in result.stderr


def test_validator_rejects_wrong_release_url(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(
        tmp_path,
        sha256_value=sha256(artifact),
        url="https://example.invalid/consilium-principis.mcpb",
    )

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "registry package identifier must equal release URL" in result.stderr


def test_validator_rejects_wrong_registry_name(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(
        tmp_path, sha256_value=sha256(artifact), name="io.github.example/wrong"
    )

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "registry name must equal canonical server name" in result.stderr


def test_validator_rejects_non_mcpb_package(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(
        tmp_path, sha256_value=sha256(artifact), registry_type="npm"
    )

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "registry package type must be mcpb" in result.stderr


def test_validator_rejects_non_stdio_transport(tmp_path):
    artifact = make_bundle(tmp_path, entries=complete_entries())
    registry = write_registry(
        tmp_path, sha256_value=sha256(artifact), transport_type="http"
    )

    result = run_validator(TAG, artifact, registry)

    assert result.returncode != 0
    assert "registry package transport must be stdio" in result.stderr
