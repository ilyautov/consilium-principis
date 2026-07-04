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

    t = (topic or "overview").strip()

    if t in ("", "overview"):
        body = _narr(root, "00-overview.md") + "\n\n" + _narr(root, "30-architecture.md")
        mm = idx["meta"]
        stat = "Тулов %d · правил %d · рецептов %d · скриптов %d · тестов %d." % (
            mm["tool_count"], mm["rule_count"], mm["recipe_count"], mm["script_count"], mm["test_count"])
        return _shell("overview", [{"title": "Что это и как устроено", "body": body + "\n\n" + stat,
                                    "source_ref": "narrative/00-overview.md;30-architecture.md"}],
                      see_also=["concept:moat", "concept:firewall", "concept:extend"])

    if ":" in t:
        kind, _, val = t.partition(":")
        kind, val = kind.strip().lower(), val.strip()
        if kind == "tool":
            hit = next((x for x in idx["tools"] if x["name"] == val), None)
            if hit:
                body = "%s\nСтатус: %s. Схема: %s.%s" % (
                    hit["description"], hit["status"], json.dumps(hit["input_schema"], ensure_ascii=False),
                    (" Упоминается: " + ", ".join(hit["referenced_in"])) if hit["referenced_in"] else "")
                return _shell(t, [{"title": "Тул `%s`" % val, "body": body, "source_ref": "index:tools/%s" % val}])
            return _shell(t, [], suggestions=[x["name"] for x in idx["tools"] if val.lower() in x["name"].lower()][:6]
                          or [x["name"] for x in idx["tools"]][:6])
        if kind == "rule":
            hit = next((r for r in idx["rules"] if str(r["n"]) == val), None)
            if hit:
                return _shell(t, [{"title": "Правило %d. %s" % (hit["n"], hit["title"]), "body": hit["text"],
                                   "source_ref": "index:rules/%s" % val}])
            return _shell(t, [], suggestions=["rule:%d" % r["n"] for r in idx["rules"]][:15])
        if kind == "recipe":
            hit = next((r for r in idx["recipes"] if r["id"] == val), None)
            if hit:
                return _shell(t, [{"title": "Рецепт %s" % val, "body": hit.get("does", ""),
                                   "source_ref": "index:recipes/%s" % val}])
            return _shell(t, [], suggestions=[r["id"] for r in idx["recipes"]][:10])
        if kind == "concept":
            fname = _CONCEPTS.get(val.lower())
            if fname:
                return _shell(t, [{"title": val, "body": _narr(root, fname),
                                   "source_ref": "narrative/%s" % fname}])
            return _shell(t, [], suggestions=["concept:%s" % k for k in _CONCEPTS])
        if kind == "term":
            hit = next((g for g in idx["glossary"] if g["term"].lower() == val.lower()), None)
            if hit:
                return _shell(t, [{"title": hit["term"], "body": hit["definition"],
                                   "source_ref": "index:glossary/%s" % hit["term"]}])
            return _shell(t, [], suggestions=[g["term"] for g in idx["glossary"]
                                              if val.lower() in g["term"].lower()][:8])

    # свободный текст → best-match по тулам/правилам/концептам/терминам
    low = t.lower()
    sug = []
    sug += ["tool:%s" % x["name"] for x in idx["tools"] if low in x["name"].lower() or low in x["description"].lower()][:5]
    sug += ["concept:%s" % k for k in _CONCEPTS if low in k or low in _narr(root, _CONCEPTS[k]).lower()[:2000]][:3]
    sug += ["term:%s" % g["term"] for g in idx["glossary"] if low in g["term"].lower()][:5]
    if sug:
        return _shell(t, [], suggestions=list(dict.fromkeys(sug))[:8])
    return _shell(t, [], suggestions=["overview", "concept:moat", "concept:architecture"])
