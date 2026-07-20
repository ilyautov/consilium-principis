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

def test_guard_catches_env_variants_and_nested(tmp_path):
    # .env* в любом вкусе ловится; basename-матч — секрет в ПОДКАТАЛОГЕ не проскальзывает
    # (раньше "sub/mcp.json" и "sub/.env.production" проходили: паттерн матчился только
    # с начала полного пути).
    listing = tmp_path / "files.txt"
    listing.write_text(".env.local\nsub/.env.production\nsub/mcp.json\nSKILL.md\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    for s in (".env.local", ".env.production", "mcp.json"):
        assert s in r.stdout

def test_guard_allows_env_templates(tmp_path):
    # публичные env-шаблоны — задокументированное исключение (и во вложении тоже)
    listing = tmp_path / "files.txt"
    listing.write_text(".env.example\nsub/.env.example\nSKILL.md\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout

def test_guard_catches_nested_mcp_json(tmp_path):
    listing = tmp_path / "files.txt"
    listing.write_text("sub/mcp.json\nSKILL.md\n")
    r = subprocess.run([sys.executable, str(ROOT/"scripts/ci_bundle_guard.py"), str(listing)],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "sub/mcp.json" in r.stdout
