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


def test_cli_main_runs_full_healthcheck(capsys):
    # MEDIUM #2 pre-publish: `python3 scripts/doctor.py` должен гнать ПОЛНЫЙ run_doctor
    # (контур-самотест + gov-anchor + hint), а не усечённый report() (только тир).
    import doctor
    doctor.main([])
    out = capsys.readouterr().out
    assert "contour" in out          # самотест рва виден
    assert "gov-anchor" in out       # якорь целостности виден
    assert ("Всё в порядке" in out or "требует внимания" in out)  # человеч. hint


def test_cli_main_tier_flag_keeps_legacy_report(monkeypatch, capsys):
    # Обратная совместимость: --tier по-прежнему отдаёт короткий отчёт о тире.
    from engine.semantic import SemanticEngine
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    import doctor
    doctor.main(["--tier"])
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


# ─────────────── gov-anchor: подмена советника целиком видна врачу ───────────────

def _build_under(root, name, body):
    from corpusbuild import pipeline
    adv = os.path.join(root, "advisors", name)
    os.makedirs(os.path.join(adv, "sources"))
    with open(os.path.join(adv, "sources", "x.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    pipeline.build(adv)
    return adv


def test_gov_anchor_mismatch_is_loud_failure(tmp_path):
    # Якорь есть, но голова не совпала (симуляция подмены целиком) → громкий провал по-русски.
    from doctor import check_gov_anchors
    from governance import registry_path
    root = str(tmp_path)
    _build_under(root, "sage", "Настоящий корпус советника.\n")
    with open(registry_path(root), "w", encoding="utf-8") as f:
        json.dump({"advisors/sage": {"gov_head": "0" * 64, "n": 1}}, f)
    c = check_gov_anchors(root)
    assert c["ok"] is False
    assert "подменена целиком" in c["detail"] and "advisors/sage" in c["detail"]


def test_gov_anchor_unregistered_is_warning_not_fail(tmp_path):
    # Реестра нет (старый советник) → предупреждение с шагом регистрации, здоровье не падает.
    from doctor import check_gov_anchors
    root = str(tmp_path)
    _build_under(root, "legacy", "Корпус до эпохи якорей.\n")
    c = check_gov_anchors(root)
    assert c["ok"] is True
    assert "не зарегистрирован" in c["detail"] and "freeze" in c["detail"]


def test_gov_anchor_malformed_registry_is_loud_failure(tmp_path):
    # Битый gov_heads.json → доктор кричит (детект подмены отключён), НЕ мягкое «не зарегистрирован».
    from doctor import check_gov_anchors
    from governance import registry_path
    root = str(tmp_path)
    _build_under(root, "sage", "Корпус при битом реестре.\n")
    with open(registry_path(root), "w", encoding="utf-8") as f:
        f.write('{"advisors/sage": ')                         # усечённый JSON
    c = check_gov_anchors(root)
    assert c["ok"] is False
    assert "поврежд" in c["detail"] and "gov_heads.json" in c["detail"]


def test_gov_anchor_match_is_quiet_ok(tmp_path):
    from doctor import check_gov_anchors
    from governance import freeze
    root = str(tmp_path)
    adv = _build_under(root, "sage", "Корпус с закреплённым якорем.\n")
    freeze(adv, root=root)
    c = check_gov_anchors(root)
    assert c["ok"] is True and "якорь совпал: 1" in c["detail"]
