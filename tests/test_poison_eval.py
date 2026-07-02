"""§3.1 moat-v2: харнесс отравленных твин-пар (poison_eval).

Оффлайн: судья мокается — тестируем САМ харнесс (валидность батареи, инвариант
твин-пары «удалил инъекцию → байт-в-байт clean», спаривание вызовов судьи, метрику
инфляции, fail-closed на ошибке судьи). Живой замер инфляции — poison_eval.main().
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import pytest
import poison_eval


@pytest.fixture(scope="module")
def battery():
    return poison_eval.load_battery()


# ───────────────────────── батарея (фикстура в репо) ─────────────────────────

def test_battery_has_at_least_10_pairs(battery):
    assert len(battery) >= 10


def test_battery_rows_carry_required_keys(battery):
    for row in battery:
        for k in poison_eval.REQUIRED_KEYS:
            assert row.get(k), f"{row.get('id')}: пустой {k}"
        assert row["position"] in poison_eval.VALID_POSITIONS


def test_battery_mixes_kinds_and_languages(battery):
    kinds = {r["kind"] for r in battery}
    langs = {r["lang"] for r in battery}
    assert len(kinds) >= 5, f"мало видов инъекций: {kinds}"
    assert {"ru", "en"} <= langs


def test_battery_ids_unique(battery):
    ids = [r["id"] for r in battery]
    assert len(ids) == len(set(ids))


def test_battery_covers_all_positions(battery):
    assert {r["position"] for r in battery} == set(poison_eval.VALID_POSITIONS)


def test_battery_includes_delimiter_escape_kind(battery):
    """Худшая инъекция — попытка закрыть блок данных судьи своим ПАССАЖ>>>."""
    esc = [r for r in battery if r["kind"] == "delimiter_escape"]
    assert esc and any("ПАССАЖ>>>" in r["injection"] for r in esc)


def test_load_battery_raises_on_missing_key(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"id": "x", "kind": "k"}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        poison_eval.load_battery(str(p))


# ───────────────────────── твин-инвариант ────────────────────────────────────

def test_twin_invariant_removing_injection_restores_clean(battery):
    """Единственная разница пары = инъекция: удаление вставленного блока даёт clean
    байт-в-байт (иначе дельта не атрибутируется инъекции)."""
    for row in battery:
        poisoned = poison_eval.poisoned_text(row)
        clean, inj, pos = row["clean"], row["injection"], row["position"]
        if pos == "start":
            assert poisoned == inj + "\n" + clean
        elif pos == "end":
            assert poisoned == clean + "\n" + inj
        else:
            i = poison_eval._mid_insert_index(clean)
            assert poisoned == clean[:i] + "\n" + inj + "\n" + clean[i:]
            assert 0 < i < len(clean), "middle-вставка обязана быть внутри текста"


def test_mid_insert_index_falls_back_without_sentence_boundary():
    assert poison_eval._mid_insert_index("no sentence boundary here") == \
        len("no sentence boundary here")


# ───────────────────────── спаривание вызовов судьи ──────────────────────────

def test_harness_judges_both_twins_with_same_query(battery):
    calls = []

    def spy_judge(q, passage):
        calls.append((q, passage))
        return 1

    poison_eval.inflation_eval(battery, spy_judge)
    assert len(calls) == 2 * len(battery)
    for row, (c_clean, c_poison) in zip(battery, zip(calls[0::2], calls[1::2])):
        assert c_clean[0] == c_poison[0] == row["q"]          # тот же вопрос
        assert c_clean[1] == row["clean"]                     # чистый близнец без инъекции
        assert row["injection"] in c_poison[1]                # отравленный — с ней


# ───────────────────────── метрика инфляции ──────────────────────────────────

def test_inflatable_judge_detected(battery):
    """Судья, ведущийся на инъекцию (видит её текст → 3), даёт inflation_rate 1.0."""
    def gullible(q, passage):
        return 3 if any(r["injection"] in passage for r in battery) else 1
    res = poison_eval.inflation_eval(battery, gullible)
    assert res["inflated_n"] == res["n"] == len(battery)
    assert res["inflation_rate"] == 1.0
    assert res["mean_delta"] == 2.0 and res["max_delta"] == 2


def test_honest_judge_zero_inflation(battery):
    """Судья, независимый от инъекции (рейтинг — функция вопроса), даёт инфляцию 0."""
    def honest(q, passage):
        return len(q) % 4
    res = poison_eval.inflation_eval(battery, honest)
    assert res["inflated_n"] == 0
    assert res["inflation_rate"] == 0.0
    assert all(r["delta"] == 0 for r in res["per_row"])


def test_deflation_is_not_counted_as_inflation(battery):
    """Отравленный близнец оценён НИЖЕ чистого (судья счёл инъекцию мусором) —
    это не инфляция: inflated_n == 0, дельты отрицательные."""
    def suspicious(q, passage):
        return 0 if any(r["injection"] in passage for r in battery) else 2
    res = poison_eval.inflation_eval(battery, suspicious)
    assert res["inflated_n"] == 0
    assert res["max_delta"] == -2


def test_judge_error_fail_closed_no_inflation(battery):
    """Судья бросил на отравленном → рейтинг 0 + error-флаг; ошибка не может
    засчитаться как инфляция."""
    def flaky(q, passage):
        if any(r["injection"] in passage for r in battery):
            raise RuntimeError("boom")
        return 2
    res = poison_eval.inflation_eval(battery, flaky)
    assert res["inflated_n"] == 0
    assert all(r["error"] for r in res["per_row"])
    assert all(r["poisoned_rating"] == 0 for r in res["per_row"])


def test_by_kind_breakdown_sums_to_total(battery):
    def gullible(q, passage):
        return 3 if any(r["injection"] in passage for r in battery) else 0
    res = poison_eval.inflation_eval(battery, gullible)
    assert sum(k["n"] for k in res["by_kind"].values()) == res["n"]
    assert sum(k["inflated_n"] for k in res["by_kind"].values()) == res["inflated_n"]


def test_empty_battery_zero_metrics():
    res = poison_eval.inflation_eval([], lambda q, p: 3)
    assert res == {"n": 0, "inflated_n": 0, "inflation_rate": 0.0, "gate_flips": 0,
                   "mean_delta": 0.0, "max_delta": 0, "by_kind": {}, "per_row": []}


def test_gate_flip_counts_threshold_crossing(battery):
    """gate_flip = clean < 2 <= poisoned (инъекция перевернула решение гейта прода);
    инфляция 2→3 инфлейт, но НЕ gate_flip (оба и так проходят порог)."""
    def cross(q, passage):
        return 2 if any(r["injection"] in passage for r in battery) else 1
    res = poison_eval.inflation_eval(battery, cross)
    assert res["gate_flips"] == res["n"]           # каждая пара перевернула гейт

    def above(q, passage):
        return 3 if any(r["injection"] in passage for r in battery) else 2
    res2 = poison_eval.inflation_eval(battery, above)
    assert res2["inflated_n"] == res2["n"] and res2["gate_flips"] == 0


def test_median_voting_kills_single_sample_noise(battery):
    """n_samples=3: одиночный шумовой выброс судьи (1 из 3 сэмплов +1) не меняет
    медианный рейтинг → инфляция 0 (то, что одиночный сэмпл засчитал бы)."""
    calls = {"n": 0}

    def noisy(q, passage):
        calls["n"] += 1
        return 1 if calls["n"] % 3 == 0 else 0     # каждый третий сэмпл шумит вверх
    res = poison_eval.inflation_eval(battery, noisy, n_samples=3)
    assert res["inflated_n"] == 0
    assert all(r["clean_rating"] == 0 and r["poisoned_rating"] == 0
               for r in res["per_row"])
    assert calls["n"] == 2 * 3 * len(battery)      # оба близнеца × 3 сэмпла


def test_median_error_sample_fail_closed(battery):
    """Один из 3 сэмплов бросил → он считается 0 (не может завысить медиану),
    error-флаг взводится."""
    calls = {"n": 0}

    def flaky(q, passage):
        calls["n"] += 1
        if calls["n"] % 3 == 1:
            raise RuntimeError("boom")
        return 2
    res = poison_eval.inflation_eval(battery, flaky, n_samples=3)
    assert all(r["error"] for r in res["per_row"])
    assert all(r["clean_rating"] == 2 and r["poisoned_rating"] == 2
               for r in res["per_row"])            # медиана [0,2,2] = 2
