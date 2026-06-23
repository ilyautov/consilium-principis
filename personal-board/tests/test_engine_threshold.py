import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))   # ТОЛЬКО scripts/
from engine import _pick_threshold


def test_dict_form_picks_backend():
    at = {"semantic": 0.5, "lexical": 0.04}
    assert _pick_threshold(at, "semantic", 0.9) == 0.5
    assert _pick_threshold(at, "lexical", 0.9) == 0.04

def test_missing_backend_returns_default():
    assert _pick_threshold({"semantic": 0.5}, "remote", 0.7) == 0.7

def test_legacy_flat_number_maps_to_semantic():
    assert _pick_threshold(0.62, "semantic", 0.5) == 0.62
    assert _pick_threshold(0.62, "lexical", 0.04) == 0.04  # плоский не относится к lexical

def test_none_returns_default():
    assert _pick_threshold(None, "semantic", 0.5) == 0.5
