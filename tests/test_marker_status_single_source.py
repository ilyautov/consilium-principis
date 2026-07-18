"""H6: единый источник маркера. Прежде маркер по тиру считался в ТРЁХ местах
(engine.fidelity нигде, Engine.fidelity_check, mcp_server._fidelity_check) — дрейф формул
= дрейф рва. Теперь один marker_status() в fidelity.py, оба вызова делегируют."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


def _corpus(tmp_path, text, tier="P1"):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    (adv / "build" / "corpus.jsonl").write_text(
        '{"text":"%s","tier":"%s"}\n' % (text, tier), encoding="utf-8")
    return str(adv)


def test_marker_status_single_source(tmp_path):
    from engine.fidelity import marker_status
    adv = _corpus(tmp_path, "fortune favors the bold indeed")
    r = marker_status("fortune favors the bold indeed", adv)
    assert r["status"] == "🔵" and r["verbatim"] is True
    assert marker_status("nope not present at all here", adv)["status"] == "🟡"


def test_marker_status_green_for_secondary(tmp_path):
    from engine.fidelity import marker_status
    adv = _corpus(tmp_path, "commentary sentence recorded here plainly", tier="S1")
    assert marker_status("commentary sentence recorded here plainly", adv)["status"] == "🟢"


def test_mcp_and_engine_delegate_to_marker_status(tmp_path):
    import mcp_server as srv
    from engine import Engine
    from engine.fidelity import marker_status
    adv = _corpus(tmp_path, "fortune favors the bold indeed")
    quote = "fortune favors the bold indeed"
    expected = marker_status(quote, adv)
    mcp_out = srv._fidelity_check(quote, adv)          # abs path → _resolve no-op
    assert mcp_out == expected

    class _E(Engine):
        def retrieve(self, q, d, top_k=3): return []
        def build_index(self, d): return {}
        def abstain_threshold(self, d): return 0.0
    fr = _E().fidelity_check(quote, adv)
    assert fr.status == expected["status"] and fr.verbatim == expected["verbatim"] and fr.source == expected["source"]
