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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

import install  # noqa: E402
from engine.fidelity import best_match  # noqa: E402


def test_runtime_ships_lenses_and_gov_heads():
    assert "lenses" in install.RUNTIME
    assert "gov_heads.json" in install.RUNTIME


def test_runtime_does_not_ship_dead_nested_skill():
    # install-skill/SKILL.md приземляется на уровень глубже, чем ищет Claude Code
    # (~/.claude/skills/*/SKILL.md) → как под-скилл он не регистрируется. Не шипуем мёртвый.
    assert "install-skill" not in install.RUNTIME


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
