"""Чистка/границы: проставить тир каждому ингест-рекорду по регионам манифеста.
Чанкинг потом не склеивает соседей разных тиров (region-boundary)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import provenance as prov  # noqa: E402


def tag_regions(records, source: str, advisor_dir: str):
    """records: [ (loc, text), ... ] → [ {loc, text, tier}, ... ]."""
    lines = [txt for _, txt in records]
    out = []
    for i, (loc, txt) in enumerate(records):
        tier = prov.tier_for_line(source, i, lines, advisor_dir)
        out.append({"loc": loc, "text": txt, "tier": tier})
    return out
