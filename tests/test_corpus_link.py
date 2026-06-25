import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import link

def test_nearest_p1_picks_above_threshold_topm():
    s1 = ("t.txt:1-2", [1.0, 0.0])
    p1 = [("a:1-2", [0.99, 0.14]), ("b:3-4", [0.0, 1.0]), ("c:5-6", [0.95, 0.31])]
    links = link.nearest_p1(s1, p1, top_m=2, min_cos=0.5)
    dsts = [l["dst"] for l in links]
    assert dsts == ["a:1-2", "c:5-6"]          # два самых близких выше порога, по убыванию
    assert all(l["src"] == "t.txt:1-2" and l["type"] == "толкует" for l in links)

def test_nearest_p1_drops_below_threshold():
    s1 = ("t.txt:1-2", [1.0, 0.0])
    p1 = [("b:3-4", [0.0, 1.0])]               # ортогонален → cos 0 < порог
    assert link.nearest_p1(s1, p1, top_m=3, min_cos=0.45) == []
