"""install.py упаковывает РАБОЧУЮ доску, а не пустую.

Регресс на HIGH #1 (pre-publish аудит): RUNTIME ронял `lenses/` и `gov_heads.json`,
поэтому skill-install в ~/.claude/skills/ приезжал БЕЗ единственного грунтованного
контента (Сунь-цзы `lenses/strategist`, 🔵-способная PD-линза). Проверяем:
  • RUNTIME включает lenses + gov_heads.json (+ install-skill НЕ шипуется — dead nested skill);
  • copy_runtime реально кладёт corpus.jsonl линзы и якорь целостности;
  • пост-инсталл cite (best_match) находит дословную максиму → линза работает офлайн;
  • тяжёлый регенерируемый lenses/*/build/ НЕ едет (copyright/размер).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import install  # noqa: E402
from engine.fidelity import best_match  # noqa: E402


def test_shipped_md_relative_links_resolve_in_installed_tree():
    # Любая ОТНОСИТЕЛЬНАЯ markdown-ссылка в шипуемом .md должна вести на то, что ТОЖЕ шипуется
    # (RUNTIME + advisors/README) — иначе она МЁРТВА в установленном скилле (~/.claude/skills/...):
    # там нет ни docs/, ни install.command/.bat, ни QUICKSTART.en.md, ни CONNECT-MCP.md.
    # Link-guard репо этого не ловит (сканирует repo-tree, где всё на месте). Абсолютные URL и
    # #якоря — ок; на не-шипуемое ссылайся абсолютным URL. Ранняя версия ловила только `](docs/`,
    # пропуская 4 ссылки другой формы (регресс раунда 4).
    shipped_top = set(install.RUNTIME) | {"advisors"}
    shipped_md = [f for f in install.RUNTIME if f.endswith(".md")] + ["advisors/README.md"]
    offenders = []
    for rel in shipped_md:
        p = os.path.join(install.HERE, rel)
        if not os.path.isfile(p):
            continue
        text = open(p, encoding="utf-8").read()
        for m in re.finditer(r"\]\(([^)]+)\)", text):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            first = target.split("#", 1)[0].split("/", 1)[0]
            if first and first not in shipped_top:
                offenders.append(f"{rel}: ]({target})")
    assert not offenders, ("относительные ссылки на НЕ-шипуемое в шипуемых файлах (мертвы в "
                           "installed skill — используй абсолютный URL): " + "; ".join(offenders))


def test_runtime_ships_lenses_and_gov_heads():
    assert "lenses" in install.RUNTIME
    assert "gov_heads.json" in install.RUNTIME


def test_runtime_ships_selfdoc_so_explain_self_works(tmp_path):
    # explain_self (реклама в SKILL.md) читает docs/selfdoc/index.json + narrative/. Если docs/
    # selfdoc не шипуется, в установленном скилле тул отдаёт 0 секций и советует запустить
    # gen_selfdoc.py — а тот падает без tests/. Гард: selfdoc едет и тул работает после install.
    assert "docs/selfdoc" in install.RUNTIME
    dest = tmp_path / "installed"
    install.copy_runtime(install.HERE, dest)
    assert (dest / "docs" / "selfdoc" / "index.json").is_file()
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import selfdoc_query
    out = selfdoc_query.explain("overview", root=str(dest))
    assert out["sections"] and out["sections"][0]["body"].strip(), "explain_self пуст в installed skill"
    assert "gen_selfdoc" not in str(out.get("suggestions", [])), "тул советует упавший recovery"


def test_runtime_does_not_ship_dead_nested_skill():
    # install-skill/SKILL.md переехал в docs/onboarding-recipe.md (2026-07-21) — как
    # под-скилл он приземлялся глубже, чем ищет Claude Code (~/.claude/skills/*/SKILL.md).
    # Гард: старый путь не шипуется; из docs/ едет ТОЛЬКО docs/selfdoc (для explain_self),
    # не весь docs/ и не онбординг-рецепт.
    assert "install-skill" not in install.RUNTIME
    assert "docs" not in install.RUNTIME
    docs_items = [x for x in install.RUNTIME if x.startswith("docs")]
    assert docs_items == ["docs/selfdoc"], f"из docs/ должен ехать только selfdoc, а не {docs_items}"
    assert "docs/onboarding-recipe.md" not in install.RUNTIME


def test_copy_runtime_ships_working_strategist_lens(tmp_path):
    dest = tmp_path / "installed"
    install.copy_runtime(install.HERE, dest)

    lens = dest / "lenses" / "strategist"
    assert (lens / "corpus.jsonl").is_file(), "корпус линзы не приехал → пустая доска"
    assert (lens / "lens.md").is_file()
    assert (lens / "sources" / "manifest.json").is_file()
    assert (dest / "gov_heads.json").is_file(), "якорь целостности не приехал"

    # Пост-инсталл: дословная максима Сунь-цзы (Giles 1910, PD) матчится как P1/P2 → cite даст 🔵.
    m = best_match("The art of war is of vital importance to the State", str(lens))
    assert m is not None and m[0] in ("P1", "P2"), "линза не грунтует офлайн — cite не найдёт цитату"


def test_copy_runtime_skips_regenerable_lens_build(tmp_path):
    # Синтетический источник: тяжёлый lenses/foo/build/ должен быть пропущен, а corpus.jsonl — нет.
    src = tmp_path / "src"
    (src / "lenses" / "foo" / "build").mkdir(parents=True)
    (src / "lenses" / "foo" / "corpus.jsonl").write_text('{"text":"x","tier":"P1"}\n', encoding="utf-8")
    (src / "lenses" / "foo" / "build" / "heavy.npy").write_text("BINARYBLOB", encoding="utf-8")

    dest = tmp_path / "out"
    install.copy_runtime(src, dest)

    assert (dest / "lenses" / "foo" / "corpus.jsonl").is_file()
    assert not (dest / "lenses" / "foo" / "build").exists(), "регенерируемый build/ не должен шиповаться"
