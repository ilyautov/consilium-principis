#!/usr/bin/env python3
"""selfdoc_query.py — детерминированный движок explain_self. Читает docs/selfdoc/index.json +
narrative/*.md, возвращает ФАКТЫ с source_ref (хост нарратит). Fail-closed на неизвестном topic."""
import os, json, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_CONCEPTS = {"overview": "00-overview.md", "moat": "10-moat.md", "firewall": "20-firewall.md",
             "architecture": "30-architecture.md", "extend": "40-extend.md"}


def _load_index(root):
    p = os.path.join(root, "docs", "selfdoc", "index.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _narr(root, fname):
    p = os.path.join(root, "docs", "selfdoc", "narrative", fname)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def _shell(topic, sections, see_also=None, suggestions=None):
    return {"kind": "self_explanation", "topic": topic or "overview", "sections": sections,
            "see_also": see_also or [], "suggestions": suggestions or []}


def explain(topic, root=None):
    root = root or ROOT
    idx = _load_index(root)
    if idx is None:
        return _shell(topic, [], suggestions=["запусти scripts/gen_selfdoc.py — индекс отсутствует/битый"])

    t = (topic if isinstance(topic, str) and topic else "overview").strip()

    if t in ("", "overview"):
        body = _narr(root, "00-overview.md") + "\n\n" + _narr(root, "30-architecture.md")
        mm = idx.get("meta", {})
        stat = "Тулов %d · правил %d · рецептов %d · скриптов %d · тестов %d." % (
            mm.get("tool_count", 0), mm.get("rule_count", 0), mm.get("recipe_count", 0),
            mm.get("script_count", 0), mm.get("test_count", 0))
        return _shell("overview", [{"title": "Что это и как устроено", "body": body + "\n\n" + stat,
                                    "source_ref": "narrative/00-overview.md;30-architecture.md"}],
                      see_also=["concept:moat", "concept:firewall", "concept:extend"])

    if ":" in t:
        kind, _, val = t.partition(":")
        kind, val = kind.strip().lower(), val.strip()
        if kind == "tool":
            hit = next((x for x in idx.get("tools", []) if x["name"] == val), None)
            if hit:
                referenced_in = hit.get("referenced_in", [])
                body = "%s\nСтатус: %s. Схема: %s.%s" % (
                    hit.get("description", ""), hit.get("status", ""),
                    json.dumps(hit.get("input_schema", {}), ensure_ascii=False),
                    (" Упоминается: " + ", ".join(referenced_in)) if referenced_in else "")
                return _shell(t, [{"title": "Тул `%s`" % val, "body": body, "source_ref": "index:tools/%s" % val}])
            return _shell(t, [], suggestions=[x["name"] for x in idx.get("tools", []) if val.lower() in x["name"].lower()][:6]
                          or [x["name"] for x in idx.get("tools", [])][:6])
        if kind == "rule":
            hit = next((r for r in idx.get("rules", []) if str(r.get("n")) == val), None)
            if hit:
                n = hit.get("n", "?")
                return _shell(t, [{"title": "Правило %s. %s" % (n, hit.get("title", "")), "body": hit.get("text", ""),
                                   "source_ref": "index:rules/%s" % val}])
            return _shell(t, [], suggestions=["rule:%s" % r.get("n") for r in idx.get("rules", [])][:15])
        if kind == "recipe":
            hit = next((r for r in idx.get("recipes", []) if r["id"] == val), None)
            if hit:
                return _shell(t, [{"title": "Рецепт %s" % val, "body": hit.get("does", ""),
                                   "source_ref": "index:recipes/%s" % val}])
            return _shell(t, [], suggestions=[r["id"] for r in idx.get("recipes", [])][:10])
        if kind == "concept":
            fname = _CONCEPTS.get(val.lower())
            if fname:
                return _shell(t, [{"title": val, "body": _narr(root, fname),
                                   "source_ref": "narrative/%s" % fname}])
            return _shell(t, [], suggestions=["concept:%s" % k for k in _CONCEPTS])
        if kind == "term":
            hit = next((g for g in idx.get("glossary", []) if g["term"].lower() == val.lower()), None)
            if hit:
                return _shell(t, [{"title": hit.get("term", val), "body": hit.get("definition", ""),
                                   "source_ref": "index:glossary/%s" % hit.get("term", val)}])
            return _shell(t, [], suggestions=[g["term"] for g in idx.get("glossary", [])
                                              if val.lower() in g["term"].lower()][:8])

    # свободный текст → best-match по тулам/правилам/концептам/терминам
    low = t.lower()
    sug = []
    sug += ["tool:%s" % x["name"] for x in idx.get("tools", []) if low in x["name"].lower() or low in x.get("description", "").lower()][:5]
    sug += ["concept:%s" % k for k in _CONCEPTS if low in k or low in _narr(root, _CONCEPTS[k]).lower()[:2000]][:3]
    sug += ["term:%s" % g["term"] for g in idx.get("glossary", []) if low in g["term"].lower()][:5]
    if sug:
        return _shell(t, [], suggestions=list(dict.fromkeys(sug))[:8])
    return _shell(t, [], suggestions=["overview", "concept:moat", "concept:architecture"])
