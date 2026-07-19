"""Регрессионный гард: провенанс-граф (L2.2) НЕ подключён к прод-гейту верности.

Мотив (аудит M2, «заряженное ружьё»): `corpusbuild.graph.marker_of` мапит kind
"kernel" → 🔵 (см. `_BLUE = {"p1","p2","kernel"}`), а `fidelity.marker_for_path`
оборачивает `graph.weakest_link`. Кернел — LLM-производный узел; если бы
`marker_for_path` был вызван в живом MCP-пути, составной ответ мог бы получить 🔵
на силе LLM-кернела — это ровно «воркер само-сертифицирует 🔵», что контур запрещает.

Сейчас путь БЕЗОПАСЕН: живой гейт = `best_match`/`marker_status` (per-chunk вербатим),
граф в него не входит, `marker_for_path`/`weakest_link` не имеют ни одного рантайм-вызова
(только тесты). Этот гард ПИНИТ неподключённость: если кто-то заведёт граф-провенанс в
MCP-поверхность, тест падёт и заставит осознанно пересмотреть moat-семантику
(в частности, kernel→🔵) ПЕРЕД тем, как ружьё окажется заряжено И подключено.
"""
import os

_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _server_source():
    with open(os.path.join(_ROOT, "scripts", "mcp_server.py"), encoding="utf-8") as f:
        return f.read()


def test_marker_for_path_not_wired_into_mcp_surface():
    """MCP-сервер не должен ссылаться на граф-провенансный маркер, пока kernel→🔵
    не пересмотрен. Подключишь — сознательно сними этот гард после moat-ревью."""
    src = _server_source()
    for banned in ("marker_for_path", "weakest_link", "assemble_graph"):
        assert banned not in src, (
            f"{banned} появился в mcp_server.py — граф-провенанс (kernel→🔵) подключается "
            f"к прод-поверхности. Это заряжает 'ружьё' само-сертификации 🔵. Проведи "
            f"moat-ревью (нужен ли kernel в _BLUE?) и только затем осознанно правь этот гард."
        )


def test_live_fidelity_gate_is_per_chunk_verbatim_not_graph():
    """Санити: живой гейт верности — marker_status/best_match (per-chunk вербатим),
    независимый от графа. Импортируется без движка (backend-независим)."""
    import sys
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))
    from engine import fidelity
    assert hasattr(fidelity, "marker_status"), "живой гейт marker_status пропал"
    assert hasattr(fidelity, "best_match"), "живой гейт best_match пропал"
