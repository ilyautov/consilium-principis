#!/usr/bin/env python3
"""gen_selfdoc.py — интроспектор живого кода → docs/selfdoc/index.json.
Единый источник правды для docs/MANUAL.md и тула explain_self. Ноль сети/движка.
Запуск: python scripts/gen_selfdoc.py  (перезаписывает index.json)."""
import os, sys, json, re, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _root(root=None):
    return root or ROOT


def _load_mcp():
    # Тулы/правила интроспектируются из ЖИВОГО импортированного mcp_server ПО ДИЗАЙНУ (само-док
    # документирует РАБОТАЮЩИЙ сервер, не foreign-root копию); `root` в остальных extract_* правит
    # только файловыми источниками (recipes.json, internal-tools.md, scripts/, tests/, GLOSSARY.md).
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


def _subsystem_of(rel_path):
    """Подсистема по каталогу/имени файла."""
    parts = rel_path.replace("\\", "/").split("/")
    if "corpusbuild" in parts:
        return "corpusbuild"
    base = parts[-1]
    for key in ("mcp_server", "collect", "engine", "tier", "build_advisor", "install", "doctor",
                "catalog", "seed_council", "eval", "diversity", "situation", "calibrate"):
        if base.startswith(key) or key in base:
            return key.split("_")[0]
    return "other"


def _first_docline(path):
    """Первая непустая строка docstring модуля (или '')."""
    try:
        src = open(path, encoding="utf-8").read()
    except Exception:
        return ""
    m = re.search(r'^\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', src, re.S | re.M)
    if not m:
        return ""
    for ln in m.group(1).strip().splitlines():
        if ln.strip():
            return ln.strip()[:200]
    return ""


def extract_scripts(root=None):
    d = os.path.join(_root(root), "scripts")
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".py"):
            continue
        rel = os.path.join("scripts", name)
        full = os.path.join(d, name)
        out.append({"path": rel, "subsystem": _subsystem_of(rel), "doc": _first_docline(full)})
    return out


def extract_tests(root=None):
    d = os.path.join(_root(root), "tests")
    out = []
    for name in sorted(os.listdir(d)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        covers = name[len("test_"):-len(".py")].replace("_", " ")
        out.append({"path": os.path.join("tests", name), "covers": covers})
    return out


def extract_glossary(root=None):
    """Термины '**Термин** — определение' из docs/GLOSSARY.md (многострочные до пустой строки)."""
    path = os.path.join(_root(root), "docs", "GLOSSARY.md")
    if not os.path.exists(path):
        return []
    lines = open(path, encoding="utf-8").read().splitlines()
    out, cur = [], None
    term_re = re.compile(r"^\*\*(.+?)\*\*\s+—\s+(.*)$")
    for ln in lines:
        mo = term_re.match(ln)
        if mo:
            if cur:
                out.append(cur)
            cur = {"term": mo.group(1).strip(), "definition": mo.group(2).strip()}
        elif cur is not None:
            if ln.strip() == "":
                out.append(cur); cur = None
            else:
                cur["definition"] = (cur["definition"] + " " + ln.strip()).strip()
    if cur:
        out.append(cur)
    return out


def build_index(root=None):
    # тулы/правила — из ЖИВОГО импортированного mcp_server (само-док документирует работающий сервер);
    # root управляет только файловыми источниками (recipes/registry/scripts/tests/glossary).
    tools = extract_tools(root)
    rules = extract_rules(root)
    recipes = extract_recipes(root)
    scripts = extract_scripts(root)
    tests = extract_tests(root)
    glossary = extract_glossary(root)
    return {
        "meta": {"tool_count": len(tools), "rule_count": len(rules), "recipe_count": len(recipes),
                 "script_count": len(scripts), "test_count": len(tests), "glossary_count": len(glossary)},
        "tools": tools, "rules": rules, "recipes": recipes,
        "scripts": scripts, "tests": tests, "glossary": glossary,
    }


def write_index(idx, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")


INDEX_PATH = os.path.join(ROOT, "docs", "selfdoc", "index.json")


def main():
    idx = build_index()
    write_index(idx, INDEX_PATH)
    print("selfdoc index: %d тулов, %d правил, %d рецептов, %d скриптов, %d тестов, %d терминов → %s"
          % (idx["meta"]["tool_count"], idx["meta"]["rule_count"], idx["meta"]["recipe_count"],
             idx["meta"]["script_count"], idx["meta"]["test_count"], idx["meta"]["glossary_count"],
             os.path.relpath(INDEX_PATH, ROOT)))


if __name__ == "__main__":
    main()
