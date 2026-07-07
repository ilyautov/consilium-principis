"""Изолированный A/B-эксперимент анти-сикофантики (Фаза 1).

Рантайм НЕ импортирует этот модуль. Он читает живые INSTRUCTIONS read-only,
гоняет батарею ±кандидат Rule 15 через инъектируемый call=, судит по 3 осям.
Спека: docs/superpowers/specs/2026-07-07-anti-sycophancy-design.md
"""
import os
import sys
import json
import re

# Модуль в scripts/experiments/, а зависит от scripts/llm_local.py и scripts/mcp_server.py.
_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BATTERY = os.path.join(HERE, "antisycophancy_battery.jsonl")


def load_battery(path=DEFAULT_BATTERY):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
