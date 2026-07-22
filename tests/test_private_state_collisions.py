"""Independent processes must not overwrite private artifacts with equal slugs."""
import json
import multiprocessing
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))


def _valid_map():
    return {
        "question": "Ship or wait?",
        "options": [
            {"id": "ship_public", "name": "Ship", "reversibility": "one-way"},
            {"id": "status_quo", "name": "Wait", "reversibility": "two-way",
             "status_quo": True},
        ],
        "uncertainties": [
            {"id": "traction_prob", "kind": "event", "prob": 0.3, "confirmed_by_user": True},
            {"id": "upside", "kind": "continuous", "min": 50, "mode": 150, "max": 400,
             "confirmed_by_user": True},
        ],
        "stakes": {"metric": "value", "direction": "max"},
        "horizon": "3 months",
        "model": {
            "ship_public": {"expr": "traction_prob * upside", "words": "traction times upside"},
            "status_quo": {"expr": "0", "words": "wait"},
        },
    }


def _save_in_process(kind, root, queue):
    sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
    import mcp_server  # noqa: PLC0415

    mcp_server._root = lambda: root
    if kind == "map":
        result = mcp_server.dispatch("save_decision_map", {"map": _valid_map(), "slug": "same", "n": 20})
    elif kind == "card":
        result = mcp_server.dispatch("save_decision_card", {
            "map": _valid_map(), "chosen_option": "ship_public", "slug": "same",
            "review_horizon_days": 30, "n": 20,
        })
    else:
        result = mcp_server.dispatch("calibrated_consult_open", {
            "question": "Same consult", "prior_call": "wait", "prior_confidence": 0.6,
        })
    queue.put(result)


def _concurrent_saves(kind, tmp_path):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [context.Process(target=_save_in_process, args=(kind, str(tmp_path), queue))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=30) for _ in workers]
    for worker in workers:
        worker.join(timeout=30)
        assert worker.exitcode == 0
    assert all(result.get("ok") is True for result in results)
    assert results[0]["path"] != results[1]["path"]
    return results


def test_competing_processes_preserve_both_decision_maps(tmp_path):
    results = _concurrent_saves("map", tmp_path)
    documents = [json.loads((tmp_path / result["path"]).read_text(encoding="utf-8")) for result in results]
    assert all(document["kind"] == "decision_map" for document in documents)
    assert all(document["calculation"]["result"] for document in documents)


def test_competing_processes_preserve_both_decision_cards_with_valid_ids(tmp_path):
    results = _concurrent_saves("card", tmp_path)
    documents = [json.loads((tmp_path / result["path"]).read_text(encoding="utf-8")) for result in results]
    sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
    import decision_card  # noqa: PLC0415
    assert {document["id"] for document in documents} == {result["card_id"] for result in results}
    assert all(re.fullmatch(r"dc_[A-Za-z0-9]+", document["id"]) for document in documents)
    assert all(decision_card.validate_card(document, map=_valid_map()) == [] for document in documents)


def test_competing_processes_preserve_both_consults_with_valid_ids(tmp_path):
    results = _concurrent_saves("consult", tmp_path)
    documents = [json.loads((tmp_path / result["path"]).read_text(encoding="utf-8")) for result in results]
    sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
    import calibrated_consult  # noqa: PLC0415
    assert {document["id"] for document in documents} == {result["consult_id"] for result in results}
    assert all(re.fullmatch(r"cc_[A-Za-z0-9]+", document["id"]) for document in documents)
    assert all(calibrated_consult.validate_consult(document) == [] for document in documents)
