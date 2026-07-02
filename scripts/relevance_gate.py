#!/usr/bin/env python3
"""Borderline-gated судья релевантности — потолок 🟡 для топически-близких-но-НЕ-отвечающих.

Дыра рва: семантический ретрив выдаёт пассажи, топически похожие на вопрос, но НЕ
отвечающие на него (камуфляж смежного домена — напр. Макиавелли про «дезинформацию на
X» вытягивает дословный пассаж про обман). Хост подаёт TRUE 🔵-цитату, ПРИМЕНЁННУЮ к
вопросу, на который она не отвечает. Судья релевантности (relevance_judge.judge, 0-3)
это ловит. Полоса действия судьи АСИММЕТРИЧНА по поверхностям:
  • gate_passage (retrieve): судим ТОЛЬКО в полосе [band_lo, band_hi] — sub-band пассажи
    уже покрыты host-abstention-рамкой (0.50), флаг там transparency-only;
  • gate_quote (cite): для ЦИТАТ низкий косинус ≠ безопасно — у _cite нет abstention-пола,
    verbatim не-отвечающая цитата на 0.44 уходила как 🔵 (M1 sub-band bypass). Судью
    пропускает ТОЛЬКО score > band_hi (калиброванный верх: top-edge утечек на 0.65 нет).
Выше band_hi уверенность высока (истинное попадание) → судью НЕ зовём, латентность
ограничена.

Инварианты:
  • INERT на lexical-бэкенде — полоса калибрована под semantic-скор. CI (ollama-free →
    lexical) не видит изменений.
  • FAIL-CLOSED: судья упал/неуверен → gated (пассаж флагнут / цитата снята),
    НИКОГДА не выдаём 🔵 «на всякий».
  • ADDITIVE: слой релевантности ПОВЕРХ verbatim-тиринга — _fidelity_check не трогаем.
  • Судья зовётся ТОЛЬКО на semantic; retrieve — только in-band (латентный контракт),
    cite — всё, что не выше band_hi.

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
JUDGE_BACKEND_DEFAULT = "auto"          # §2.2: host|ollama|api|auto (резолюция — judge_backend.py)


def _root():
    return os.path.dirname(HERE)


def _config_path():
    return os.path.join(_root(), "board_config.json")


def _coerce_enabled(val):
    """bool()-коэрсия строк — наивный bool("false") == True (Python), молча игнорирует
    намерение юзера. Реальные bool/числа → bool() как есть; строки регистронезависимо
    "true"/"false" → соответствующий bool; ЛЮБОЕ другое значение (мусор, "yes", список,
    ...) → дефолт True (fail-closed = гейт активен), никогда не бросает."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        low = val.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
        return True
    try:
        return bool(val)
    except Exception:
        return True


def _coerce_backend(val):
    """judge_backend: только host|ollama|api|auto; любой мусор → ValueError → дефолт auto
    (fail-closed: опечатка в конфиге не должна молча отключить резолюцию)."""
    v = str(val).strip().lower()
    if v in ("host", "ollama", "api", "auto"):
        return v
    raise ValueError(val)


def _gate_config(advisor_dir=None):
    """Дефолты + опциональные оверрайды из board_config.json ключа `relevance_gate`.
    Форма: {"enabled":bool, "band_lo":float, "band_hi":float, "rel_threshold":int,
    "judge_backend":str}. По умолчанию enabled=True, judge_backend=auto. Любая ошибка
    чтения → дефолты (гейт активен, fail-closed).
    §3.2: поверх глобального конфига оверлеится PER-ADVISOR калибровка полосы
    (advisors/<slug>/build/calibration.json → relevance_gate.band_lo/band_hi) —
    пишет calibrate_advisor.py; битые/инвертированные значения игнорируются
    (остаётся глобальная полоса). enabled/rel_threshold/judge_backend калибровка
    НЕ трогает — это политика, не распределение скоров."""
    cfg = {"enabled": True, "band_lo": BAND_LO, "band_hi": BAND_HI,
           "rel_threshold": REL_THRESHOLD, "judge_backend": JUDGE_BACKEND_DEFAULT}
    try:
        with open(_config_path(), encoding="utf-8") as f:
            raw = json.load(f).get("relevance_gate")
    except Exception:
        raw = None
    if isinstance(raw, dict):
        # Коэрсим ЗНАЧЕНИЯ per-key: битое значение (напр. band_lo:"0.45") НЕ должно доходить
        # до _in_band и валить retrieve/cite TypeError'ом. Провал коэрса → default (fail-closed
        # = гейт активен). enabled — через _coerce_enabled (bool() тупо на строках: "false" → True).
        _coerce = {"enabled": _coerce_enabled, "band_lo": float, "band_hi": float,
                   "rel_threshold": int, "judge_backend": _coerce_backend}
        for k, fn in _coerce.items():
            if k in raw:
                try:
                    cfg[k] = fn(raw[k])
                except (TypeError, ValueError):
                    pass
    if cfg["band_lo"] > cfg["band_hi"]:
        # Инвертированная полоса — _in_band никогда не true → гейт молча инертен ВНУТРИ
        # полосы (fail-OPEN направление). Откатываем ОБА оверрайда к калиброванным дефолтам.
        cfg["band_lo"] = BAND_LO
        cfg["band_hi"] = BAND_HI
    # §3.2: per-advisor полоса из build/calibration.json (приоритетнее глобальной —
    # она посчитана по РАСПРЕДЕЛЕНИЮ ЭТОГО корпуса). Валидна только пара lo < hi.
    try:
        import engine as _engine
        cal = _engine.load_calibration(advisor_dir)
    except Exception:
        cal = None
    if cal:
        rg = cal.get("relevance_gate")
        if isinstance(rg, dict):
            try:
                lo, hi = float(rg["band_lo"]), float(rg["band_hi"])
                if lo < hi:
                    cfg["band_lo"], cfg["band_hi"] = lo, hi
            except (KeyError, TypeError, ValueError):
                pass                                   # битая калибровка → глобальная полоса
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


def _default_judge(query, passage, source=None):
    import relevance_judge
    return relevance_judge.judge(query, passage, source=source)


def _call_judge(jf, query, text, source):
    """source прокидываем ТОЛЬКО когда он есть — judge_fn старой сигнатуры
    (query, passage) без source продолжает работать, пока source не подаётся.
    (jf с source, но старой сигнатурой → TypeError → у вызывающих fail-closed.)"""
    if source:
        return jf(query, text, source=source)
    return jf(query, text)


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
        rel = _call_judge(jf, query, passage.get("text", ""), passage.get("source"))
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


def gate_quote(query, quote_text, score, advisor_dir, judge_fn=None, cfg=None,
               source=None) -> bool:
    """keep=True / withhold=False. Вне semantic → keep (True). На semantic судью
    пропускает ТОЛЬКО score > band_hi (калибровано: top-edge утечек на 0.65 не
    наблюдалось); всё остальное (in-band, SUB-BAND, None-score) → судья: keep iff
    judge>=threshold. FAIL-CLOSED: судья бросил → withhold (False).

    Для ЦИТАТ низкий косинус ≠ безопасно — асимметрия с gate_passage. У retrieve
    низкий скор и так уходит в 🟡-путь (host abstention 0.50), а _cite БЕЗ пола
    abstention возвращал дословную цитату на косинусе 0.44 как 🔵 — verbatim
    не-отвечающая цитата и есть сетап misapply (измерено: M1, 4 утечки Marcus,
    судья по ним давал сплошные нули → судить sub-band = снять все четыре).
    Снятая цитата → путь схлопывается в честный 🟡 «дословного ответа нет»."""
    cfg = cfg or _gate_config(advisor_dir)
    if not cfg.get("enabled", True):
        return True
    if not is_semantic(advisor_dir):
        return True
    if isinstance(score, (int, float)) and score > cfg["band_hi"]:
        return True                                    # единственный не-судимый путь
    jf = judge_fn if judge_fn is not None else _default_judge
    try:
        rel = _call_judge(jf, query, quote_text, source)
    except Exception:
        return False                                   # fail-closed withhold
    return rel >= cfg["rel_threshold"]
