"""A/B-калибровка подачи под человека (N=1), с guardrail не-захвата.

Один контент совета подаётся двумя фреймингами:
  • светлый (light) — под когницию: опции, трение, сократично (не-захват, юзер думает сам);
  • тёмный (dark)  — под комплаенс: директивно, один путь, минимум трения (граница манипуляции).
Калибровка по журналу решений: какой фрейминг ведёт ЭТОГО юзера к исходам, которые он
ОДОБРЯЕТ задним числом. Guardrail: если тёмный выигрывает по действию, но проигрывает по
одобрению (юзер потом жалеет) — это ЗАХВАТ, рекомендуем светлый несмотря на «успех».
Ядро (scorer) чистое → детерминированный тест.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from calibration import classify_framing, parse_decision_log, calibrate


def test_classify_framing_ru_en():
    assert classify_framing("Подача: светлый") == "light"
    assert classify_framing("framing: dark") == "dark"
    assert classify_framing("тёмный фрейм") == "dark"
    assert classify_framing("ничего") is None


LOG = """
### 2026-06-20 Решение A
- Подача: светлый
- **ИСХОД: ✅** — сработало
- Одобрено задним числом: да

### 2026-06-22 Решение B
- Подача: светлый
- **ИСХОД: ✅**
- Одобрено задним числом: да

### 2026-06-24 Решение C
- Подача: тёмный
- **ИСХОД: ✅** — продавили, сделал
- Одобрено задним числом: нет

### 2026-06-26 Решение D
- Подача: тёмный
- **ИСХОД: ⏳ pending**
"""


def test_parse_extracts_entries_with_framing_outcome_endorsement():
    entries = parse_decision_log(LOG)
    assert len(entries) == 4
    a = entries[0]
    assert a["framing"] == "light" and a["outcome"] == "good" and a["endorsed"] is True
    c = entries[2]
    assert c["framing"] == "dark" and c["outcome"] == "good" and c["endorsed"] is False
    d = entries[3]
    assert d["outcome"] == "pending"          # ⏳ не resolved


def test_calibrate_flags_capture_when_dark_acts_but_user_regrets():
    cal = calibrate(parse_decision_log(LOG))
    # тёмный: 1 «успех» по действию, но 0 одобрений → захват
    assert cal["capture_flag"] is True
    assert cal["recommend"] == "light"        # не оптимизируем под захват
    assert cal["by_framing"]["light"]["endorse_rate"] == 1.0
    assert cal["by_framing"]["dark"]["endorse_rate"] == 0.0


def test_calibrate_recommends_dark_only_if_endorsed():
    log = """
### r1
- Подача: тёмный
- **ИСХОД: ✅**
- Одобрено задним числом: да
### r2
- Подача: светлый
- **ИСХОД: ❌**
- Одобрено задним числом: нет
"""
    cal = calibrate(parse_decision_log(log))
    assert cal["capture_flag"] is False       # тёмный одобрен → не захват
    assert cal["recommend"] == "dark"         # честно ведёт к одобренному исходу


def test_calibrate_defaults_to_light_without_data():
    cal = calibrate([])
    assert cal["recommend"] == "light"        # дефолт безопасен (не-захват)
    assert cal["capture_flag"] is False


def test_pending_entries_excluded_from_rates():
    log = """
### r1
- Подача: светлый
- **ИСХОД: ⏳ pending**
"""
    cal = calibrate(parse_decision_log(log))
    assert cal["by_framing"]["light"]["resolved"] == 0
    assert cal["recommend"] == "light"
