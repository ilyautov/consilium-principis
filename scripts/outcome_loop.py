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
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibration import parse_decision_log
from premortem import simulation_accuracy
from governance import build_chain

# Ф4 (§6): строка прогноза записи журнала — «- Прогноз: 📐 <predicted> (карта: decisions/…)»
# (её отдаёт save_decision_map как journal_line). Глиф 📐 обязателен: он отличает прогноз
# расчёта от произвольного слова «Прогноз» в тексте решения.
_FORECAST_RE = re.compile(r"(?m)^\s*[-*]?\s*Прогноз:\s*📐\s*(\S.*)$")


def predicted_from_block(block):
    """Ф4: текст прогноза из блока записи журнала. Fail-closed: нет строки «Прогноз: 📐 …» /
    пустой хвост / кривой вход → None (поле predicted у pending-item просто не появляется)."""
    if not isinstance(block, str):
        return None
    m = _FORECAST_RE.search(block)
    return m.group(1).strip() if m else None


def pending_from_journal(text):
    """#2: заголовки решений с незакрытым исходом (⏳) из markdown-журнала."""
    return [e["title"] for e in parse_decision_log(text) if e["outcome"] == "pending"]


def pending_entries(text):
    """#2 + Ф4: незакрытые записи с опциональным прогнозом: [{"title", "predicted"?}].
    Блоки режутся ТЕМ ЖЕ регексом, что parse_decision_log (### …) — zip выравнен по
    построению. predicted появляется только при строке «Прогноз: 📐 …» (fail-closed)."""
    blocks = re.split(r"(?m)^###\s+", text)[1:]
    out = []
    for blk, e in zip(blocks, parse_decision_log(text)):
        if e["outcome"] != "pending":
            continue
        item = {"title": e["title"]}
        pred = predicted_from_block(blk)
        if pred is not None:
            item["predicted"] = pred
        out.append(item)
    return out


def pending_from_files(root):
    """#2 server-side (§4.3 минимум): незакрытые решения из СУЩЕСТВУЮЩИХ журналов —
    principis.md в корне + advisors/*/relationship.md. Второй стор НЕ заводим: читаем те же
    markdown-записи `### …` с ИСХОД: ⏳, что и калибровка. Fail-closed: нечитаемое → пропуск,
    пустой/отсутствующий корень → [] (холодный старт не ломается)."""
    files = [("principis.md", os.path.join(root, "principis.md"))]
    adv_root = os.path.join(root, "advisors")
    try:
        advisors = sorted(os.listdir(adv_root)) if os.path.isdir(adv_root) else []
    except OSError:
        advisors = []
    for d in advisors:
        files.append((f"advisors/{d}/relationship.md",
                      os.path.join(adv_root, d, "relationship.md")))
    out = []
    for label, path in files:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for ent in pending_entries(text):      # Ф4: predicted едет вместе с записью
            ent["source"] = label
            out.append(ent)
    return out


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
