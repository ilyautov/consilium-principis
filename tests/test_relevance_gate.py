"""Borderline-gated судья релевантности: гейт ТОЛЬКО в неуверенной косинус-полосе.

Закрывает дыру рва: семантический ретрив выдаёт топически-близкие-но-НЕ-отвечающие
пассажи на камуфляж смежного домена (напр. Макиавелли про «дезинформацию на X» →
дословный 🔵-пассаж про обман, но он НЕ отвечает на вопрос). Судья это ловит.

Инварианты (тесты стерегут):
  • INERT на lexical (полоса калибрована под semantic) → CI без ollama = 0 изменений.
  • Судья зовётся ТОЛЬКО для in-band на semantic (латентный контракт → call-count).
  • FAIL-CLOSED: судья упал/неуверен in-band → gated (пассаж флагнут / цитата снята).
Всё офлайн: judge_fn мокается, is_semantic монки-патчится.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pytest
import relevance_gate


class Counter:
    """judge_fn-заглушка со счётчиком вызовов (латентный контракт)."""
    def __init__(self, ret):
        self._ret = ret
        self.calls = 0

    def __call__(self, query, passage):
        self.calls += 1
        if isinstance(self._ret, Exception):
            raise self._ret
        return self._ret


def _semantic(monkeypatch, val=True):
    monkeypatch.setattr(relevance_gate, "is_semantic", lambda advisor_dir: val)


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


def test_gate_quote_not_semantic_keeps_no_judge(monkeypatch):
    _semantic(monkeypatch, val=False)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_none_score_keeps_no_judge(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(0)
    assert relevance_gate.gate_quote("q", "text", None, "adv", judge_fn=j) is True
    assert j.calls == 0


def test_gate_quote_judge_raises_fail_closed_withhold(monkeypatch):
    _semantic(monkeypatch)
    j = Counter(RuntimeError("boom"))
    assert relevance_gate.gate_quote("q", "text", 0.50, "adv", judge_fn=j) is False
    assert j.calls == 1


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
    monkeypatch.setattr(relevance_judge, "judge", lambda q, p, model=None: judge_ret)
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
    """CI (lexical) — гейт инертен: судья не зван, поведение как раньше."""
    import mcp_server
    _semantic(monkeypatch, val=False)
    fake = [{"text": "All warfare is based on deception.", "score": 0.50, "source": "src"}]
    import eval as _eval_mod
    monkeypatch.setattr(_eval_mod, "retrieve", lambda q, d, top_k=8: list(fake))
    monkeypatch.setattr(mcp_server, "_fidelity_check",
                        lambda t, d: {"status": "🔵", "verbatim": True, "source": "src"})
    import relevance_judge
    called = {"n": 0}
    def _spy(q, p, model=None):
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
    def _spy(q, p, model=None):
        calls["n"] += 1
        return 0                                        # судья режет
    monkeypatch.setattr(relevance_judge, "judge", _spy)
    r = mcp_server._cite("advisors/machiavelli", ["primary", "secondary"], use_kernels=False)
    assert calls["n"] >= 1                              # судья ЗВАН на kernel/secondary-цитате
    assert r["quotes"] == [] and r["marker"] == "🟡"    # снята → честный 🟡 (не утекла как 🔵)
