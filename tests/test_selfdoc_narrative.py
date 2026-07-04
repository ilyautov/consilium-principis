import os
NARR = os.path.join(os.path.dirname(__file__), "..", "docs", "selfdoc", "narrative")

def test_five_narrative_files_present_and_nonempty():
    for name in ("00-overview.md", "10-moat.md", "20-firewall.md", "30-architecture.md", "40-extend.md"):
        p = os.path.join(NARR, name)
        assert os.path.exists(p), f"нет {name}"
        assert len(open(p, encoding="utf-8").read().strip()) > 200, f"{name} слишком короткий"

def test_narrative_has_no_private_leaks():
    forbidden = ["principis.md", "gov_heads.local.json"]
    for name in os.listdir(NARR):
        body = open(os.path.join(NARR, name), encoding="utf-8").read()
        for f in forbidden:
            assert body.count(f) == 0 or name == "20-firewall.md"
