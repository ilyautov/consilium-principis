#!/usr/bin/env python3
"""
install.py — поставить скилл personal-board (Consilium) в ~/.claude/skills/<name>/,
где Claude Code обнаруживает пользовательские скиллы.

Что делает (ничего не ломает, повторный запуск безопасен):
  1. копирует МАШИНЕРИЮ (SKILL.md, scripts/, QUICKSTART.md, assets/) + грунтованный
     контент из коробки (lenses/ = Сунь-цзы 🔵-линза, gov_heads.json = якорь целостности)
     в каноническое место — обновляет, НЕ удаляя твою доску;
  2. определяет тир (есть ollama bge-m3 → FULL, иначе пол) и гонит board_init
     (он же заводит council/ с нуля — приватную папку решений мы НЕ копируем);
  3. пишет breadcrumb last_install.json (без секретов).

ТВОЯ ДОСКА = user-data, НИКОГДА не затирается переустановкой:
  advisors/ (кроме README), board_config.json, data/, scripts/golden/, council/ (приватные решения).

Примеры:
  python3 install.py                 # поставить в ~/.claude/skills/consilium-principis
  python3 install.py --name my-board # другое имя скилла
  python3 install.py --in-place      # не копировать, настроить прямо здесь (dev)
  python3 install.py --print         # показать, что будет сделано, и выйти
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_NAME = "consilium-principis"
HERE = Path(__file__).resolve().parent
SKILLS_HOME = Path.home() / ".claude" / "skills"

# #4 EN-паритет: вывод установщика показывается юзеру НАПРЯМУЮ (хост его не переводит), поэтому
# двуязычим по CONSILIUM_LANG (дефолт ru — поведение не меняем молча). Ключи двух словарей должны
# совпадать (гард test_install_messages_en_ru_parity).
_MSG = {
    "ru": {
        "need_py": "❌ Нужен Python 3.10+, сейчас {ver}. Поставь с https://python.org.",
        "src": "Источник:   {here}", "dst": "Назначение: {dest}  ({mode})",
        "mode_inplace": "in-place", "mode_copy": "копия",
        "machinery": "Машинерия:  {items}",
        "preserved": "Сохраняется как есть: advisors/ (кроме README), board_config.json, data/, scripts/golden/",
        "setup_inplace": "⚙️  Настройка in-place: {dest}", "copying": "📦 Копирую скилл → {dest}",
        "tier": "🎛  tier: {tier}",
        "tier_full": "FULL (semantic, ollama bge-m3)",
        "tier_simple": "SIMPLE (пол — контур работает без ollama)",
        "raising_full": "⬆️  Поднимаю FULL-тир…",
        "full_optional": "   FULL-тир (умный кросс-язычный поиск) — по желанию: `python3 scripts/board.py setup-full`",
        "full_optional2": "   (контур 🔵 и совет работают и без него, на полу)",
        "init_fail": "\n❌ board_init упал (код {code}) — установка не завершена. Проверь вывод выше и запусти повторно.",
        "selfcheck": "\n🔎 Самопроверка:", "done": "\n✅ Готово.", "skill_at": "   Скилл: {dest}",
        "empty_board": "   Доска пустая — два простых старта:",
        "start1": "     • «с чего начать» → соберу стартовый совет (Аврелий + Эпиктет)",
        "start2": "     • «что умеешь?»   → меню рецептов простыми фразами",
        "restart": "   Перезапусти Claude Code, чтобы он увидел новый скилл.",
    },
    "en": {
        "need_py": "❌ Python 3.10+ required, currently {ver}. Install from https://python.org.",
        "src": "Source:      {here}", "dst": "Destination: {dest}  ({mode})",
        "mode_inplace": "in-place", "mode_copy": "copy",
        "machinery": "Machinery:   {items}",
        "preserved": "Preserved as-is: advisors/ (except README), board_config.json, data/, scripts/golden/",
        "setup_inplace": "⚙️  In-place setup: {dest}", "copying": "📦 Copying the skill → {dest}",
        "tier": "🎛  tier: {tier}",
        "tier_full": "FULL (semantic, ollama bge-m3)",
        "tier_simple": "SIMPLE (floor — the contour works without ollama)",
        "raising_full": "⬆️  Bringing up the FULL tier…",
        "full_optional": "   FULL tier (smart cross-language search) — optional: `python3 scripts/board.py setup-full`",
        "full_optional2": "   (the 🔵 contour and the council work without it, on the floor)",
        "init_fail": "\n❌ board_init failed (code {code}) — install not completed. Check the output above and re-run.",
        "selfcheck": "\n🔎 Self-check:", "done": "\n✅ Done.", "skill_at": "   Skill: {dest}",
        "empty_board": "   The board is empty — two simple starts:",
        "start1": '     • "where do I start" → I\'ll assemble a starter council (Aurelius + Epictetus)',
        "start2": '     • "what can you do?" → a recipe menu in plain phrases',
        "restart": "   Restart Claude Code so it picks up the new skill.",
    },
}


def _messages(lang):
    return _MSG.get(lang, _MSG["ru"])


def _lang():
    return "en" if (os.getenv("CONSILIUM_LANG") or "").strip().lower() == "en" else "ru"

# Машинерия — копируется/обновляется. (scripts/golden и advisors-доска сохраняются, см. ниже.)
# lenses/ + gov_heads.json — ГРУНТОВАННЫЙ контент из коробки (Сунь-цзы 🔵-линза + якорь целостности):
# без них skill-install приезжал с ПУСТОЙ доской (HIGH #1 pre-publish аудита). Онбординг-рецепт
# переехал в docs/onboarding-recipe.md (2026-07-21) и НЕ шипуется в RUNTIME (docs/ не копируем);
# онбординг покрыт README/QUICKSTART + тулами board_status/doctor/seed_council/setup_full.
# catalog/ — указатели PD-фигур (pd_figures.json) для catalog_add/search/preview: без него
# эти тулы на установленном скилле бьют по несуществующему файлу.
RUNTIME = ["SKILL.md", "QUICKSTART.md", "recipes.json", "scripts", "assets",
           "lenses", "gov_heads.json", "catalog", "docs/selfdoc"]
# docs/selfdoc — единственное исключение из «docs/ не шипуется»: explain_self читает
# docs/selfdoc/index.json + narrative/, без них тул отдаёт 0 секций в установленном скилле.
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
    M = _messages(_lang())

    if not py_ok():
        print(M["need_py"].format(ver=sys.version.split()[0]), file=sys.stderr)
        sys.exit(1)

    dest = HERE if args.in_place else (Path(args.target).expanduser() if args.target
                                       else SKILLS_HOME / args.name)

    if args.print_only:
        print(M["src"].format(here=HERE))
        print(M["dst"].format(dest=dest, mode=M["mode_inplace"] if args.in_place else M["mode_copy"]))
        print(M["machinery"].format(items=", ".join(RUNTIME)))
        print(M["preserved"])
        return

    if args.in_place:
        print(M["setup_inplace"].format(dest=dest))
    else:
        print(M["copying"].format(dest=dest))
        copy_runtime(HERE, dest)

    semantic = detect_semantic(dest)
    print(M["tier"].format(tier=M["tier_full"] if semantic else M["tier_simple"]))
    if not semantic:
        if args.setup_full:
            print(M["raising_full"])
            subprocess.run([sys.executable, "scripts/setup_full.py"], cwd=dest)
        else:
            print(M["full_optional"])
            print(M["full_optional2"])
    sys.stdout.flush()
    init = subprocess.run([sys.executable, "scripts/board_init.py", "advisors",
                           "--semantic-available", "true" if semantic else "false"], cwd=dest)
    if init.returncode != 0:
        # board_init = ЯДРО установки. Упал → доска не инициализирована; молчаливый «✅ Готово»
        # выдал бы сломанную установку за успех. Fail-closed: честная ошибка + ненулевой выход.
        print(M["init_fail"].format(code=init.returncode), file=sys.stderr)
        sys.exit(1)
    write_breadcrumb(dest, semantic)

    print(M["selfcheck"])
    sys.stdout.flush()  # иначе вывод субпроцесса перемешается с буфером print
    subprocess.run([sys.executable, "scripts/board.py", "doctor"], cwd=dest)

    print(M["done"])
    print(M["skill_at"].format(dest=dest))
    print(M["empty_board"])
    print(M["start1"])
    print(M["start2"])
    if not args.in_place:
        print(M["restart"])


if __name__ == "__main__":
    main()
