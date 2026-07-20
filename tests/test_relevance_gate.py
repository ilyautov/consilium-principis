"""Borderline-gated судья релевантности: гейт ТОЛЬКО в неуверенной косинус-полосе.

Закрывает дыру рва: семантический ретрив выдаёт топически-близкие-но-НЕ-отвечающие
пассажи на камуфляж смежного домена (напр. Макиавелли про «дезинформацию на X» →
дословный 🔵-пассаж про обман, но он НЕ отвечает на вопрос). Судья это ловит.

Инварианты (тесты стерегут):
  • Судья недоступен (SIMPLE-пол без ollama) → гейт инертен → CI без ollama = 0 изменений.
  • M4: вне semantic-режима с ДОСТУПНЫМ судьёй verbatim-кандидаты судятся все; полоса
    band — только на semantic-шкале (сырой косинус, при смеси — поле raw_score).
  • Судья зовётся на semantic ТОЛЬКО для in-band (латентный контракт → call-count).
  • FAIL-CLOSED: судья упал/неуверен → gated (пассаж флагнут / цитата снята).
Всё офлайн: judge_fn мокается, is_semantic/_judge_available монки-патчатся.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pytest
import relevance_gate


class Counter:
    """judge_fn-заглушка со счётчиком вызовов (латентный контракт) + захват source."""
    def __init__(self, ret):
        self._ret = ret
        self.calls = 0
        self.last_source = None

    def __call__(self, query, passage, source=None):
        self.calls += 1
        self.last_source = source
        if isinstance(self._ret, Exception):
            raise self._ret
        return self._ret


def _semantic(monkeypatch, val=True):
    monkeypatch.setattr(relevance_gate, "is_semantic", lambda advisor_dir, prefer=None: val)


def _judge_avail(monkeypatch, val=True):
    """M4: пин доступности серверного судьи (ollama/api жив). Вне semantic-режима гейт
    судит только когда судья доступен; пин делает тест герметичным (без пробинга сети)."""
    monkeypatch.setattr(relevance_gate, "_judge_available", lambda advisor_dir: val)


# ───────────────────────── gate_passage ─────────────────────────

def test_gate_passage_inband_low_judge_flags(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(1)
    p = {"text": "topically similar", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True
    assert j.calls == 1
    assert p.get("relevance_gated") is None            # не мутирует оригинал (COPY)


def test_gate_passage_inband_high_judge_passes(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(3)
    p = {"text": "answers it", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert out.get("relevance") == 3
    assert j.calls == 1


def test_gate_passage_above_band_no_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(0)
    p = {"text": "strong", "score": 0.70, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0                                # латентный контракт: судья НЕ зван


def test_gate_passage_below_band_no_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(0)
    p = {"text": "weak", "score": 0.30, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0


def test_gate_passage_not_semantic_no_judge(monkeypatch):
    _semantic(monkeypatch, val=False)                  # lexical → гейт инертен
    _judge_avail(monkeypatch, val=False)               # судья недоступен (M4: иначе судили бы)
    j = Counter(0)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0


def test_gate_passage_judge_raises_fail_closed(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(RuntimeError("boom"))
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True          # fail-closed
    assert j.calls == 1


# ───────────────────────── gate_quote ─────────────────────────

def test_gate_quote_inband_low_withholds(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(1)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_inband_high_keeps(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(2)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 1


def test_gate_quote_out_of_band_keeps_no_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.90, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_above_band_hi_keeps_no_judge(monkeypatch):
    # 0.70 > band_hi 0.65 — калиброванный верх: top-edge утечек на 0.65 не наблюдалось.
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.70, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_not_semantic_keeps_no_judge(monkeypatch):
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch, val=False)               # судья недоступен → прежний keep
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_not_semantic_subband_keeps_no_judge(monkeypatch):
    # lexical + судья недоступен → sub-band тоже инертен (CI без ollama без изменений)
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch, val=False)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.30, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_judge_raises_fail_closed_withhold(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(RuntimeError("boom"))
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is False
    assert j.calls == 1


# ── M1 (sub-band bypass): для ЦИТАТ низкий косинус ≠ безопасно — судим ──────

def test_gate_quote_subband_judged_zero_withheld(monkeypatch):
    # Был KEEP (out-of-band-low → keep) → _cite отдавал 🔵 на косинусе 0.44 без судьи.
    # Теперь: sub-band → СУДИТСЯ; judge=0 → снята.
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.30, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_subband_judged_high_kept(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(3)
    assert relevance_gate.gate_quote("q", "text", 0.30, "adv", judge_fn=j) is True
    assert j.calls == 1


def test_gate_quote_subband_judge_raises_fail_closed(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(RuntimeError("boom"))
    assert relevance_gate.gate_quote("q", "text", 0.30, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_none_score_is_judged(monkeypatch):
    # None-скор (primary не находил кандидата) → судим (раньше _cite подставлял midpoint —
    # правило упрощено: для cite судью пропускает ТОЛЬКО score > band_hi).
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", None, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_none_score_judge_high_kept(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(2)
    assert relevance_gate.gate_quote("q", "text", None, "adv", judge_fn=j) is True
    assert j.calls == 1


# ── Fix 2: source прокидывается судье (структурный контекст) ────────────────

def test_gate_quote_passes_source_to_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(3)
    relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j,
                              source="The Prince, ch. XII")
    assert j.calls == 1
    assert j.last_source == "The Prince, ch. XII"


def test_gate_quote_no_source_backward_compat_two_arg_judge(monkeypatch):
    # judge_fn старой сигнатуры (query, passage) БЕЗ source — работает, если source не дан
    _semantic(monkeypatch)
    calls = {"n": 0}
    def legacy_judge(query, passage):
        calls["n"] += 1
        return 3
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=legacy_judge) is True
    assert calls["n"] == 1


def test_gate_passage_passes_source_to_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(3)
    p = {"text": "answers it", "score": 0.50, "source": "Meditations, book IV"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert j.calls == 1
    assert j.last_source == "Meditations, book IV"
    assert not out.get("relevance_gated")


# ───────────────────────── config override ─────────────────────────

def test_config_override_disables_gate(monkeypatch):
    _semantic(monkeypatch)
    cfg = {"enabled": False, "band_lo": 0.45, "band_hi": 0.60, "rel_threshold": 2}
    monkeypatch.setattr(relevance_gate, "_gate_config", lambda advisor_dir: cfg)
    j = Counter(0)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0                                # enabled=false → инертен
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_config_band_override_respected(monkeypatch):
    _semantic(monkeypatch)
    cfg = {"enabled": True, "band_lo": 0.10, "band_hi": 0.20, "rel_threshold": 2}
    monkeypatch.setattr(relevance_gate, "_gate_config", lambda advisor_dir: cfg)
    j = Counter(1)
    # 0.50 теперь ВЫШЕ узкой полосы [0.10,0.20] → судья не зван, не флагнут
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0


def test_default_config_values():
    assert relevance_gate.BAND_LO == 0.45
    assert relevance_gate.BAND_HI == 0.65          # выше камуфляж-потолка 0.612 (C1)
    assert relevance_gate.REL_THRESHOLD == 2


def test_gate_passage_061_in_band_is_judged(monkeypatch):
    # C1: 0.61 (внутри камуфляж-оверлапа, ≤ band_hi 0.65) ДОЛЖЕН судиться, не пропускаться.
    _semantic(monkeypatch)
    j = Counter(1)                                  # судья: косвенно → gated
    p = {"text": "camouflage span @0.61", "score": 0.61, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert j.calls == 1                             # судья ЗВАН (раньше 0.61 > 0.60 → пропуск)
    assert out.get("relevance_gated") is True


def test_gate_quote_061_in_band_is_judged(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(1)
    assert relevance_gate.gate_quote("q", "span", 0.61, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_config_malformed_value_falls_back_no_crash(monkeypatch, tmp_path):
    # I2: строковое band-значение НЕ должно валить _in_band TypeError'ом → дефолт (fail-closed).
    import json
    cfgfile = tmp_path / "board_config.json"
    cfgfile.write_text(json.dumps({"relevance_gate": {"band_lo": "0.45", "band_hi": "0.65",
                                                      "rel_threshold": "x", "enabled": True}}),
                       encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(cfgfile))
    cfg = relevance_gate._gate_config("adv")
    assert cfg["band_lo"] == relevance_gate.BAND_LO      # битая строка → дефолт
    assert cfg["band_hi"] == relevance_gate.BAND_HI
    assert cfg["rel_threshold"] == relevance_gate.REL_THRESHOLD
    # и гейт функционирует без исключения
    _semantic(monkeypatch)
    j = Counter(1)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True


def test_config_enabled_string_false_disables_gate(monkeypatch, tmp_path):
    # Дефект: bool("false") == True в питоне — строка "false" молча оставляла гейт
    # активным (безопасное направление, но игнорирует явное намерение юзера). Фикс:
    # регистронезависимая строковая коэрсия.
    import json
    cfgfile = tmp_path / "board_config.json"
    cfgfile.write_text(json.dumps({"relevance_gate": {"enabled": "false"}}), encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(cfgfile))
    cfg = relevance_gate._gate_config("adv")
    assert cfg["enabled"] is False
    _semantic(monkeypatch)
    j = Counter(0)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0                                # enabled="false" → инертен, судья не зван


def test_config_enabled_string_true_keeps_gate_active(monkeypatch, tmp_path):
    import json
    cfgfile = tmp_path / "board_config.json"
    cfgfile.write_text(json.dumps({"relevance_gate": {"enabled": "true"}}), encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(cfgfile))
    cfg = relevance_gate._gate_config("adv")
    assert cfg["enabled"] is True
    _semantic(monkeypatch)
    j = Counter(1)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True
    assert j.calls == 1


def test_config_enabled_garbage_falls_back_default_true(monkeypatch, tmp_path):
    # Мусорное значение (число 123, не "true"/"false") → дефолт True (fail-closed = активен).
    import json
    cfgfile = tmp_path / "board_config.json"
    cfgfile.write_text(json.dumps({"relevance_gate": {"enabled": 123}}), encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(cfgfile))
    cfg = relevance_gate._gate_config("adv")
    assert cfg["enabled"] is True


def test_config_inverted_band_falls_back_to_defaults(monkeypatch, tmp_path):
    # Инвертированная полоса (band_lo > band_hi после коэрсии) — _in_band никогда true →
    # гейт молча инертен ВНУТРИ полосы (fail-OPEN). Откат ОБОИХ к калиброванным дефолтам.
    import json
    cfgfile = tmp_path / "board_config.json"
    cfgfile.write_text(json.dumps({"relevance_gate": {"band_lo": 0.7, "band_hi": 0.5}}),
                       encoding="utf-8")
    monkeypatch.setattr(relevance_gate, "_config_path", lambda: str(cfgfile))
    cfg = relevance_gate._gate_config("adv")
    assert cfg["band_lo"] == relevance_gate.BAND_LO
    assert cfg["band_hi"] == relevance_gate.BAND_HI
    # калиброванная полоса по-прежнему работает: 0.50-скор пассаж ДОЛЖЕН судиться
    _semantic(monkeypatch)
    j = Counter(1)
    p = {"text": "x", "score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True
    assert j.calls == 1


# ───────────────────────── wiring in _cite ─────────────────────────

def _force_semantic_cite(monkeypatch, judge_ret):
    """_cite прогоняется через семантический путь с подставным ретривом и судьёй."""
    import mcp_server
    _semantic(monkeypatch)
    # подставной пул кандидатов с in-band score (0.50) — так гейт активируется
    fake = [{"text": "All warfare is based on deception.", "score": 0.50, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    # дословность реальна (verbatim-тир не трогаем) — форсим 🔵 через _fidelity_check
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    monkeypatch.setattr(relevance_judge, "judge",
                        lambda q, p, model=None, source=None: judge_ret)
    return mcp_server


def test_cite_wiring_judge_rejects_collapses_to_yellow(monkeypatch):
    mcp_server = _force_semantic_cite(monkeypatch, judge_ret=0)  # судья всё режет
    r = mcp_server._cite("advisors/machiavelli", "counter disinformation on X", use_kernels=False)
    assert r["quotes"] == [] and r["best"] is None and r["marker"] == "🟡"


def test_cite_wiring_judge_accepts_returns_quotes(monkeypatch):
    mcp_server = _force_semantic_cite(monkeypatch, judge_ret=3)  # судья пропускает
    r = mcp_server._cite("advisors/machiavelli", "deception in war", use_kernels=False)
    assert r["quotes"] and r["best"]["marker"] == "🔵"


def test_cite_wiring_lexical_unaffected(monkeypatch):
    """CI (lexical, судья недоступен) — гейт инертен: судья не зван, поведение как раньше."""
    import mcp_server
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch, val=False)               # M4: иначе доступный судья судил бы
    fake = [{"text": "All warfare is based on deception.", "score": 0.50, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    called = {"n": 0}
    def _spy(q, p, model=None, source=None):
        called["n"] += 1
        return 0
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", "deception in war", use_kernels=False)
    assert r["quotes"] and r["best"]["marker"] == "🔵"
    assert called["n"] == 0                            # lexical → судья НЕ зван


def test_cite_wiring_secondary_query_quote_still_judged(monkeypatch):
    # I1: цитата, которую вытащил ВТОРИЧНЫЙ запрос (высокий косинус к СВОЕЙ теме, вне полосы),
    # но primary НЕ находил — ДОЛЖНА судиться против primary, а не пройти по max-across-score.
    import mcp_server
    _semantic(monkeypatch)
    quote = "All warfare is based on deception."

    def fake_retrieve(q, d, top_k=8):
        # primary («primary») не находит ничего; вторичный («secondary») — на 0.90 (вне полосы)
        if q == "secondary":
            return [{"text": quote, "score": 0.90, "source": "src"}]
        return []

    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    calls = {"n": 0}
    def _spy(q, p, model=None, source=None):
        calls["n"] += 1
        return 0                                        # судья режет
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", ["primary", "secondary"], use_kernels=False)
    assert calls["n"] >= 1                              # судья ЗВАН на kernel/secondary-цитате
    assert r["quotes"] == [] and r["marker"] == "🟡"    # снята → честный 🟡 (не утекла как 🔵)


def test_cite_subband_candidate_judged_and_withheld(monkeypatch):
    # M1 (sub-band bypass): кандидат с primary-косинусом 0.44 < band_lo РАНЬШЕ шёл в 🔵 без
    # судьи (out-of-band-low → keep, а abstention-пола у _cite нет). Теперь судится; judge=0 → 🟡.
    import mcp_server
    _semantic(monkeypatch)
    fake = [{"text": "All warfare is based on deception.", "score": 0.44, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    calls = {"n": 0}
    def _spy(q, p, model=None, source=None):
        calls["n"] += 1
        return 0
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", "adjacent-domain camouflage q", use_kernels=False)
    assert calls["n"] == 1                              # sub-band → судья ЗВАН (раньше 0)
    assert r["quotes"] == [] and r["marker"] == "🟡"


def test_cite_passes_source_into_judge(monkeypatch):
    # Fix 2 wiring: _cite прокидывает fc["source"] судье (структурный контекст промпта).
    import mcp_server
    _semantic(monkeypatch)
    fake = [{"text": "All warfare is based on deception.", "score": 0.50,
             "source": "Art of War, ch. I"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True,
                                      "source": "Art of War, ch. I"})
    import relevance_judge
    seen = {}
    def _spy(q, p, model=None, source=None):
        seen["source"] = source
        return 3
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", "deception in war", use_kernels=False)
    assert r["quotes"]
    assert seen["source"] == "Art of War, ch. I"


def test_retrieve_passes_source_into_judge(monkeypatch):
    # Fix 2 wiring: _retrieve → gate_passage → судья видит p["source"].
    import mcp_server
    _semantic(monkeypatch)
    fake = [{"text": "topical passage", "score": 0.50, "source": "Meditations, book II"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=3: list(fake))
    import relevance_judge
    seen = {}
    def _spy(q, p, model=None, source=None):
        seen["source"] = source
        return 3
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._retrieve("q", "advisors/machiavelli")
    assert r["passages"]
    assert seen["source"] == "Meditations, book II"


# ── M4 (вариант A): гейт защищает и вне semantic-cosine мира ─────────────
# Политика: verbatim-кандидаты СУДЯТСЯ независимо от retrieval-движка, когда
# серверный судья доступен (_judge_available). Полоса band — ТОЛЬКО на
# semantic-шкале (сырой косинус; при hybrid_alpha-смеси/RRF — поле raw_score);
# вне semantic-шкалы судим всех. Судья недоступен → прежний путь
# (keep/pass-through) — офлайн-инвариант SIMPLE-пола не ломается.

def test_gate_quote_nonsemantic_judge_available_zero_withheld(monkeypatch):
    # retrieval_mode=hybrid (is_semantic False) + ЖИВОЙ судья: не-отвечающая verbatim
    # цитата (judge=0) снимается — раньше был молчаливый keep (дыра M4).
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_nonsemantic_judge_available_high_kept(monkeypatch):
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    j = Counter(3)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 1


def test_gate_quote_nonsemantic_high_score_still_judged(monkeypatch):
    # lexical/RRF-скор 0.95 — НЕ semantic-шкала: auto-keep по band_hi не срабатывает,
    # судим (зеркало host-фазы-1: на lexical судятся все verbatim-кандидаты).
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    j = Counter(1)
    assert relevance_gate.gate_quote("q", "text", 0.95, "adv", judge_fn=j) is False
    assert j.calls == 1


def test_gate_quote_raw_score_preferred_over_blend(monkeypatch):
    # hybrid_alpha>0: score=0.9 — СМЕСЬ ((1-a)·cos + a·lex), raw_score=0.3 — сырой
    # косинус. Гейт обязан судить по raw (0.3 ≤ band_hi), а не auto-keep по смеси.
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.9, "adv", judge_fn=j,
                                     raw_score=0.3) is False
    assert j.calls == 1


def test_gate_quote_raw_above_band_hi_auto_keep(monkeypatch):
    # Смесь in-band (0.60), но сырой косинус 0.90 > band_hi → калиброванный auto-keep.
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.60, "adv", judge_fn=j,
                                     raw_score=0.90) is True
    assert j.calls == 0


def test_gate_passage_blend_above_band_raw_inband_judged(monkeypatch):
    # Смесь 0.9 подняла пассаж над полосой, но сырой косинус 0.50 in-band → судим по raw.
    _semantic(monkeypatch)
    j = Counter(1)
    p = {"text": "x", "score": 0.9, "raw_score": 0.50, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert out.get("relevance_gated") is True
    assert j.calls == 1


def test_gate_passage_nonsemantic_judge_available_judged(monkeypatch):
    # lexical + живой судья: пассаж судится (раньше — молчаливый pass-through).
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    j = Counter(3)
    p = {"text": "x", "score": 0.5, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert out.get("relevance") == 3
    assert j.calls == 1


def test_gate_quote_nonsemantic_judge_unavailable_keeps(monkeypatch):
    # Судья недоступен (ollama мёртв) → прежний путь: keep, судья НЕ зван.
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch, val=False)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_passage_nonsemantic_judge_unavailable_passthrough(monkeypatch):
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch, val=False)
    j = Counter(0)
    p = {"text": "x", "score": 0.5, "source": "s"}
    out = relevance_gate.gate_passage("q", p, "adv", judge_fn=j)
    assert not out.get("relevance_gated")
    assert j.calls == 0


def test_gate_quote_nonsemantic_judge_raises_fail_closed(monkeypatch):
    # Судья доступен, но бросил → fail-closed withhold (как на semantic).
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    j = Counter(RuntimeError("boom"))
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is False
    assert j.calls == 1


# ── M4 wiring: _cite/_retrieve на не-semantic движке с доступным судьёй ────

def test_cite_wiring_nonsemantic_judge_available_withholds(monkeypatch):
    # hybrid/lexical ретрив (is_semantic False), судья доступен и режет → честный 🟡.
    import mcp_server
    _semantic(monkeypatch, val=False)
    _judge_avail(monkeypatch)
    fake = [{"text": "All warfare is based on deception.", "score": 0.44, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    calls = {"n": 0}
    def _spy(q, p, model=None, source=None):
        calls["n"] += 1
        return 0
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", "adjacent-domain camouflage q",
                         use_kernels=False)
    assert calls["n"] == 1                              # судья ЗВАН (раньше 0 — дыра M4)
    assert r["quotes"] == [] and r["marker"] == "🟡"


def test_cite_wiring_raw_score_from_retrieve_gates_blend(monkeypatch):
    # hybrid_alpha>0: retrieve отдал смесь 0.9 + raw 0.3 — _cite прокидывает raw в гейт,
    # гейт судит по raw (без raw_score смесь 0.9 > band_hi ушла бы в auto-keep — дыра M4).
    import mcp_server
    _semantic(monkeypatch)
    fake = [{"text": "All warfare is based on deception.", "score": 0.9,
             "raw_score": 0.3, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    calls = {"n": 0}
    def _spy(q, p, model=None, source=None):
        calls["n"] += 1
        return 3
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", "deception in war", use_kernels=False)
    assert calls["n"] == 1                              # судья ЗВАН несмотря на смесь 0.9
    assert r["quotes"] and r["best"]["marker"] == "🔵"


def test_eval_retrieve_forwards_raw_score(monkeypatch):
    # Прокидка M4: Passage.raw_score → dict retrieve (без неё _cite не видит сырой косинус).
    import eval as _eval_mod
    from engine import Passage
    class _FakeEng:
        def retrieve(self, q, d, top_k=3):
            return [Passage("t", 0.9, "s", None, raw_score=0.3),
                    Passage("u", 0.8, "s", None)]      # чистая семантика — без raw
    monkeypatch.setattr(_eval_mod._engine, "resolve_engine", lambda d, prefer=None: _FakeEng())
    out = _eval_mod.retrieve("q", "adv", top_k=2)
    assert out[0]["raw_score"] == 0.3
    assert "raw_score" not in out[1]                   # нет raw — ключа нет (форма прежняя)


# ───────────────── M9a: EVAL_ENGINE не протекает в прод-гейт ─────────────────

class _EngStub:
    def __init__(self, name):
        self.name = name


def test_is_semantic_ignores_eval_engine_env(monkeypatch):
    # Прод-путь (без prefer) смотрит ТОЛЬКО на реальный движок — env-форс из шелла
    # юзера не должен ГАСИТЬ семантику (lexical-env при живом semantic).
    import engine as _engine
    seen = []
    monkeypatch.setattr(_engine, "resolve_engine",
                        lambda d, prefer=None: seen.append(prefer) or _EngStub("semantic"))
    monkeypatch.setenv("EVAL_ENGINE", "lexical")
    assert relevance_gate.is_semantic("adv") is True
    assert seen == [None]                                # env НЕ дошла до резолвера


def test_is_semantic_env_cannot_enable_semantic(monkeypatch):
    # ...и не должен ВКЛЮЧАТЬ её (semantic-env при реальном lexical-поле).
    import engine as _engine
    monkeypatch.setattr(_engine, "resolve_engine",
                        lambda d, prefer=None: _EngStub("lexical"))
    monkeypatch.setenv("EVAL_ENGINE", "semantic")
    assert relevance_gate.is_semantic("adv") is False


def test_is_semantic_prefer_explicit_forwarded(monkeypatch):
    # Eval-вход: prefer ЯВНЫЙ — доходит до резолвера и решает.
    import engine as _engine
    seen = []
    monkeypatch.setattr(_engine, "resolve_engine",
                        lambda d, prefer=None: seen.append(prefer) or _EngStub(prefer or "?"))
    assert relevance_gate.is_semantic("adv", prefer="semantic") is True
    assert relevance_gate.is_semantic("adv", prefer="lexical") is False
    assert seen == ["semantic", "lexical"]


def test_gate_quote_threads_prefer_to_is_semantic(monkeypatch):
    seen = []
    monkeypatch.setattr(relevance_gate, "is_semantic",
                        lambda advisor_dir, prefer=None: seen.append(prefer) or False)
    _judge_avail(monkeypatch, True)
    j = Counter(3)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j,
                                     prefer="lexical") is True
    assert seen == ["lexical"]


def test_gate_passage_threads_prefer_to_is_semantic(monkeypatch):
    seen = []
    monkeypatch.setattr(relevance_gate, "is_semantic",
                        lambda advisor_dir, prefer=None: seen.append(prefer) or False)
    _judge_avail(monkeypatch, True)
    j = Counter(3)
    out = relevance_gate.gate_passage("q", {"text": "t", "score": 0.50, "source": "s"},
                                      "adv", judge_fn=j, prefer="hybrid")
    assert out.get("relevance_gated") is None            # judge=3 >= threshold → пропущен
    assert seen == ["hybrid"]


def test_gate_prefer_defaults_none(monkeypatch):
    # Прод-вызов без prefer — is_semantic получает None (никакого скрытого env-канала).
    seen = []
    monkeypatch.setattr(relevance_gate, "is_semantic",
                        lambda advisor_dir, prefer=None: seen.append(prefer) or True)
    j = Counter(3)
    assert relevance_gate.gate_quote("q", "text", 0.90, "adv", judge_fn=j) is True
    assert seen == [None]
