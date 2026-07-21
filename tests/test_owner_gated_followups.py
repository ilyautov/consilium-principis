"""Гарды owner-gated добивания находок соседей (2026-07-21).

Каждая правка была «owner decision» в планах ремедиации — исполнитель их не решал сам.
Здесь регресс-гарды, чтобы правки не отдрейфовали обратно:

  • #1 заморозка PD-golden для воспроизводимого moat-базлайна (firewall-safe: ТОЛЬКО
    3 PD-советника через retrieval-слайс; приватные слайсы и *.answerable.v2 остаются локальны);
  • #2 реальная команда плагина /board (закрыт честностный пробел «SKILL.md обещает
    slash-команды, которых нет»);
  • #3 install-skill/SKILL.md → docs/onboarding-recipe.md (мёртвый вложенный скилл убран);
  • #4 кавеат линейности в торнадо mc_run (|Пирсон| слеп к U-образной чувствительности).

F1 (жёсткий пол допуска на эрозию рва) живёт в tests/test_moat_check.py.
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from mc_run import mc_run


# ── #4: торнадо честно оговаривает линейность ────────────────────────────────

def _valid_map():
    return {
        "question": "Куда вкладывать следующий месяц?",
        "options": [
            {"id": "ship_public", "name": "Выпустить публично", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Ничего не делать",
             "reversibility": "two-way", "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3, "confirmed_by_user": True},
            {"id": "hours_to_ship", "kind": "continuous", "unit": "часы",
             "min": 20, "mode": 40, "max": 90, "confirmed_by_user": True},
            {"id": "upside_hours", "kind": "continuous", "unit": "часы",
             "min": 50, "mode": 150, "max": 400, "confirmed_by_user": True},
        ],
        "stakes": {"metric": "ценность в часах", "direction": "max"},
        "horizon": "3 месяца",
        "model": {
            "ship_public": {"expr": "traction_prob * upside_hours - hours_to_ship",
                            "words": "трекшен × выигрыш − часы"},
            "status_quo": {"expr": "0", "words": "ноль"},
        },
    }


def test_tornado_reports_linearity_caveat():
    out = mc_run(_valid_map(), seed=0, n=300)
    assert "tornado" in out
    assert "tornado_caveat" in out, "торнадо обязан честно оговорить, что impact линейный"
    c = out["tornado_caveat"].lower()
    assert "пирсон" in c and ("линейн" in c or "монотон" in c)


# ── #2: команда /board реальна и покрывает всё, что обещает SKILL.md ──────────

def test_board_command_file_exists():
    assert os.path.isfile(os.path.join(ROOT, "commands", "board.md"))


def test_board_command_covers_advertised_subcommands():
    cmd = open(os.path.join(ROOT, "commands", "board.md"), encoding="utf-8").read()
    skill = open(os.path.join(ROOT, "SKILL.md"), encoding="utf-8").read()
    seg = skill.split("## Команды", 1)[-1].split("\n## ", 1)[0]
    subs = set(re.findall(r"/board (\w+)", seg))
    assert subs, "SKILL.md больше не перечисляет /board под-команды — обновить гард"
    missing = sorted(s for s in subs if s not in cmd)
    assert not missing, f"commands/board.md не покрывает обещанные под-команды: {missing}"


# ── #3: онбординг-рецепт перенесён и разскилен ───────────────────────────────

def test_onboarding_recipe_moved_and_deskilled():
    doc = os.path.join(ROOT, "docs", "onboarding-recipe.md")
    assert os.path.isfile(doc)
    assert not os.path.exists(os.path.join(ROOT, "install-skill")), "мёртвый install-skill/ должен быть убран"
    text = open(doc, encoding="utf-8").read()
    assert not text.lstrip().startswith("---\nname:"), "skill-frontmatter должен быть снят (иначе Claude Code примет за скилл)"
    qs = open(os.path.join(ROOT, "QUICKSTART.md"), encoding="utf-8").read()
    assert "install-skill/SKILL.md" not in qs
    assert "docs/onboarding-recipe.md" in qs


# ── #1: заморожены РОВНО PD-слайсы, приватное/производное — нет ──────────────

FROZEN = [
    "scripts/golden/machiavelli.retrieval.en.jsonl",
    "scripts/golden/machiavelli.retrieval.jsonl",
    "scripts/golden/marcus-aurelius.retrieval.en.jsonl",
    "scripts/golden/marcus-aurelius.retrieval.jsonl",
    "scripts/golden/sun-tzu.retrieval.en.jsonl",
]
PD_SLUGS = {"machiavelli", "marcus-aurelius", "sun-tzu", "epictetus", "seneca", "aristotle"}


def _private_slugs():
    """Приватные слаги = каталоги advisors/ минус PD-allowlist (как firewall_check.sh).
    НЕ хардкодим — иначе сам тест носил бы реальные имена живых людей в трекуемый файл."""
    adv = os.path.join(ROOT, "advisors")
    if not os.path.isdir(adv):
        return set()
    return {d for d in os.listdir(adv)
            if os.path.isdir(os.path.join(adv, d)) and d not in PD_SLUGS}


def _git_ok():
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                           cwd=ROOT, capture_output=True, text=True)
        return r.returncode == 0
    except (OSError, FileNotFoundError):
        return False


def _is_ignored(rel):
    r = subprocess.run(["git", "check-ignore", rel], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0  # 0 = игнорируется, 1 = трекуемо


def test_frozen_pd_golden_are_trackable():
    if not _git_ok():
        pytest.skip("не git-worktree — гард неприменим")
    for rel in FROZEN:
        assert os.path.isfile(os.path.join(ROOT, rel)), f"{rel} отсутствует локально"
        assert not _is_ignored(rel), f"{rel} должен быть заморожен (не игнорирован)"


def test_private_slug_golden_stay_ignored():
    if not _git_ok():
        pytest.skip("не git-worktree — гард неприменим")
    priv = _private_slugs()
    if not priv:
        pytest.skip("advisors/ недоступен — приватные слаги не вывести")
    gdir = os.path.join(ROOT, "scripts", "golden")
    for n in os.listdir(gdir):
        if n.split(".")[0] in priv:
            rel = f"scripts/golden/{n}"
            assert _is_ignored(rel), f"приватный слайс {rel} НЕ должен трекаться"


def test_derived_golden_variants_stay_ignored():
    # *.answerable.v2 / *.abstention / *.auto базлайну не нужны и могут тащить копирайт-вторичку
    if not _git_ok():
        pytest.skip("не git-worktree — гард неприменим")
    gdir = os.path.join(ROOT, "scripts", "golden")
    for n in os.listdir(gdir):
        if any(k in n for k in (".answerable.", ".abstention.", ".auto.")):
            rel = f"scripts/golden/{n}"
            assert _is_ignored(rel), f"{rel} (производный слайс) НЕ должен трекаться"


def test_no_extra_golden_unignored():
    if not _git_ok():
        pytest.skip("не git-worktree — гард неприменим")
    gdir = os.path.join(ROOT, "scripts", "golden")
    unignored = [f"scripts/golden/{n}" for n in os.listdir(gdir)
                 if n.endswith(".jsonl") and not _is_ignored(f"scripts/golden/{n}")]
    extra = set(unignored) - set(FROZEN)
    assert not extra, f"из scripts/golden un-ignore'нуто лишнее (риск утечки): {sorted(extra)}"


def test_frozen_pd_golden_have_no_private_slug():
    priv = _private_slugs()
    if not priv:
        pytest.skip("advisors/ недоступен — приватные слаги не вывести")
    for rel in FROZEN:
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        low = open(p, encoding="utf-8").read().lower()
        for slug in priv:
            assert slug.lower() not in low, f"приватный слаг просочился в {rel}"
