#!/usr/bin/env python3
"""gen_selfdoc.py — интроспектор живого кода → docs/selfdoc/index.json.
Единый источник правды для docs/MANUAL.md и тула explain_self. Ноль сети/движка.
Запуск: python scripts/gen_selfdoc.py  (перезаписывает index.json)."""
import os, sys, json, re, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _root(root=None):
    return root or ROOT


def _load_mcp():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import mcp_server
    return mcp_server


def _internal_registry(root=None):
    """Множество id внутренних тулов из ```text```-блока docs/dev/internal-tools.md."""
    path = os.path.join(_root(root), "docs", "dev", "internal-tools.md")
    if not os.path.exists(path):
        return set()
    text = open(path, encoding="utf-8").read()
    m = re.search(r"```text\n(.*?)```", text, re.S)
    if not m:
        return set()
    return {ln.strip() for ln in m.group(1).splitlines() if ln.strip()}


def _recipes_raw(root=None):
    path = os.path.join(_root(root), "recipes.json")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else "[]"


def extract_tools(root=None):
    """Тулы из mcp_server.TOOLS + статус (4-канальная логика test_no_dark_tools) + referenced_in."""
    m = _load_mcp()
    instr = m.INSTRUCTIONS
    all_descs = " ".join(t.get("description", "") for t in m.TOOLS.values())
    recipes_text = _recipes_raw(root)
    internal = _internal_registry(root)
    rules = extract_rules(root)
    recipes = extract_recipes(root)
    out = []
    for name in sorted(m.TOOLS):
        spec = m.TOOLS[name]
        surfaced = (name in instr) or (name in all_descs) or (name in recipes_text)
        status = "internal" if (name in internal and not (name in instr)) else ("surfaced" if surfaced else "internal")
        refs = [f"rule:{r['n']}" for r in rules if name in r["text"]]
        refs += [f"recipe:{rc['id']}" for rc in recipes if name in json.dumps(rc, ensure_ascii=False)]
        out.append({"name": name, "description": spec.get("description", ""),
                    "input_schema": spec.get("input_schema", {}), "status": status,
                    "referenced_in": refs})
    return out


def extract_rules(root=None):
    """Нумерованные правила 0..N из INSTRUCTIONS (строки '^\\d+\\. ЗАГОЛОВОК ...')."""
    m = _load_mcp()
    text = m.INSTRUCTIONS
    pattern = re.compile(r"(?m)^(\d+)\.\s+(.*?)(?=\n\d+\.\s|\Z)", re.S)
    out = []
    for mo in pattern.finditer(text):
        n = int(mo.group(1))
        body = mo.group(2).strip()
        title = body.split(".")[0].split("(")[0].strip()[:80]
        out.append({"n": n, "title": title, "text": body})
    out.sort(key=lambda r: r["n"])
    return out


def extract_recipes(root=None):
    return json.loads(_recipes_raw(root))


def build(root=None):
    """Собирает полный индекс {tools, rules, recipes} для docs/selfdoc/index.json."""
    return {
        "tools": extract_tools(root),
        "rules": extract_rules(root),
        "recipes": extract_recipes(root),
    }


if __name__ == "__main__":
    index = build()
    out_dir = os.path.join(ROOT, "docs", "selfdoc")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {out_path}")
