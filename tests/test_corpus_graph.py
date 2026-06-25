import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from corpusbuild import graph

def test_marker_of_by_kind():
    assert graph.marker_of({"kind": "p1"}) == "🔵"
    assert graph.marker_of({"kind": "kernel"}) == "🔵"
    assert graph.marker_of({"kind": "s1"}) == "🟢"
    assert graph.marker_of({"kind": "enrichment"}) == "🟡"
    assert graph.marker_of({"kind": "что-то-неизвестное"}) == "🟡"   # fail-closed = слабейшее

def test_weakest_link_returns_weakest_on_path():
    pure_blue = [{"kind": "p1"}, {"kind": "kernel"}]
    assert graph.weakest_link(pure_blue) == "🔵"
    via_green = [{"kind": "p1"}, {"kind": "s1"}]
    assert graph.weakest_link(via_green) == "🟢"
    via_yellow = [{"kind": "p1"}, {"kind": "s1"}, {"kind": "cross_domain"}]
    assert graph.weakest_link(via_yellow) == "🟡"

def test_assemble_graph_unifies_edges(tmp_path):
    adv = tmp_path / "adv"; (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "links.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"src": "t:1-2", "dst": "p:3-4", "type": "толкует", "weight": 0.6}) + "\n")
    with open(adv / "build" / "kernels.json", "w", encoding="utf-8") as f:
        json.dump([{"name": "K1", "grounded_in": ["p:3-4"]}], f)
    edges = graph.assemble_graph(str(adv))
    types = {e["type"] for e in edges}
    assert "толкует" in types and "заземляет" in types
