"""H5: read-side path-traversal гард. `_resolve` НЕ ограничивал результат корнем — только
write-side `_resolve_under_root` делал. Read-тулы, берущие advisor_dir от хоста через `_resolve`,
позволяли advisor_dir="../outside" читать корпус ВНЕ корня репо. Гард: относительный путь,
вылезающий за корень → fail-closed (ничего не читаем). Абсолютные пути — явные/доверенные
(внутренние вызовы и существующие тесты передают уже срезолвленный abs-путь) → пропускаем
(иначе ломается поведение, на которое эти тесты опираются; см. test_marker_status/quote_of_day).

Каждый reject-тест САЖАЕТ реально читаемый корпус ВНЕ патченного корня и достаёт его через
'../outside' — так тест ловит именно traversal (без гарда → корпус прочитан → 🔵/grounded;
с гардом → отказ). Пустой /etc «проходил» бы и без гарда (там нет corpus.jsonl) — это не тест."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

PHRASE = "secret leaked verbatim phrase outside root"


def _planted_root(srv, monkeypatch, tmp_path, *, corpus=True, manifest=False):
    """root = tmp_path/root; за его пределами (tmp_path/outside, достижимо '../outside')
    сажаем читаемые артефакты, которые гард ОБЯЗАН не дать прочитать."""
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(srv, "_root", lambda: str(root))
    outside = tmp_path / "outside"
    if corpus:
        (outside / "build").mkdir(parents=True)
        (outside / "build" / "corpus.jsonl").write_text(
            '{"text":"%s","tier":"P1"}\n' % PHRASE, encoding="utf-8")
    if manifest:
        (outside / "sources").mkdir(parents=True)
        (outside / "sources" / "manifest.json").write_text(
            '{"book.txt": {"tier": "P1"}}', encoding="utf-8")
    return root, outside


def test_fidelity_check_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._fidelity_check(PHRASE, "../outside")
    assert out["status"] == "🟡" and out["verbatim"] is False   # traversal заблокирован — корпус не прочитан


def test_fidelity_check_allows_inside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    root, _ = _planted_root(srv, monkeypatch, tmp_path)
    adv = root / "advisors" / "a" / "build"
    adv.mkdir(parents=True)
    (adv / "corpus.jsonl").write_text('{"text":"%s","tier":"P1"}\n' % PHRASE, encoding="utf-8")
    out = srv._fidelity_check(PHRASE, "advisors/a")
    assert out["status"] == "🔵"                                # легит-путь под корнем читается


def test_fidelity_check_absolute_path_outside_root_rejected(monkeypatch, tmp_path):
    """Ужесточение (решение владельца): АБСОЛЮТНЫЙ путь вне корня тоже клампится → 🟡.
    _root НЕ патчим — реальный корень репо; abs tmp_path заведомо вне него."""
    import mcp_server as srv
    adv = tmp_path / "adv" / "build"
    adv.mkdir(parents=True)
    (adv / "corpus.jsonl").write_text('{"text":"%s","tier":"P1"}\n' % PHRASE, encoding="utf-8")
    out = srv._fidelity_check(PHRASE, str(tmp_path / "adv"))
    assert out["status"] == "🟡" and out["verbatim"] is False   # abs вне корня → не прочитан


def test_fidelity_check_absolute_path_inside_root_allowed(monkeypatch, tmp_path):
    """Легит abs-путь ПОД (патченным) корнем обязан проходить — иначе сломан гард, не сетап."""
    import mcp_server as srv
    monkeypatch.setattr(srv, "_root", lambda: str(tmp_path))
    adv = tmp_path / "adv" / "build"
    adv.mkdir(parents=True)
    (adv / "corpus.jsonl").write_text('{"text":"%s","tier":"P1"}\n' % PHRASE, encoding="utf-8")
    out = srv._fidelity_check(PHRASE, str(tmp_path / "adv"))    # abs, но под корнем
    assert out["status"] == "🔵"


def test_retrieve_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._retrieve(PHRASE, "../outside")
    assert out.get("passages") == []                            # traversal-корпус не отдан пассажами


def test_cite_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._cite("../outside", PHRASE, use_kernels=False)
    assert out.get("best") is None and out.get("quotes") == []  # traversal-корпус не процитирован


def test_quote_of_day_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._quote_of_day("../outside", date="2026-07-11")
    assert out.get("marker") != "🔵" and "note" in out          # traversal-цитата не выдана


def test_atomic_grounding_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._atomic_grounding(PHRASE, "../outside")
    assert out["atom_level"] == 0.0                             # traversal-корпус не обосновал ни атома


def test_validate_manifest_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path, corpus=False, manifest=True)
    out = srv._validate_manifest("../outside")
    assert out.get("problems") == []                           # манифест вне корня не прочитан


def test_governance_verify_rejects_outside_root(monkeypatch, tmp_path):
    import mcp_server as srv
    _planted_root(srv, monkeypatch, tmp_path)
    out = srv._governance_verify("../outside/build/corpus.jsonl")
    assert out.get("ok") is False                              # цепь целостности вне корня не проверяем


def test_governance_verify_absolute_path_outside_root_rejected(monkeypatch, tmp_path):
    """Ужесточение: abs .jsonl-путь вне корня (host-exposed arbitrary-read) → отказ, файл не читан.
    _root НЕ патчим — реальный корень; /etc/hosts заведомо вне него."""
    import mcp_server as srv
    out = srv._governance_verify("/etc/hosts")
    assert out.get("ok") is False and "error" in out           # abs вне корня → не читаем
