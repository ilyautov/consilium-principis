#!/usr/bin/env python3
"""Петля исхода U1 — сёрфейсер висящих (#2) + поток записи-решения (#3).

«Продукт или игры разума» решается ТОЛЬКО петлёй исхода: меняет ли совет исход реальных
решений. Но без двух вещей петля не работает:
  #2 Сёрфейсер — без нуджа исходы остаются ⏳ навсегда. `pending_from_journal` вытаскивает
     незакрытые решения из журнала (principis.md/relationship.md) — «вернись и закрой».
  #3 Поток записи — premortem (прогноз), governance (hash-chain) и resolution лежали РЯДОМ,
     но порознь. Связываем: при записи решения фиксируем прогноз исхода → позже сверяем с
     фактом → `loop_status` даёт точность прогнозов; `seal` = tamper-evident снимок (governance).
Запись несёт RATIONALE (почему решил) — чтобы hindsight-bias не переписал прошлое (ловит seal).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibration import parse_decision_log
from premortem import simulation_accuracy
from governance import build_chain


def pending_from_journal(text):
    """#2: заголовки решений с незакрытым исходом (⏳) из markdown-журнала."""
    return [e["title"] for e in parse_decision_log(text) if e["outcome"] == "pending"]


def record_decision(ledger, decision_id, decision, rationale, predicted):
    """#3: записать решение с RATIONALE и прогнозом исхода (число; знак = направление)."""
    ledger.append({"decision_id": decision_id, "decision": decision, "rationale": rationale,
                   "predicted": predicted, "actual": None, "endorsed": None})
    return ledger


def resolve_decision(ledger, decision_id, actual, endorsed):
    """Сверить решение с реальным исходом по факту + одобрил ли задним числом."""
    for r in ledger:
        if r["decision_id"] == decision_id and r["actual"] is None:
            r["actual"], r["endorsed"] = actual, endorsed
            return r
    return None


def pending(ledger):
    """Незакрытые записи леджера (write-сторона)."""
    return [r for r in ledger if r["actual"] is None]


def loop_status(ledger):
    """Сводка петли: открыто/закрыто + точность прогнозов (premortem) + доля одобренных."""
    resolved = [r for r in ledger if r["actual"] is not None]
    endorsed = sum(1 for r in resolved if r.get("endorsed"))
    return {
        "total": len(ledger), "resolved": len(resolved), "pending": len(ledger) - len(resolved),
        "prediction_accuracy": simulation_accuracy(ledger),
        "endorse_rate": endorsed / len(resolved) if resolved else None,
    }


def seal(ledger):
    """Tamper-evident снимок леджера (Барсик hash-chain): переписанное решение рвёт цепь."""
    return build_chain(ledger)
