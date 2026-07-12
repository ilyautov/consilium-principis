"""Регрессионный гард: ни один тул не должен «потемнеть».

Тул считается проведённым (не тёмным), если его имя встречается:
  - в INSTRUCTIONS (проводка в правила поведения хоста), ИЛИ
  - в описании любого ДРУГОГО тула (виден через тул-родитель), ИЛИ
  - в recipes.json (проведён как рецепт; list_recipes есть в INSTRUCTIONS), ИЛИ
  - в реестре внутренних тулов docs/dev/internal-tools.md (осознанно не рекламируется).
Иначе — тёмный тул, и тест падает с его именем.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server as m  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _internal_registry():
    path = os.path.join(_ROOT, "docs", "dev", "internal-tools.md")
    text = open(path, encoding="utf-8").read()
    # Машиночитаемый блок: секция "## Реестр внутренних тулов" → ```text ... ```
    block = re.search(r"```text\n(.*?)```", text, re.DOTALL)
    assert block, "В docs/dev/internal-tools.md нет ```text``` блока с реестром"
    ids = {line.strip() for line in block.group(1).splitlines() if line.strip()}
    return ids


def _recipes_text():
    path = os.path.join(_ROOT, "recipes.json")
    return open(path, encoding="utf-8").read()


def test_every_tool_is_surfaced_or_declared_internal():
    tools = set(m.TOOLS.keys())
    instr = m.INSTRUCTIONS
    all_descs = " ".join(t.get("description", "") for t in m.TOOLS.values())
    recipes = _recipes_text()
    internal = _internal_registry()
    dark = []
    for name in sorted(tools):
        if name in instr:            # проведён в правила хоста
            continue
        if name in all_descs:        # виден через описание тула-сиблинга
            continue
        if name in recipes:          # проведён как рецепт (list_recipes в INSTRUCTIONS)
            continue
        if name in internal:         # явно помечен внутренним
            continue
        dark.append(name)
    assert not dark, f"Тёмные тулы (нигде не проведены и не помечены внутренними): {dark}"


def test_internal_registry_matches_expected():
    assert _internal_registry() == {"validate_manifest", "job_status", "ollama_ensure",
                                    "stability", "atomic_grounding", "catalog_verify"}


def test_federation_tools_surfaced_in_instructions():
    for name in ("federation_open", "federation_poll", "federation_assemble",
                 "federation_claim", "federation_submit", "federation_heartbeat"):
        assert name in m.INSTRUCTIONS, "%s не проведён в INSTRUCTIONS (тёмный федерация-тул)" % name


def test_federation_block_numbered_and_write_consent():
    nums = [int(n) for n in re.findall(r"(?m)^(\d+)\.\s", m.INSTRUCTIONS)]
    assert 15 in nums, "федерация-блок не пронумерован (ожидалось правило 15)"
    # write-тулы не прячем: рядом с federation в инструкциях есть отсылка к Rule 0 (запись проговори)
    fed_seg = m.INSTRUCTIONS[m.INSTRUCTIONS.index("federation_open"):]
    assert "Rule 0" in fed_seg, "федерация-блок не проводит write-consent (Rule 0) для пишущих тулов"
