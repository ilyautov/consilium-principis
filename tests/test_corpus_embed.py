import os, sys, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import embed

def test_cosine_orthogonal_and_identical():
    assert abs(embed.cosine([1.0, 0.0], [0.0, 1.0]) - 0.0) < 1e-9
    assert abs(embed.cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

def test_cosine_is_normalized():
    # ненормированные входы → косинус, не сырой dot
    assert abs(embed.cosine([3.0, 0.0], [5.0, 0.0]) - 1.0) < 1e-9
