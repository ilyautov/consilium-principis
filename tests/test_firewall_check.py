import shutil
import subprocess
from pathlib import Path


def test_firewall_check_accepts_clean_repo_with_only_allowed_advisors(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts" / "firewall_check.sh"
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[1] / "scripts" / "firewall_check.sh", script)
    advisors = repo / "advisors"
    advisors.mkdir()
    (advisors / "README.md").write_text("# advisors\n", encoding="utf-8")
    for name in ("machiavelli", "marcus-aurelius", "sun-tzu"):
        (advisors / name).mkdir()

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "scripts/firewall_check.sh", "advisors/README.md"],
                   cwd=repo, check=True)
    result = subprocess.run(["sh", "scripts/firewall_check.sh"], cwd=repo,
                            text=True, capture_output=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "firewall-check: OK" in result.stdout


def test_firewall_check_accepts_clean_repo_without_advisors_directory(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts" / "firewall_check.sh"
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[1] / "scripts" / "firewall_check.sh", script)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "scripts/firewall_check.sh"], cwd=repo, check=True)
    result = subprocess.run(["sh", "scripts/firewall_check.sh"], cwd=repo,
                            text=True, capture_output=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "firewall-check: OK" in result.stdout


def test_firewall_check_fails_closed_when_advisors_cannot_be_listed(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts" / "firewall_check.sh"
    script.parent.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parents[1] / "scripts" / "firewall_check.sh", script)
    advisors = repo / "advisors"
    advisors.mkdir()

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "scripts/firewall_check.sh"], cwd=repo, check=True)
    advisors.chmod(0)
    try:
        result = subprocess.run(["sh", "scripts/firewall_check.sh"], cwd=repo,
                                text=True, capture_output=True)
    finally:
        advisors.chmod(0o755)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "advisors" in result.stdout
