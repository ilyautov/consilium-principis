"""Сборка графа провенанса и правило слабого звена (L2.2).
marker_of / weakest_link — чистые, ядро контура на трассе."""
import json, os
from . import paths

# 🔵 сильнее 🟢 сильнее 🟡; ранг = «слабость»
_RANK = {"🔵": 0, "🟢": 1, "🟡": 2}
_BLUE = {"p1", "p2", "kernel"}
_GREEN = {"s1", "s2", "толкование"}


def marker_of(node: dict) -> str:
    kind = node.get("kind", "")
    if kind in _BLUE:
        return "🔵"
    if kind in _GREEN:
        return "🟢"
    return "🟡"   # enrichment/cross_domain/user/неизвестное → fail-closed слабейшее


def weakest_link(path: list) -> str:
    """Маркер составного ответа = самое слабое звено на пути по графу."""
    if not path:
        return "🟡"
    return max((marker_of(n) for n in path), key=lambda m: _RANK[m])


def assemble_graph(advisor_dir: str) -> list:
    """Унифицирует links.jsonl (толкует) + kernels.json (заземляет) + enrichment.jsonl (раскрывает)
    в graph.jsonl как {src_id, dst_id, type, weight}."""
    bd = paths.build_dir(advisor_dir)
    edges = []
    lp = os.path.join(bd, "links.jsonl")
    if os.path.isfile(lp):
        with open(lp, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    l = json.loads(line)
                    edges.append({"src_id": l["src"], "dst_id": l["dst"],
                                  "type": "толкует", "weight": l.get("weight", 0.0)})
    kp = os.path.join(bd, "kernels.json")
    if os.path.isfile(kp):
        with open(kp, encoding="utf-8") as f:
            kj = json.load(f)
        for k in kj:
            for pid in k.get("grounded_in", []):
                edges.append({"src_id": k["name"], "dst_id": pid, "type": "заземляет", "weight": 1.0})
    ep = os.path.join(bd, "enrichment.jsonl")
    if os.path.isfile(ep):
        with open(ep, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if line.strip():
                    e = json.loads(line)
                    for pid in e.get("derived_from", []):
                        edges.append({"src_id": f'enrich:{i}', "dst_id": pid,
                                      "type": "раскрывает", "weight": 1.0})
    out = os.path.join(bd, "graph.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for e in edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"[graph] {advisor_dir}: {len(edges)} рёбер → {out}")
    return edges
