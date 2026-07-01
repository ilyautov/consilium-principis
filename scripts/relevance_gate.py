#!/usr/bin/env python3
"""Borderline-gated судья релевантности — потолок 🟡 для топически-близких-но-НЕ-отвечающих.

Дыра рва: семантический ретрив выдаёт пассажи, топически похожие на вопрос, но НЕ
отвечающие на него (камуфляж смежного домена — напр. Макиавелли про «дезинформацию на
X» вытягивает дословный пассаж про обман). Хост подаёт TRUE 🔵-цитату, ПРИМЕНЁННУЮ к
вопросу, на который она не отвечает. Судья релевантности (relevance_judge.judge, 0-3)
это ловит. Гейтим ТОЛЬКО в неуверенной косинус-полосе [band_lo, band_hi] — вне полосы
уверенность высока (низкий скор → и так 🟡-путь; высокий → истинное попадание) → судью
НЕ зовём, латентность ограничена.

Инварианты:
  • INERT на lexical-бэкенде — полоса калибрована под semantic-скор. CI (ollama-free →
    lexical) не видит изменений.
  • FAIL-CLOSED: судья упал/неуверен in-band → gated (пассаж флагнут / цитата снята),
    НИКОГДА не выдаём 🔵 «на всякий».
  • ADDITIVE: слой релевантности ПОВЕРХ verbatim-тиринга — _fidelity_check не трогаем.
  • Судья зовётся ТОЛЬКО для in-band на semantic (латентный контракт).

`judge_fn` — TEST SEAM (в проде = relevance_judge.judge).
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Дефолты — семантически-калиброванная полоса неуверенности + порог «релевантно».
# band_hi=0.65 НАМЕРЕННО выше камуфляж-потолка 0.612 (Machiavelli) / 0.596 (Marcus) из
# adversarial-eval: OOC-камуфляж и отвечающие спаны (0.537–0.689) ПЕРЕСЕКАЮТСЯ на
# [0.537, 0.612] — за это и отвечает судья. НЕ «прибирать» назад к 0.60: (0.60, 0.612] —
# top-edge leak (худший наблюдённый кейс 0.612 уходил бы ungated). Отвечающие в 0.60–0.65
# наберут rel≥2 и пройдут → цена = ограниченное число лишних in-band вызовов судьи (его работа).
BAND_LO = 0.45
BAND_HI = 0.65
REL_THRESHOLD = 2


def _root():
    return os.path.dirname(HERE)


def _config_path():
    return os.path.join(_root(), "board_config.json")


def _gate_config(advisor_dir=None):
    """Дефолты + опциональные оверрайды из board_config.json ключа `relevance_gate`.
    Форма: {"enabled":bool, "band_lo":float, "band_hi":float, "rel_threshold":int}.
    По умолчанию enabled=True. Любая ошибка чтения → дефолты (гейт активен, fail-closed)."""
    cfg = {"enabled": True, "band_lo": BAND_LO, "band_hi": BAND_HI,
           "rel_threshold": REL_THRESHOLD}
    try:
        with open(_config_path(), encoding="utf-8") as f:
            raw = json.load(f).get("relevance_gate")
    except Exception:
        raw = None
    if isinstance(raw, dict):
        # Коэрсим ЗНАЧЕНИЯ per-key: битое значение (напр. band_lo:"0.45") НЕ должно доходить
        # до _in_band и валить retrieve/cite TypeError'ом. Провал коэрса → default (fail-closed
        # = гейт активен). enabled через bool (не бросает).
        _coerce = {"enabled": bool, "band_lo": float, "band_hi": float, "rel_threshold": int}
        for k, fn in _coerce.items():
            if k in raw:
                try:
                    cfg[k] = fn(raw[k])
                except (TypeError, ValueError):
                    pass
    return cfg


def is_semantic(advisor_dir) -> bool:
    """True iff резолвнутый бэкенд = semantic (полоса калибрована под его скор).
    Любая ошибка → False (гейт инертен = безопасно)."""
    try:
        import engine as _engine
        eng = _engine.resolve_engine(advisor_dir, prefer=os.getenv("EVAL_ENGINE"))
        return getattr(eng, "name", "") == "semantic"
    except Exception:
        return False


def _default_judge(query, passage):
    import relevance_judge
    return relevance_judge.judge(query, passage)


def _in_band(score, cfg):
    return (isinstance(score, (int, float))
            and cfg["band_lo"] <= score <= cfg["band_hi"])


def gate_passage(query, passage, advisor_dir, judge_fn=None, cfg=None) -> dict:
    """Пассаж {text,score,source}. Вне semantic ИЛИ score вне полосы → возврат КАК ЕСТЬ.
    In-band → судья: <threshold → COPY с relevance_gated=True (пассаж НЕ выбрасываем —
    прозрачность), >=threshold → без флага (+ annotate relevance=judge).
    FAIL-CLOSED: судья бросил → gated (relevance_gated=True)."""
    cfg = cfg or _gate_config(advisor_dir)
    if not cfg.get("enabled", True):
        return passage
    if not is_semantic(advisor_dir) or not _in_band(passage.get("score"), cfg):
        return passage
    jf = judge_fn if judge_fn is not None else _default_judge
    try:
        rel = jf(query, passage.get("text", ""))
    except Exception:
        out = dict(passage)
        out["relevance_gated"] = True                  # fail-closed
        return out
    if rel < cfg["rel_threshold"]:
        out = dict(passage)
        out["relevance_gated"] = True
        return out
    out = dict(passage)
    out["relevance"] = rel
    return out


def gate_quote(query, quote_text, score, advisor_dir, judge_fn=None, cfg=None) -> bool:
    """keep=True / withhold=False. Вне semantic ИЛИ score вне полосы → keep (True).
    In-band → судья: keep iff judge>=threshold. FAIL-CLOSED: судья бросил → withhold
    (False). Для cite (обещает «это ТА самая цитата») снять не-отвечающую верно — путь
    схлопывается в честный 🟡 «дословного ответа нет»."""
    cfg = cfg or _gate_config(advisor_dir)
    if not cfg.get("enabled", True):
        return True
    if not is_semantic(advisor_dir) or not _in_band(score, cfg):
        return True
    jf = judge_fn if judge_fn is not None else _default_judge
    try:
        rel = jf(query, quote_text)
    except Exception:
        return False                                   # fail-closed withhold
    return rel >= cfg["rel_threshold"]
