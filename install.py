#!/usr/bin/env python3
"""
install.py — поставить скилл personal-board (Consilium) в ~/.claude/skills/<name>/,
где Claude Code обнаруживает пользовательские скиллы.

Что делает (ничего не ломает, повторный запуск безопасен):
  1. копирует МАШИНЕРИЮ (SKILL.md, scripts/, QUICKSTART.md, council/, assets/) + грунтованный
     контент из коробки (lenses/ = Сунь-цзы 🔵-линза, gov_heads.json = якорь целостности)
     в каноническое место — обновляет, НЕ удаляя твою доску;
  2. определяет тир (есть ollama bge-m3 → FULL, иначе пол) и гонит board_init;
  3. пишет breadcrumb last_install.json (без секретов).

ТВОЯ ДОСКА = user-data, НИКОГДА не затирается переустановкой:
  advisors/ (кроме README), board_config.json, data/, scripts/golden/.

Примеры:
  python3 install.py                 # поставить в ~/.claude/skills/consilium-principis
  python3 install.py --name my-board # другое имя скилла
  python3 install.py --in-place      # не копировать, настроить прямо здесь (dev)
  python3 install.py --print         # показать, что будет сделано, и выйти
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_NAME = "consilium-principis"
HERE = Path(__file__).resolve().parent
SKILLS_HOME = Path.home() / ".claude" / "skills"

# Машинерия — копируется/обновляется. (scripts/golden и advisors-доска сохраняются, см. ниже.)
# lenses/ + gov_heads.json — ГРУНТОВАННЫЙ контент из коробки (Сунь-цзы 🔵-линза + якорь целостности):
# без них skill-install приезжал с ПУСТОЙ доской (HIGH #1 pre-publish аудита). install-skill НЕ шипуем —
# как под-скилл он приземляется глубже, чем ищет Claude Code (~/.claude/skills/*/SKILL.md), т.е. мёртв;
# онбординг покрыт README/QUICKSTART + тулами board_status/doctor/seed_council/setup_full.
RUNTIME = ["SKILL.md", "QUICKSTART.md", "recipes.json", "scripts", "council", "assets",
           "lenses", "gov_heads.json"]
# golden = per-advisor user-data; build = тяжёлые регенерируемые артефакты (эмбеддинги/индексы линз —
# шипуем только PD-исходник corpus.jsonl + manifest, не производное).
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "golden", "build")


def py_ok() -> bool:
    return sys.version_info >= (3, 10)


def detect_semantic(skill_dir: Path) -> bool:
    """ollama bge-m3 доступен? (через сам движок, в целевой папке)."""
    try:
        out = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, 'scripts'); "
             "from engine.semantic import SemanticEngine; print(SemanticEngine.available())"],
            cwd=skill_dir, capture_output=True, text=True, timeout=30)
        return "True" in out.stdout
    except Exception:
        return False


def copy_runtime(src: Path, dest: Path) -> None:
    """Обновить машинерию в dest, сохранив доску. Слияние (dirs_exist_ok), без удаления user-data."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in RUNTIME:
        s = src / item
        if not s.exists():
            continue
        d = dest / item
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=IGNORE)
        else:
            shutil.copy2(s, d)
    # advisors/: завести структуру + README, НИКОГДА не трогать существующую доску
    adv = dest / "advisors"
    adv.mkdir(exist_ok=True)
    readme = src / "advisors" / "README.md"
    if readme.exists():
        shutil.copy2(readme, adv / "README.md")


def write_breadcrumb(dest: Path, semantic: bool) -> None:
    crumb = {
        "skill": dest.name,
        "installed_to": str(dest),
        "tier": "FULL (semantic, bge-m3)" if semantic else "SIMPLE (пол, без ollama)",
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "advisors/ — твои данные, живут здесь и НЕ затираются переустановкой.",
    }
    (dest / "last_install.json").write_text(
        json.dumps(crumb, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Поставить personal-board (Consilium) в ~/.claude/skills/")
    ap.add_argument("--name", default=SKILL_NAME, help="имя скилла в ~/.claude/skills/")
    ap.add_argument("--target", default="", help="переопределить целевую папку целиком")
    ap.add_argument("--in-place", action="store_true", help="не копировать; настроить прямо здесь (dev)")
    ap.add_argument("--print", action="store_true", dest="print_only", help="показать план и выйти")
    ap.add_argument("--setup-full", action="store_true", help="поднять FULL-тир (ollama + pull bge-m3)")
    args = ap.parse_args()

    if not py_ok():
        print(f"❌ Нужен Python 3.10+, сейчас {sys.version.split()[0]}. Поставь с https://python.org.",
              file=sys.stderr)
        sys.exit(1)

    dest = HERE if args.in_place else (Path(args.target).expanduser() if args.target
                                       else SKILLS_HOME / args.name)

    if args.print_only:
        print(f"Источник:   {HERE}")
        print(f"Назначение: {dest}  ({'in-place' if args.in_place else 'копия'})")
        print(f"Машинерия:  {', '.join(RUNTIME)}")
        print("Сохраняется как есть: advisors/ (кроме README), board_config.json, data/, scripts/golden/")
        return

    if args.in_place:
        print(f"⚙️  Настройка in-place: {dest}")
    else:
        print(f"📦 Копирую скилл → {dest}")
        copy_runtime(HERE, dest)

    semantic = detect_semantic(dest)
    print(f"🎛  tier: {'FULL (semantic, ollama bge-m3)' if semantic else 'SIMPLE (пол — контур работает без ollama)'}")
    if not semantic:
        if args.setup_full:
            print("⬆️  Поднимаю FULL-тир…")
            subprocess.run([sys.executable, "scripts/setup_full.py"], cwd=dest)
        else:
            print("   FULL-тир (умный кросс-язычный поиск) — по желанию: `python3 scripts/board.py setup-full`")
            print("   (контур 🔵 и совет работают и без него, на полу)")
    sys.stdout.flush()
    subprocess.run([sys.executable, "scripts/board_init.py", "advisors",
                    "--semantic-available", "true" if semantic else "false"], cwd=dest)
    write_breadcrumb(dest, semantic)

    print("\n🔎 Самопроверка:")
    sys.stdout.flush()  # иначе вывод субпроцесса перемешается с буфером print
    subprocess.run([sys.executable, "scripts/board.py", "doctor"], cwd=dest)

    print("\n✅ Готово.")
    print(f"   Скилл: {dest}")
    print("   Доска пустая — два простых старта:")
    print("     • «с чего начать» → соберу стартовый совет (Аврелий + Эпиктет)")
    print("     • «что умеешь?»   → меню рецептов простыми фразами")
    if not args.in_place:
        print("   Перезапусти Claude Code, чтобы он увидел новый скилл.")


if __name__ == "__main__":
    main()
