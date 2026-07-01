"""tests/test_synth_eval.py — офлайн-тесты генератора синтетики.

Нет сети, нет ollama, нет реального корпуса.
LLM-вызовы мокируются через monkeypatch llm_local._raw_generate.
Корпус мокируется через monkeypatch synth_eval._load_chunks.
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import llm_local
import synth_eval


# ── Fixtures ───────────────────────────────────────────────────────────────────

# Канонический ответ LLM на запрос OOC: 3 валидные строки
CANNED_OOC = (
    "Q: Как Макиавелли оценил бы IPO стартапа в 2024 году? | WHY: требует современной финансовой концепции, отсутствующей в корпусе\n"
    "Q: Что советовал бы Государь по поводу регуляции ИИ? | WHY: технологическая тема, за пределами домена\n"
    "Q: Как применить «Государя» к стратегии NFT-проектов? | WHY: блокчейн-специфика, нет в корпусе\n"
)

# Строки, которые НЕ соответствуют формату (должны отбрасываться)
MALFORMED_OOC = (
    "Q: только вопрос без вертикальной черты\n"
    "просто текст без ключевых слов\n"
    "WHY: только reason без Q\n"
    "Q: Хороший вопрос? | WHY: валидная причина (единственная валидная строка)\n"
)

CANNED_ANSWERABLE = "Как государь должен относиться к помощникам и советникам?"
CANNED_FAKE_CLAUSE = "the wise prince should seek digital alliances above all else"

# Три синтетических чанка (≥ 350 симв каждый)
_LONG_SENT_1 = "It is better to be feared than loved, as men are ungrateful by nature and fickle in danger. "
_LONG_SENT_2 = "Fortune governs half our actions, and the other half are left to ourselves to determine. "
_LONG_SENT_3 = "A prince ought never to make an alliance with one more powerful than himself in arms. "

FAKE_CHUNKS = [
    {"text": _LONG_SENT_1 * 5, "source": "The Prince XVII"},
    {"text": _LONG_SENT_2 * 5, "source": "The Prince XXV"},
    {"text": _LONG_SENT_3 * 5, "source": "The Prince XXI"},
]


def _patch_chunks(monkeypatch):
    monkeypatch.setattr(synth_eval, "_load_chunks", lambda _: FAKE_CHUNKS)


# ── _parse_qwhy (unit) ─────────────────────────────────────────────────────────

def test_parse_qwhy_parses_valid_lines():
    results = synth_eval._parse_qwhy(CANNED_OOC)
    assert len(results) == 3
    assert all("q" in r and "why" in r for r in results)


def test_parse_qwhy_drops_malformed():
    results = synth_eval._parse_qwhy(MALFORMED_OOC)
    assert len(results) == 1
    assert "единственная валидная строка" in results[0]["why"]


def test_parse_qwhy_empty_input():
    assert synth_eval._parse_qwhy("") == []


def test_parse_qwhy_case_insensitive():
    # Нижний регистр «q:» и «why:» тоже должен работать
    line = "q: Вопрос на степень безопасности? | why: современная метрика, нет в корпусе"
    results = synth_eval._parse_qwhy(line)
    assert len(results) == 1


# ── gen_adversarial_ooc ────────────────────────────────────────────────────────

def test_adversarial_ooc_parses_canned_response(monkeypatch):
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_OOC)
    results = synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 5)
    assert len(results) == 3  # 3 валидные строки в CANNED_OOC
    assert all("q" in r and "why" in r for r in results)
    assert "2024" in results[0]["q"]


def test_adversarial_ooc_drops_malformed_lines(monkeypatch):
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: MALFORMED_OOC)
    results = synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 5)
    assert len(results) == 1  # только одна валидная строка


def test_adversarial_ooc_caps_at_n(monkeypatch):
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_OOC)
    results = synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 2)
    assert len(results) == 2  # обрезано до n=2


def test_adversarial_ooc_empty_response(monkeypatch):
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: "")
    results = synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 3)
    assert results == []  # fail-closed, не падает


def test_adversarial_ooc_passes_model_to_generate(monkeypatch):
    captured = {}
    monkeypatch.setattr(llm_local, "_raw_generate",
                        lambda p, m, t, to: (captured.update(model=m), CANNED_OOC)[1])
    synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 2,
                                   model="test-model")
    assert captured.get("model") == "test-model"


# ── seed_failures инжекция ─────────────────────────────────────────────────────

def test_seed_failures_injected_in_prompt(monkeypatch):
    captured = {}

    def fake_raw(prompt, model, temp, timeout):
        captured["prompt"] = prompt
        return CANNED_OOC

    monkeypatch.setattr(llm_local, "_raw_generate", fake_raw)
    seed = [{"q": "Как Государь относился к биткоину?", "why": "нет в корпусе"}]
    synth_eval.gen_adversarial_ooc(
        "advisors/machiavelli", "Niccolò Machiavelli", 3, seed_failures=seed
    )
    assert "биткоину" in captured["prompt"], "seed question text должен присутствовать в prompt"
    assert "TOO EASY" in captured["prompt"], "инструкция о повышении сложности должна быть в prompt"


def test_seed_failures_not_injected_when_none(monkeypatch):
    captured = {}

    def fake_raw(prompt, model, temp, timeout):
        captured["prompt"] = prompt
        return CANNED_OOC

    monkeypatch.setattr(llm_local, "_raw_generate", fake_raw)
    synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 3)
    assert "TOO EASY" not in captured["prompt"]


def test_seed_failures_truncated_to_five(monkeypatch):
    """Более 5 seed_failures — в prompt попадает не более 5 (защита от раздутого промпта)."""
    captured = {}

    def fake_raw(prompt, model, temp, timeout):
        captured["prompt"] = prompt
        return CANNED_OOC

    monkeypatch.setattr(llm_local, "_raw_generate", fake_raw)
    seeds = [{"q": f"Вопрос {i}", "why": "причина"} for i in range(10)]
    synth_eval.gen_adversarial_ooc("advisors/machiavelli", "Niccolò Machiavelli", 3,
                                   seed_failures=seeds)
    # Вопросы 5-9 не должны попасть в prompt
    for i in range(5, 10):
        assert f"Вопрос {i}" not in captured["prompt"]


# ── gen_answerable ─────────────────────────────────────────────────────────────

def test_gen_answerable_returns_expected_keys(monkeypatch):
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_ANSWERABLE)
    results = synth_eval.gen_answerable("advisors/machiavelli", 3)
    assert len(results) == 3
    for r in results:
        assert "q" in r and "anchor" in r and "ref" in r
        assert len(r["q"]) > 5


def test_gen_answerable_anchor_not_empty(monkeypatch):
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_ANSWERABLE)
    results = synth_eval.gen_answerable("advisors/machiavelli", 2)
    for r in results:
        assert r["anchor"], "anchor не должен быть пустым"


def test_gen_answerable_short_llm_response_dropped(monkeypatch):
    """Если LLM вернул слишком короткий текст (≤10 симв), item пропускается."""
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: "Ок")
    results = synth_eval.gen_answerable("advisors/machiavelli", 3)
    assert results == []


# ── gen_atomic_compounds ────────────────────────────────────────────────────────

def test_atomic_compounds_has_both_grounded_flags(monkeypatch):
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_FAKE_CLAUSE)
    results = synth_eval.gen_atomic_compounds("advisors/machiavelli", 3)
    assert len(results) >= 1
    for item in results:
        assert "text" in item
        assert "atoms" in item
        flags = [a["grounded"] for a in item["atoms"]]
        assert True in flags, "должен быть grounded=True (реальная клауза из корпуса)"
        assert False in flags, "должен быть grounded=False (выдуманная клауза)"


def test_atomic_compounds_text_contains_both_clauses(monkeypatch):
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_FAKE_CLAUSE)
    results = synth_eval.gen_atomic_compounds("advisors/machiavelli", 1)
    assert len(results) == 1
    item = results[0]
    real_atom = next(a for a in item["atoms"] if a["grounded"])
    fake_atom = next(a for a in item["atoms"] if not a["grounded"])
    # Реальная клауза (начало) должна присутствовать в составном тексте
    assert real_atom["text"][:30] in item["text"], "реальная клауза должна быть в compound text"
    # Выдуманная клауза должна присутствовать в составном тексте
    assert fake_atom["text"] in item["text"], "выдуманная клауза должна быть в compound text"


def test_atomic_compounds_atoms_have_text_field(monkeypatch):
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_FAKE_CLAUSE)
    results = synth_eval.gen_atomic_compounds("advisors/machiavelli", 2)
    for item in results:
        for atom in item["atoms"]:
            assert "text" in atom
            assert "grounded" in atom
            assert isinstance(atom["grounded"], bool)


def test_atomic_compounds_deterministic(monkeypatch):
    """seed=42 → один и тот же порядок выборки (воспроизводимость)."""
    _patch_chunks(monkeypatch)
    monkeypatch.setattr(llm_local, "_raw_generate", lambda p, m, t, to: CANNED_FAKE_CLAUSE)
    r1 = synth_eval.gen_atomic_compounds("advisors/machiavelli", 2)
    r2 = synth_eval.gen_atomic_compounds("advisors/machiavelli", 2)
    assert [x["text"] for x in r1] == [x["text"] for x in r2]


# ── write_jsonl round-trip ─────────────────────────────────────────────────────

def test_write_jsonl_roundtrip(tmp_path):
    rows = [{"q": "Вопрос?", "why": "Причина"}, {"q": "Ещё?", "why": "Ещё причина"}]
    path = str(tmp_path / "test.jsonl")
    synth_eval.write_jsonl(path, rows)
    loaded = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    assert loaded == rows


def test_write_jsonl_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "sub" / "nested" / "out.jsonl")
    synth_eval.write_jsonl(path, [{"k": "v"}])
    assert os.path.isfile(path)


def test_write_jsonl_utf8_preserved(tmp_path):
    rows = [{"q": "Как государю устроить власть?", "why": "корпус отвечает"}]
    path = str(tmp_path / "utf8.jsonl")
    synth_eval.write_jsonl(path, rows)
    content = open(path, encoding="utf-8").read()
    assert "государю" in content
    assert "корпус" in content


def test_write_jsonl_empty_list(tmp_path):
    path = str(tmp_path / "empty.jsonl")
    synth_eval.write_jsonl(path, [])
    assert os.path.isfile(path)
    assert open(path).read() == ""
