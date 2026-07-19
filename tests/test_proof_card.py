"""proof_card — карточка ОДНОЙ 🔵-verbatim-цитаты (виирал-ассет). Fail-closed: не 🔵 → нет карточки."""
import os, sys, json
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))


@pytest.fixture(autouse=True)
def _clamp_root_at_tmp(monkeypatch, tmp_path):
    """H5 read-гард клампит advisor_dir корнем репо; синтетический корпус лежит под tmp_path,
    значит _root надо навести на tmp_path, иначе abs-путь честно отвергается как вне корня."""
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))


def _make_advisor(tmp_path, chunks):
    adv = tmp_path / "adv"
    (adv / "build").mkdir(parents=True)
    with open(adv / "build" / "corpus.jsonl", "w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(adv)


def test_verbatim_blue_quote_makes_card(tmp_path):
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"}])
    r = _proof_card("Confine thyself to the present.", adv)
    assert r["verified"] is True
    assert "Meditations 7.29" in r["content"]
    # честный бейдж: «дословно — сверено с первоисточником» (не оверклейм «посимвольно»)
    assert "первоисточник" in r["content"]
    assert "посимвольно" not in r["content"]
    assert r["content"].startswith("<!doctype html>")
    assert "<script" not in r["content"].lower()


def test_non_verbatim_quote_no_card(tmp_path):
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "Confine thyself to the present.", "tier": "P1", "source": "Meditations 7.29"}])
    r = _proof_card("This is a fabricated quote never in corpus.", adv)
    assert r["verified"] is False
    assert r.get("content") is None


def test_green_tier_quote_rejected(tmp_path):
    # 🟢 (комментарий S-тир) не пускаем на 🔵-пруф-карту (карточка заявляет первоисточник)
    from mcp_server import _proof_card
    adv = _make_advisor(tmp_path, [
        {"text": "A commentator paraphrase of the sage.", "tier": "S1", "source": "Commentary p.5"}])
    r = _proof_card("A commentator paraphrase of the sage.", adv)
    assert r["verified"] is False
    assert r.get("content") is None
