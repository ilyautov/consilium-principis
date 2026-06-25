import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from engine import provenance as prov

def _write_manifest(adv, data):
    os.makedirs(os.path.join(adv, "sources"), exist_ok=True)
    json.dump(data, open(os.path.join(adv, "sources", "manifest.json"), "w", encoding="utf-8"))

def test_no_manifest_defaults_p1(tmp_path):
    adv = str(tmp_path)
    assert prov.tier_for("anything.txt", 5, adv) == "P1"

def test_source_not_in_manifest_is_fail_closed_A(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"known.txt": {"tier": "P1"}})
    assert prov.tier_for("unknown.txt", 1, adv) == "A"

def test_flat_tier_applies_whole_file(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"tarasov.txt": {"tier": "S1"}})
    assert prov.tier_for("tarasov.txt", 99, adv) == "S1"

def test_regions_assign_by_marker(tmp_path):
    adv = str(tmp_path)
    _write_manifest(adv, {"med.txt": {"tier": "P1", "regions": [
        {"tier": "B", "until": "THE FIRST BOOK"},
        {"tier": "P1", "from": "THE FIRST BOOK", "until": "APPENDIX"},
        {"tier": "S1", "from": "APPENDIX"}]}})
    lines = ["Translator intro here.", "More intro.", "THE FIRST BOOK", "Real meditation.",
             "APPENDIX", "Editor notes."]
    tiers = [prov.tier_for_line("med.txt", i, lines, adv) for i in range(len(lines))]
    assert tiers == ["B", "B", "P1", "P1", "S1", "S1"]

def test_toc_forward_reference_does_not_switch_region(tmp_path):
    # оглавление в интро упоминает APPENDIX/GLOSSARY ДО начала тела — это не должно
    # преждевременно переключить регион (секвенциальное продвижение по порядку).
    adv = str(tmp_path)
    _write_manifest(adv, {"med.txt": {"tier": "P1", "regions": [
        {"tier": "B", "until": "THE FIRST BOOK"},
        {"tier": "P1", "from": "THE FIRST BOOK", "until": "APPENDIX"},
        {"tier": "S1", "from": "APPENDIX"}]}})
    lines = ["CONTENTS  APPENDIX  GLOSSARY", "translator prose", "THE FIRST BOOK",
             "real body", "APPENDIX CORRESPONDENCE", "editor notes"]
    tiers = [prov.tier_for_line("med.txt", i, lines, adv) for i in range(len(lines))]
    assert tiers == ["B", "B", "P1", "P1", "S1", "S1"]  # TOC-APPENDIX в строке 0 НЕ прыгнул в S1
