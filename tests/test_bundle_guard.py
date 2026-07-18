import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_guard_rejects_forbidden(tmp_path):
    listing = tmp_path / "files.txt"
    listing.write_text(".env\nSKILL.md\nadvisors/some-advisor/build/corpus.jsonl\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert ".env" in r.stdout or ".env" in r.stderr

def test_guard_allows_clean(tmp_path):
    listing = tmp_path / "files.txt"
    listing.write_text("SKILL.md\nscripts/mcp_server.py\nmanifest.json\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode == 0

def test_guard_allows_pd_corpus(tmp_path):
    listing = tmp_path / "files.txt"
    listing.write_text("advisors/machiavelli/corpus.jsonl\nSKILL.md\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode == 0
