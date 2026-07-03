import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server as m

def test_situational_trio_wired_in_order():
    I = m.INSTRUCTIONS
    assert "capture_situation" in I and "situation_analyze" in I and "situation_stress_test" in I
    assert I.index("capture_situation") < I.index("situation_analyze") < I.index("situation_stress_test")

def test_outcome_loop_tools_wired():
    I = m.INSTRUCTIONS
    assert "advisor_weights" in I and "mirror_report" in I

def test_principis_onboarding_wired():
    assert "scaffold_principis" in m.INSTRUCTIONS
