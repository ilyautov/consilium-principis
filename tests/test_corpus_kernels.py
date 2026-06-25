import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import kernels

def test_ground_kernel_keeps_topn_above_threshold():
    kvec = [1.0, 0.0]
    p1 = [("a:1-2", [0.99, 0.14]), ("b:3-4", [0.0, 1.0]), ("c:5-6", [0.95, 0.31])]
    g = kernels.ground_kernel(kvec, p1, ground_n=2, min_cos=0.5)
    assert g == ["a:1-2", "c:5-6"]

def test_groundless_kernel_returns_empty():
    kvec = [1.0, 0.0]
    p1 = [("b:3-4", [0.0, 1.0])]               # ничего выше порога
    assert kernels.ground_kernel(kvec, p1, ground_n=3, min_cos=0.45) == []

def test_assemble_drops_groundless():
    # L2.3.1: безземельный кернел не существует
    items = [{"name": "K1", "method": "m", "grounded_in": ["a:1-2"]},
             {"name": "K2", "method": "m", "grounded_in": []}]
    kept = kernels.drop_groundless(items)
    assert [k["name"] for k in kept] == ["K1"]
