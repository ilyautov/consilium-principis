"""Оркестровка сборки советника в один шаг: манифест-гейт → corpus → kernels → отчёт.

Фрагментация: pipeline.build доходит только до corpus.jsonl; kernels (gemma/ollama) и эмбеддинги
— отдельные ручные шаги. Здесь — один вызов. КЛЮЧЕВОЕ: манифест-гейт (валидатор A) стоит ПЕРЕД
сборкой — сломанный манифест (маркер не в тексте → съезд тиров) НЕ должен породить корпус.
Kernels требуют ollama → graceful (без сети шаг помечается, сборка не падает).
"""
import os, sys, json, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from build_orchestrator import build_advisor_full


def _advisor(tmp, source_text, manifest):
    sd = os.path.join(tmp, "sources")
    os.makedirs(sd)
    open(os.path.join(sd, "a.txt"), "w", encoding="utf-8").write(source_text)
    json.dump(manifest, open(os.path.join(sd, "manifest.json"), "w", encoding="utf-8"))
    return tmp


def test_refuses_build_on_invalid_manifest():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor(t, "тело без маркера",
                       {"a.txt": {"tier": "P1", "regions": [{"tier": "P1", "from": "НЕТ СТРОКИ"}]}})
        res = build_advisor_full(adv, run_kernels=False)
        assert res["ok"] is False
        assert res["stopped_at"] == "manifest-validation"
        assert any(p.get("marker") == "НЕТ СТРОКИ" for p in res["problems"])
        # корпус НЕ создан — гейт сработал до сборки
        assert not os.path.isfile(os.path.join(adv, "build", "corpus.jsonl"))


def test_builds_corpus_with_valid_manifest():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor(t, "Первое предложение. Второе предложение про стратегию.",
                       {"a.txt": {"tier": "P1", "attribution": "Автор"}})
        res = build_advisor_full(adv, run_kernels=False)
        assert res["ok"] is True
        corpus_step = [s for s in res["steps"] if s["step"] == "corpus"][0]
        assert corpus_step["ok"] is True and corpus_step["chunks"] > 0
        assert os.path.isfile(os.path.join(adv, "build", "corpus.jsonl"))


def test_kernels_graceful_without_ollama():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor(t, "Текст советника про власть и стратегию.",
                       {"a.txt": {"tier": "P1"}})
        res = build_advisor_full(adv, run_kernels=True)
        # сборка не падает; шаг kernels помечен (ok True если ollama есть, иначе note)
        k = [s for s in res["steps"] if s["step"] == "kernels"]
        assert len(k) == 1
        assert res["ok"] is True            # корпус собран независимо от kernels


def test_index_step_graceful():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor(t, "Первое. Второе про мудрость и спокойствие.", {"a.txt": {"tier": "P1"}})
        res = build_advisor_full(adv, run_kernels=False, run_index=True)
        idx = [s for s in res["steps"] if s["step"] == "index"]
        assert len(idx) == 1                # семантик-индекс строится (или graceful note без ollama)
        assert res["ok"] is True            # корпус цел независимо от индекса (контур на полу)


def test_index_skipped_when_disabled():
    with tempfile.TemporaryDirectory() as t:
        adv = _advisor(t, "Текст.", {"a.txt": {"tier": "P1"}})
        res = build_advisor_full(adv, run_kernels=False, run_index=False)
        assert [s for s in res["steps"] if s["step"] == "index"] == []
