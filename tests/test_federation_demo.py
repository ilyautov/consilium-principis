"""Офлайн end-to-end демо федерации: хост симулирует 3 дивергентных воркера на роль, РЕАЛЬНЫЙ
гейт верности (не мок) сверяет цитаты против tmp-корпуса, рендер даёт читаемый markdown.
Догфуд-энейблмент + регрессионный тест, не новая фича."""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from federation.queue import SqliteBackend
from mcp_server import _fidelity_check


def _make_advisor(tmp_path, chunks, name="adv"):
    adv = tmp_path / name
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(adv)


def _backend(tmp_path):
    return SqliteBackend(str(tmp_path / "f.sqlite3"))


def _advisor_dirs(tmp_path):
    aurelius_dir = _make_advisor(tmp_path, [
        {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"},
    ], name="aurelius")
    machiavelli_dir = _make_advisor(tmp_path, [
        {"text": "It is much safer to be feared than loved.", "tier": "P1", "source": "The Prince, ch.17"},
    ], name="machiavelli")
    return {"aurelius": aurelius_dir, "machiavelli": machiavelli_dir}


def test_run_demo_produces_coherent_envelope(tmp_path):
    from federation.demo import run_demo

    backend = _backend(tmp_path)
    advisor_dirs = _advisor_dirs(tmp_path)

    envelope, md = run_demo(backend, _fidelity_check, advisor_dirs, render=True)

    # --- envelope structure ---
    assert len(envelope["roles"]) == 2
    role_names = {r["role"] for r in envelope["roles"]}
    assert role_names == {"aurelius", "machiavelli"}

    all_statuses = []
    all_worker_models_per_role = []
    for role in envelope["roles"]:
        # anti-best-of-N: 3 raw replicas preserved
        assert len(role["replicas"]) == 3
        # divergence computed
        assert "divergence" in role
        assert "score" in role["divergence"] and "level" in role["divergence"]
        # 3 distinct worker models
        models = set(role["worker_models"])
        assert len(models) == 3, "ожидались 3 различных worker_model, получили %r" % models
        all_worker_models_per_role.append(models)
        for cand in role["replicas"]:
            for q in cand["quotes"]:
                all_statuses.append(q["status"])

    # both real-gate outcomes present somewhere in the envelope
    assert "🔵" in all_statuses, "реальный гейт должен был заземлить хотя бы одну verbatim-цитату"
    assert "🟡" in all_statuses, "сфабрикованная цитата должна была остаться 🟡 (гейт дискриминирует)"

    # --- render ---
    assert md.strip(), "render_council_md вернул пустую строку"
    assert "aurelius" in md
    assert "machiavelli" in md
    assert "🔵" in md
    levels = {r["divergence"]["level"] for r in envelope["roles"]}
    assert any(level in md for level in levels), "уровень дивергенции из envelope должен встретиться в markdown"


def test_render_council_md_standalone(tmp_path):
    from federation.demo import run_demo, render_council_md

    backend = _backend(tmp_path)
    advisor_dirs = _advisor_dirs(tmp_path)

    envelope = run_demo(backend, _fidelity_check, advisor_dirs, render=False)
    md = render_council_md(envelope)
    assert md.strip()
    assert "Что показывает демо" in md or "что показывает демо" in md.lower()
