#!/usr/bin/env python3
"""Validate that an MCPB artifact and its external registry manifest agree.

The registry manifest deliberately remains outside the archive: embedding it would
make its artifact checksum self-referential.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from ci_bundle_guard import offending


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/ilyautov/consilium-principis"
ARTIFACT_NAME = "consilium-principis.mcpb"
REGISTRY_NAME = "io.github.ilyautov/consilium-principis"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
TAG_RE = re.compile(r"v(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\Z")


def load_json(path, errors, label):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{label} is unreadable JSON: {error}")
        return {}


def source_versions(errors):
    """Return the repository's public version sources without external modules."""
    versions = {}
    for label, relative in (("plugin manifest", ".claude-plugin/plugin.json"),
                            ("MCPB manifest", "manifest.json")):
        document = load_json(ROOT / relative, errors, label)
        version = document.get("version")
        if isinstance(version, str):
            versions[label] = version
        else:
            errors.append(f"{label} has no string version")

    try:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"pyproject is unreadable: {error}")
    else:
        project = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", pyproject)
        match = project and re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', project.group(1))
        if match:
            versions["pyproject"] = match.group(1)
        else:
            errors.append("pyproject has no project version")

    try:
        server_source = (ROOT / "scripts/mcp_server.py").read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"MCP server source is unreadable: {error}")
    else:
        match = re.search(r'"serverInfo"\s*:\s*\{[^}]*"version"\s*:\s*"([^"]+)"', server_source)
        if match:
            versions["MCP server"] = match.group(1)
        else:
            errors.append("MCP server source has no serverInfo version")
    return versions


def artifact_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_archive_entry(filename):
    """Strip ZIP's optional ``./`` prefix without altering dotfiles."""
    while filename.startswith("./"):
        filename = filename[2:]
    return filename


def validate(tag, artifact_path, registry_path):
    errors = []
    tag_match = TAG_RE.fullmatch(tag)
    if not tag_match:
        errors.append("tag must use the form vX.Y.Z")
        tag_version = None
    else:
        tag_version = tag_match.group(1)

    if not artifact_path.is_file():
        errors.append(f"artifact does not exist: {artifact_path}")
        return errors

    registry = load_json(registry_path, errors, "registry manifest")
    if registry.get("name") != REGISTRY_NAME:
        errors.append("registry name must equal canonical server name")
    packages = registry.get("packages")
    package = packages[0] if isinstance(packages, list) and len(packages) == 1 and isinstance(packages[0], dict) else {}
    if not package:
        errors.append("registry manifest must contain exactly one package")
    elif package.get("registryType") != "mcpb":
        errors.append("registry package type must be mcpb")

    if package and package.get("transport", {}).get("type") != "stdio":
        errors.append("registry package transport must be stdio")

    registry_version = registry.get("version")
    if tag_version and registry_version != tag_version:
        errors.append("registry version must equal tag version")

    expected_url = f"{REPOSITORY}/releases/download/{tag}/{ARTIFACT_NAME}"
    if package.get("identifier") != expected_url:
        errors.append("registry package identifier must equal release URL")

    declared_sha = package.get("fileSha256")
    if not isinstance(declared_sha, str) or not SHA256_RE.fullmatch(declared_sha):
        errors.append("fileSha256 must be 64 lowercase hexadecimal characters")
    elif declared_sha != artifact_sha256(artifact_path):
        errors.append("registry fileSha256 does not match artifact SHA-256")

    versions = source_versions(errors)
    if tag_version:
        for label, version in versions.items():
            if version != tag_version:
                errors.append(f"{label} version must equal tag version")

    try:
        with zipfile.ZipFile(artifact_path) as bundle:
            entries = [normalize_archive_entry(entry.filename) for entry in bundle.infolist() if not entry.is_dir()]
            if "server.json" in entries:
                errors.append("bundle must not contain server.json")
            forbidden = offending(entries)
            if forbidden:
                errors.append("bundle contains forbidden paths: " + ", ".join(forbidden))
            try:
                bundle_manifest = json.loads(bundle.read("manifest.json"))
            except KeyError:
                errors.append("bundle is missing manifest.json")
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                errors.append(f"bundle manifest.json is invalid: {error}")
            else:
                if tag_version and bundle_manifest.get("version") != tag_version:
                    errors.append("bundle manifest version must equal tag version")
                entry_point = bundle_manifest.get("server", {}).get("entry_point")
                if not isinstance(entry_point, str) or not entry_point:
                    errors.append("bundle manifest has no server entry point")
                elif entry_point not in entries:
                    errors.append(f"bundle is missing manifest entry point: {entry_point}")
    except (OSError, zipfile.BadZipFile) as error:
        errors.append(f"artifact is not a readable MCPB ZIP: {error}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--registry-manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    errors = validate(args.tag, args.artifact, args.registry_manifest)
    if errors:
        for error in errors:
            print(f"release validation error: {error}", file=sys.stderr)
        return 1
    print("release validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
