"""Регресс-гард демо B (Monte Carlo). Корпус-независим → работает и в CI.

Стережёт: числа в кадре идут из живого run_calculation (детерминированно по сиду),
честная плашка «это не истина» на месте, ноль техношума и длинного тире (AI-маркер).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.join(_ROOT, "scripts", "demo"))

import montecarlo_demo as demo


def test_calculation_is_deterministic():
    """Один и тот же сид → тот же P(лучший) и тот же спарклайн (воспроизводимость в кадре)."""
    _r1, p1, s1, t1 = demo.run()
    _r2, p2, s2, t2 = demo.run()
    assert (p1, s1, t1) == (p2, s2, t2)
    assert 0 <= p1 <= 100 and s1 and t1


def test_numbers_come_from_live_calc():
    """P(лучший) и рычаг в транскрипте берутся из результата расчёта, не вписаны."""
    _res, p_ship, _spark, top = demo.run()
    lines = demo.transcript()
    assert any(("%d%%" % p_ship) in t for _, t in lines)      # именно живой процент
    assert top in ("traction_prob", "upside_hours", "hours_to_ship")


def test_honesty_caveat_present():
    """В кадре обязана быть плашка «это не истина, это твоя модель» (обоих языков)."""
    assert any("не истина" in t for _, t in demo.transcript(lang="ru"))
    assert any("Not the truth" in t for _, t in demo.transcript(lang="en"))


def test_no_noise_and_no_long_dash():
    """Ни путей/JSON, ни сырого id величины, ни длинного тире «—» (HARD BAN хьюномайзера)."""
    for lang in ("ru", "en"):
        for _style, text in demo.transcript(lang=lang):
            low = text.lower()
            assert ".json" not in low and "advisors/" not in low
            assert "traction_prob" not in low           # сырой id заменён человеческой подписью
            assert "—" not in text
