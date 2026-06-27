#!/usr/bin/env python3
"""Зеркало дрейфа — заявленное vs выбираемое. Финал спора про вектор (2026-06-28).

Движок НЕ знает вектор юзера как ЦЕЛЬ (знать→оптимизировать = захват). Он ОТРАЖАЕТ:
  • дрейф заявленного вектора во времени (сменился — это сигнал, не ошибка);
  • разрыв между тем, что юзер ГОВОРИТ, что хочет, и тем, что реально и ОДОБРЕННО выбирает.
Метрика выбираемого — по ОДОБРЕННЫМ задним числом решениям (как калибровка: не «послушался»,
а «одобрил»). Зеркало не советует и ни к чему не тянет — возвращает агентность. Анти-MiroFish:
не предсказывает будущее, показывает кем ты становишься. Ядро чистое → детерминированно.
"""
import re
from collections import Counter


def stated_drift(stated):
    """Последовательность заявленных векторов → дрейф. stated: [{when, vector}] по времени."""
    vs = [s["vector"] for s in stated]
    transitions = [(vs[i], vs[i + 1]) for i in range(len(vs) - 1) if vs[i] != vs[i + 1]]
    return {"history": vs, "current": vs[-1] if vs else None,
            "changed": len(transitions) > 0, "transitions": transitions}


def revealed_theme(decisions):
    """Доминирующая тема среди ОДОБРЕННЫХ решений (что реально тебе служит). None, если нет
    одобренных. decisions: [{theme, endorsed}]."""
    themes = [d["theme"] for d in decisions if d.get("endorsed")]
    if not themes:
        return None
    theme, count = Counter(themes).most_common(1)[0]
    return {"theme": theme, "count": count, "total_endorsed": len(themes)}


def _aligned(stated_vector, theme):
    """Совпадает ли выбираемая тема с заявленным вектором (подстрока или общее слово)."""
    s, t = stated_vector.lower(), theme.lower()
    if t in s:
        return True
    return bool(set(re.findall(r"\w+", t)) & set(re.findall(r"\w+", s)))


def mirror_report(stated, decisions):
    """Зеркало: дрейф заявленного + разрыв с выбираемым. Не советует — отражает."""
    drift = stated_drift(stated)
    rev = revealed_theme(decisions)
    if not stated or rev is None:
        return {"sufficient": False, "stated_drift": drift, "revealed": rev,
                "note": "мало данных: нужен заявленный вектор И одобренные решения"}
    cur = drift["current"]
    aligned = _aligned(cur, rev["theme"])
    note = (f"совпадает: говоришь «{cur}», и одобренные выборы про «{rev['theme']}»" if aligned
            else f"РАЗРЫВ: говоришь «{cur}», а одобренные выборы кластеризуются на «{rev['theme']}»")
    if drift["changed"]:
        note += f" · вектор сменился ({' → '.join(drift['history'])}) — это сигнал, не ошибка"
    return {"sufficient": True, "stated_now": cur, "stated_changed": drift["changed"],
            "revealed_dominant": rev["theme"], "aligned": aligned,
            "stated_drift": drift, "revealed": rev, "note": note}
