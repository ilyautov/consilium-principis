"""Чистка/границы: проставить тир каждому ингест-рекорду по регионам манифеста.
Чанкинг потом не склеивает соседей разных тиров (region-boundary)."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import provenance as prov  # noqa: E402


def tag_regions(records, source: str, advisor_dir: str):
    """records: [ (loc, text), ... ] → [ {loc, text, tier}, ... ].

    Две ортогональные оси: МАКРО (регионы манифеста — где кончается вступление) и МИКРО
    (аппарат внутри тела — скобки/сноски). Микро-гейт зовём ВСЕГДА: до 2026-07-15 он жил
    только в apparatus-режиме, и у советников на `regions` сноска переводчика оставалась
    🔵-eligible (см. test_apparatus_inline_in_regions).
    """
    lines = [txt for _, txt in records]
    out = []
    for i, (loc, txt) in enumerate(records):
        tier = prov.tier_for_line(source, i, lines, advisor_dir)
        out.append({"loc": loc, "text": txt, "tier": tier})
    from .apparatus import demote_inline_apparatus
    return demote_inline_apparatus(out)


def apparatus_tier(recs, source: str, advisor_dir: str):
    """Тиринг источника с apparatus.mode=='tier': секции + инлайн-комментарий (зовёт apparatus)."""
    from .apparatus import tier_records
    man = prov.load_manifest(advisor_dir) or {}
    appa = (man.get(source) or {}).get("apparatus") or {}
    return tier_records(recs,
                        front_until=appa.get("front_until"), back_from=appa.get("back_from"),
                        front_confident=appa.get("front_confident", False),
                        back_confident=appa.get("back_confident", False),
                        inline=appa.get("inline_commentary", "bracket"))
