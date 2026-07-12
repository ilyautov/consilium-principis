"""Rule-based судья федерации (MVP). Ноль LLM. PASS/FIX/ESCALATE — заимствованные явные состояния
(advisor-orchestrator-worker): PASS = заземлён, FIX = редиспатч/доработка, ESCALATE = нет кандидата."""
import re

_DIVERGENCE_THRESHOLD = 0.5


def _tokens(text):
    return set(re.findall(r"[a-zа-я0-9]+", (text or "").lower()))


def _quote_statuses(cand):
    return [q.get("status", "🟡") for q in (cand or {}).get("quotes", [])]


def score_candidate(cand):
    """Рубрика репрезентанта: 🔵×10 + 🟢×3 + (есть непустой аргумент → 1)."""
    st = _quote_statuses(cand)
    blue = st.count("🔵")
    green = st.count("🟢")
    has_arg = 1 if (cand or {}).get("argument", "").strip() else 0
    return blue * 10 + green * 3 + has_arg


def _jaccard(a, b):
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 1.0


def divergence(cands):
    """Расхождение аргументов = 1 − средняя попарная Jaccard-схожесть токенов. Пустые/пробельные
    аргументы ИСКЛЮЧАЮТСЯ (не несут взгляда — иначе слот-флуд пустышками занижал бы расхождение).
    <2 непустых → low (нечего сравнивать). Сохраняем ЧИСЛО (не схлопываем в best-of-N)."""
    toks = [t for t in (_tokens(c.get("argument", "")) for c in cands) if t]
    if len(toks) < 2:
        return {"score": 0.0, "level": "low", "flagged": False}
    sims = []
    for i in range(len(toks)):
        for j in range(i + 1, len(toks)):
            sims.append(_jaccard(toks[i], toks[j]))
    mean_sim = sum(sims) / len(sims)
    score = round(1.0 - mean_sim, 4)
    level = "high" if score >= _DIVERGENCE_THRESHOLD else "low"
    return {"score": score, "level": level, "flagged": level == "high"}


def verdict(cand):
    """PASS — есть 🔵; FIX — кандидат есть, но не заземлён (нет 🔵); ESCALATE — кандидата нет."""
    if cand is None:
        return "ESCALATE"
    st = _quote_statuses(cand)
    if "🔵" in st:
        return "PASS"
    return "FIX"
