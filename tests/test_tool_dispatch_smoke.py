"""Дымовые тесты диспатча (M4): каждый ранее-НЕ-дёрганный тул проводится через РЕАЛЬНЫЙ
путь dispatch с минимально-валидными аргументами.

Цель — покрыть проводку dispatch + имена аргументов (ловим signature drift), а НЕ логику
тула. Ассерт намеренно слабый: тул диспатчится и возвращает dict без НЕОЖИДАННОГО
исключения. Тул, легитимно вернувший error/abstain-dict на отсутствие данных, — это ОК
(проверяем «вернул dict», а не «преуспел»).

Гэп вычислен так: имя тула в m.TOOLS, которое НИ ОДИН другой тест не диспатчит и не зовёт
его handler-функцию напрямую (см. test_smoke_covers_all_undispatched_tools — он пересчитывает
гэп и падает, если появился новый непокрытый тул). На момент написания: 7 тулов —
build_advisor, capture_situation, catalog_verify, export_session, federation_heartbeat,
ingest_telegram, setup_full.

СКИПОВ НЕТ. Все 7 деградируют gracefully под офлайн-инвариантом (эмпирически проверено):
  • capture_situation / export_session — чистый оффлайн (extractor / session_render);
  • setup_full(consent=False) — только план, БЕЗ выполнения (сеть/ollama не трогаются);
  • federation_heartbeat — sqlite в tmp; неизвестный task → {stale: ...} (dict);
  • catalog_verify — под hermetic tmp-root каталог пуст → ноль фетчей → {ok, entries:[]};
    (а если бы фетчил — verify_catalog ловит сетевую ошибку per-entry в status:"error");
  • build_advisor / ingest_telegram — ФОНОВЫЙ джоб: синхронно отдают {job_id} СРАЗУ, БЕЗ
    сети (реальная работа — в daemon-нити, её ошибки глотает _start_job). Мы проверяем
    именно синхронную проводку диспатча (имена аргументов), что и есть цель M4.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import mcp_server as m  # noqa: E402


# name -> builder(tmp_path) -> args. Data-driven: добавление тула = одна строка.
_SMOKE = {
    "capture_situation": lambda t: {"text": "Alice proposed shipping now; Bob pushed back hard."},
    "export_session": lambda t: {"session": {"question": "Should we ship?", "advisors": []}},
    "catalog_verify": lambda t: {},
    "federation_heartbeat": lambda t: {"task_id": "no-such-task", "worker_id": "w1",
                                       "claim_token": "tok"},
    "setup_full": lambda t: {"consent": False},
    "build_advisor": lambda t: {"advisor_dir": os.path.join(str(t), "advisors", "some-advisor")},
    "ingest_telegram": lambda t: {"handle": "@some_nonexistent_test_channel"},
}


@pytest.fixture
def hermetic_root(tmp_path, monkeypatch):
    """Корень репо → tmp_path (пути/стейт тулов не трогают реальный проект); федерация-бэкенд
    сбрасывается, чтобы sqlite лёг в tmp, а не в общий singleton."""
    monkeypatch.setattr(m, "_root", lambda: str(tmp_path))
    monkeypatch.setattr(m, "_FED_BACKEND", None, raising=False)
    return tmp_path


@pytest.mark.parametrize("name", sorted(_SMOKE))
def test_tool_dispatches_to_dict(name, hermetic_root):
    args = _SMOKE[name](hermetic_root)
    res = m.dispatch(name, args)
    assert isinstance(res, dict), "%s: диспатч вернул %r, ожидался dict" % (name, type(res))


def _undispatched_tools():
    """Пересчитать гэп: тулы m.TOOLS, которые НИКАКОЙ тест (кроме этого smoke-файла) не
    диспатчит и не зовёт их handler-функцию напрямую. Держит smoke-таблицу честной: новый
    тул без покрытия → test_smoke_covers_all_undispatched_tools упадёт с его именем."""
    tdir = os.path.dirname(__file__)
    here = os.path.basename(__file__)
    blob = ""
    for root, _dirs, files in os.walk(tdir):
        for f in files:
            if f.endswith(".py") and f != here:
                blob += open(os.path.join(root, f), encoding="utf-8").read()
    gap = []
    for name in m.TOOLS:
        hname = m.TOOLS[name]["handler"].__name__
        dispatched = re.search(r"dispatch\(\s*[\"']%s[\"']" % re.escape(name), blob)
        handler_called = re.search(r"[^\w]%s\(" % re.escape(hname), blob)
        tools_handler = re.search(
            r"TOOLS\[[\"']%s[\"']\]\[[\"']handler[\"']\]" % re.escape(name), blob)
        if not (dispatched or handler_called or tools_handler):
            gap.append(name)
    return set(gap)


def test_smoke_covers_all_undispatched_tools():
    """Всякий тул, который больше НИГДЕ не диспатчится, обязан быть в smoke-таблице."""
    uncovered = _undispatched_tools() - set(_SMOKE)
    assert not uncovered, ("Тулы без единого dispatch-покрытия — добавь в _SMOKE или покрой "
                           "предметным тестом: %s" % sorted(uncovered))


def test_smoke_table_names_are_real_tools():
    unknown = set(_SMOKE) - set(m.TOOLS)
    assert not unknown, "В _SMOKE есть несуществующие тулы: %s" % sorted(unknown)
