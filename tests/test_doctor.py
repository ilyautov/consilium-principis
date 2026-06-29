import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def test_report_has_tier_line(monkeypatch, capsys):
    from engine.semantic import SemanticEngine
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    import doctor
    doctor.report()
    out = capsys.readouterr().out
    assert "SIMPLE" in out and "ollama" in out


# --- расширенный health-check (юзер с нуля: «работает ли у меня?») ---
from doctor import check_python, check_skill_installed, check_contour, summarize


def test_check_python_matches_runtime():
    c = check_python()
    assert c["name"] == "python"
    assert c["ok"] == (sys.version_info >= (3, 10))


def test_skill_installed_detects_presence_and_absence():
    with tempfile.TemporaryDirectory() as t:
        assert check_skill_installed(t)["ok"] is False
        d = os.path.join(t, "consilium-principis")
        os.makedirs(d)
        open(os.path.join(d, "SKILL.md"), "w").write("# skill")
        c = check_skill_installed(t)
        assert c["ok"] is True and "consilium-principis" in c["detail"]


def _advisor_with_corpus(tmp, chunks):
    adv = os.path.join(tmp, "advisors", "x")
    bd = os.path.join(adv, "build")
    os.makedirs(bd)
    with open(os.path.join(bd, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return adv


def test_contour_selftest_passes_on_real_p1():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor_with_corpus(t, [{"text": "Very little is needed to make a happy life indeed",
                                        "tier": "P1", "source": "med.txt"}])
        assert check_contour(adv)["ok"] is True


def test_contour_skipped_without_corpus():
    with tempfile.TemporaryDirectory() as t:
        adv = os.path.join(t, "advisors", "empty")
        os.makedirs(adv)
        c = check_contour(adv)
        assert c["ok"] is True and "пропущен" in c["detail"].lower()


def test_summarize_healthy_iff_all_ok():
    assert summarize([{"name": "a", "ok": True}, {"name": "b", "ok": True}])["healthy"] is True
    assert summarize([{"name": "a", "ok": True}, {"name": "b", "ok": False}])["healthy"] is False


def test_advisory_failure_does_not_drop_healthy():
    # MCP/in-place: skill-installed=False (advisory) НЕ роняет healthy — лишь предупреждение
    r = summarize([{"name": "python", "ok": True},
                   {"name": "skill-installed", "ok": False, "advisory": True}])
    assert r["healthy"] is True
    assert r["advisories"] and r["advisories"][0]["name"] == "skill-installed"


def test_check_skill_installed_is_advisory():
    assert check_skill_installed(skills_home="/nonexistent").get("advisory") is True
