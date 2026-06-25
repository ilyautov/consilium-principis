import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def test_report_has_tier_line(monkeypatch, capsys):
    from engine.semantic import SemanticEngine
    monkeypatch.setattr(SemanticEngine, "available", staticmethod(lambda: False))
    import doctor
    doctor.report()
    out = capsys.readouterr().out
    assert "SIMPLE" in out and "ollama" in out
