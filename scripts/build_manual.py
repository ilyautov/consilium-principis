#!/usr/bin/env python3
"""build_manual.py — сшивает docs/selfdoc/index.json + narrative/*.md → docs/MANUAL.md.
Слоёный: Обзор (оценщик) → Архитектура (контрибьютор) → Справочник (генерённый из индекса).
--pdf: опциональный экспорт через pandoc, если он есть (иначе сообщение + exit 0)."""
import os, sys, json, argparse, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NARR_ORDER = ["00-overview.md", "10-moat.md", "20-firewall.md", "30-architecture.md", "40-extend.md"]

HEADER = ("<!-- Этот файл СГЕНЕРИРОВАН scripts/build_manual.py из docs/selfdoc/index.json + "
          "narrative/*.md. Не правь его руками — меняй нарратив или код и пересобирай. -->\n\n"
          "# Consilium-Principis — Технический мануал\n\n"
          "> Сгенерирован из живого кода. Слой 1 — «что это/почему доверять», слой 2 — архитектура и "
          "как расширять, слой 3 — полный справочник.\n\n")


def _load_narrative(root):
    d = os.path.join(root, "docs", "selfdoc", "narrative")
    out = {}
    for name in NARR_ORDER:
        p = os.path.join(d, name)
        out[name] = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    return out


def _reference(idx):
    L = ["## Слой 3 — Справочник\n"]
    L.append("### Тулы (%d)\n" % idx["meta"]["tool_count"])
    for t in idx["tools"]:
        badge = "🌐" if t["status"] == "surfaced" else "🔧"
        refs = (" · " + ", ".join(t["referenced_in"])) if t["referenced_in"] else ""
        L.append("- %s **`%s`** — %s%s" % (badge, t["name"], t["description"], refs))
    L.append("\n### Правила INSTRUCTIONS (%d)\n" % idx["meta"]["rule_count"])
    for r in idx["rules"]:
        L.append("- **%d. %s**" % (r["n"], r["title"]))
    if idx["recipes"]:
        L.append("\n### Рецепты (%d)\n" % idx["meta"]["recipe_count"])
        for rc in idx["recipes"]:
            L.append("- **%s** — %s" % (rc["id"], rc.get("does", "")))
    L.append("\n### Глоссарий (%d)\n" % idx["meta"]["glossary_count"])
    for gt in idx["glossary"]:
        L.append("- **%s** — %s" % (gt["term"], gt["definition"]))
    return "\n".join(L)


def _inventory(idx):
    L = ["### Инвентарь кода\n", "Скрипты (%d) по подсистемам:\n" % idx["meta"]["script_count"]]
    by = {}
    for s in idx["scripts"]:
        by.setdefault(s["subsystem"], []).append(s)
    for sub in sorted(by):
        L.append("- **%s**: %s" % (sub, ", ".join("`%s`" % os.path.basename(s["path"]) for s in by[sub])))
    L.append("\nТестов: %d." % idx["meta"]["test_count"])
    return "\n".join(L)


def assemble(idx, narr):
    parts = [HEADER]
    parts.append("## Слой 1 — Обзор\n")
    parts.append(narr.get("00-overview.md", ""))
    parts.append("\n" + narr.get("10-moat.md", ""))
    parts.append("\n## Слой 2 — Архитектура\n")
    parts.append(narr.get("30-architecture.md", ""))
    parts.append("\n" + narr.get("20-firewall.md", ""))
    parts.append("\n" + narr.get("40-extend.md", ""))
    parts.append("\n" + _inventory(idx))
    parts.append("\n" + _reference(idx))
    return "\n".join(parts).rstrip() + "\n"


def build(root=None, out_path=None, pdf=False):
    root = root or ROOT
    idx = json.load(open(os.path.join(root, "docs", "selfdoc", "index.json"), encoding="utf-8"))
    narr = _load_narrative(root)
    md = assemble(idx, narr)
    out_path = out_path or os.path.join(root, "docs", "MANUAL.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    if pdf:
        _export_pdf(out_path)
    return out_path


def check(root=None, out_path=None):
    """Return whether the committed manual matches the current index and narrative."""
    root = root or ROOT
    out_path = out_path or os.path.join(root, "docs", "MANUAL.md")
    idx = json.load(open(os.path.join(root, "docs", "selfdoc", "index.json"), encoding="utf-8"))
    expected = assemble(idx, _load_narrative(root))
    try:
        with open(out_path, encoding="utf-8") as f:
            actual = f.read()
    except FileNotFoundError:
        return False
    return actual == expected


def _export_pdf(md_path):
    if not shutil.which("pandoc"):
        print("PDF пропущен: pandoc не найден в PATH. Установи pandoc для экспорта (MD уже собран).")
        return None
    pdf_path = md_path[:-3] + ".pdf" if md_path.endswith(".md") else md_path + ".pdf"
    subprocess.run(["pandoc", md_path, "-o", pdf_path], check=False)
    print("PDF: %s" % pdf_path)
    return pdf_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true", help="также экспортировать PDF через pandoc (если есть)")
    ap.add_argument("--check", action="store_true", help="проверить, что MANUAL.md не отстал от источников")
    a = ap.parse_args()
    if a.check:
        if check():
            print("MANUAL.md актуален")
            return
        print("MANUAL.md отстал — запусти scripts/build_manual.py", file=sys.stderr)
        sys.exit(1)
    out = build(pdf=a.pdf)
    print("мануал собран → %s" % os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
