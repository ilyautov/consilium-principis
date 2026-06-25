import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import fidelity

def test_marker_for_path_wraps_weakest_link():
    assert fidelity.marker_for_path([{"kind": "p1"}, {"kind": "kernel"}]) == "🔵"
    assert fidelity.marker_for_path([{"kind": "p1"}, {"kind": "cross_domain"}]) == "🟡"
