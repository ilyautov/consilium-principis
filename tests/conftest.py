"""Сьютовый пин судьи релевантности на "ollama" (single-phase, сервер судит).

§2.1 moat-v2 ввёл двухфазный host-протокол: при judge_backend=host cite возвращает
judgment_request вместо готовых цитат. В CI-среде (без ollama, без API-ключа) auto
резолвился бы в host — и ВЕСЬ легаси-контракт single-phase cite (early-exit, 🔵-приоритет,
fail-closed) перестал бы быть покрыт. Пин фиксирует легаси-режим как дефолт сьюта;
host-протокол и сама резолюция тестируются в своих файлах, переопределяя/снимая env
(monkeypatch function-scoped — пин восстанавливается после каждого теста).

Плюс СОКЕТ-ПЕСОЧНИЦА (M4): офлайн-инвариант делаем ТОТАЛЬНЫМ — любой случайный выход
в реальную сеть (OpenRouter, удалённый фетч) обязан упасть ГРОМКО, а не молча уйти на
провод. Гард патчит socket.socket.connect/connect_ex и БЛОКИРУЕТ только не-loopback
адреса. Loopback (127.0.0.0/8, ::1, localhost) РАЗРЕШЁН намеренно: офлайн-инвариант
целит OLLAMA_HOST в мёртвый 127.0.0.1:59999 и живёт на естественном ConnectionRefused →
graceful fallback; блокировать loopback = сломать этот путь. DNS/AF_UNIX не трогаем.

Плюс FS-ПЕСОЧНИЦА (M7): симметрия сокет-гарду на запись — тест, забывший запатчить
_root/_root-подобный резолвер и ПИШУЩИЙ в трекаемые файлы репо, падает громко, а не
молча пачкает рабочее дерево. Post-test сверка `git status --porcelain -uno`:
  • -uno скрывает UNTRACKED (статьи в корне, .superpowers/) — фейлит только изменение
    ТРЕКАЕМЫХ путей (M/D/A в индексе или рабочем дереве);
  • gitignored-записи (advisors/*, .consilium/, __pycache__/, .pytest_cache/) git не
    показывает вовсе → легальные кэши/стейт сьюта песочницу не задевают;
  • дельта снимков ДО→ПОСЛЕ теста: заранее грязное дерево (незакоммиченная работа)
    само по себе не фейлит — фейлит только ИЗМЕНЕНИЕ за время теста;
  • оптимизация: ОДИН git-вызов на тест — «после» предыдущего теста = «до» следующего
    (бегущий снимок в _fs_state), атрибуция по дельте соседних снимков.
"""
import ipaddress
import os
import socket
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _pin_judge_backend_single_phase(monkeypatch):
    monkeypatch.setenv("CONSILIUM_JUDGE_BACKEND", "ollama")


# ───────────────────────── сокет-песочница (M4) ─────────────────────────

_AF_UNIX = getattr(socket, "AF_UNIX", None)


def _addr_is_loopback(sock, address):
    """True → соединение РАЗРЕШЕНО (loopback / не-сетевой сокет). False → блокируем.

    Fail-open на непонятной форме адреса (не tuple, пусто) — не ломаем экзотические
    вызовы; сетевую утечку ловит IP-ветка. AF_UNIX (файловый) не сеть → разрешаем."""
    if _AF_UNIX is not None and getattr(sock, "family", None) == _AF_UNIX:
        return True
    if not isinstance(address, tuple) or not address:
        return True
    host = address[0]
    if host in ("localhost", "", None):
        return True                              # '' → INADDR_ANY на loopback-стеке
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False                             # хостнейм (не IP) = внешний → блок


def _make_guard(real):
    def _guard(self, address, *a, **k):
        if not _addr_is_loopback(self, address):
            raise RuntimeError("network blocked in tests: %r" % (address,))
        return real(self, address, *a, **k)
    return _guard


@pytest.fixture(scope="session", autouse=True)
def _block_external_network():
    """Блокирует РЕАЛЬНЫЙ внешний egress на всё время сьюта (loopback проходит естественно).
    Session-scoped setattr/restore (не monkeypatch — тот function-scoped)."""
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    socket.socket.connect = _make_guard(orig_connect)
    socket.socket.connect_ex = _make_guard(orig_connect_ex)
    try:
        yield
    finally:
        socket.socket.connect = orig_connect
        socket.socket.connect_ex = orig_connect_ex


# ───────────────────────── FS-песочница (M7) ─────────────────────────

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tracked_changes():
    """Снимок изменённых ТРЕКАЕМЫХ путей (`git status --porcelain -uno`); None — git недоступен."""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "-uno"],
                           cwd=_REPO_ROOT, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


_fs_state = {"last": None, "active": True}


@pytest.fixture(scope="session", autouse=True)
def _fs_sandbox_baseline():
    """Базовый снимок дерева до первого теста. Нет git/не репо → песочница выключается молча."""
    _fs_state["last"] = _tracked_changes()
    _fs_state["active"] = _fs_state["last"] is not None
    yield


@pytest.fixture(autouse=True)
def _fs_write_sandbox(_fs_sandbox_baseline):
    """Post-test гард: тест ИЗМЕНИЛ трекаемый путь вне tmp_path → громкий фейл с именами файлов."""
    yield
    if not _fs_state["active"]:
        return
    cur = _tracked_changes()
    last = _fs_state["last"]
    if cur is None:
        # git недоступен в этот момент (транзиентный сбой на раннере) — НЕ затираем
        # baseline в None, иначе следующий тест словит last.splitlines() на None и
        # песочница молча умрёт до конца сессии. Пропускаем проверку, baseline цел.
        return
    _fs_state["last"] = cur
    if last is None or cur == last:
        return
    new = sorted(set(cur.splitlines()) - set(last.splitlines()))
    gone = sorted(set(last.splitlines()) - set(cur.splitlines()))
    pytest.fail(
        "Тест изменил ТРЕКАЕМЫЕ файлы репо вне tmp_path (забыл monkeypatch _root / tmp_path?):\n"
        "  появились: %s\n  исчезли: %s\n"
        "Запись в корпус/стейт делай в tmp_path; gitignored-пути (advisors/*, .consilium/) "
        "песочница не видит." % (new or "—", gone or "—"),
        pytrace=False)


# ───────────────── демо-фикстура PD-корпусов (M7, CI) ─────────────────

_DEMO_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "demo_corpora")
_DEMO_SLUGS = ("marcus-aurelius", "machiavelli")          # только PD-фигуры, приватных слагов нет


def demo_corpus_available(slug):
    """Реальный (gitignored) корпус ИЛИ закоммиченная фикстура — условие skip демо-тестов."""
    real = os.path.join(_REPO_ROOT, "advisors", slug, "build", "corpus.jsonl")
    return os.path.isfile(real) or os.path.isfile(os.path.join(_DEMO_FIXTURES, slug + ".jsonl"))


@pytest.fixture(scope="session")
def demo_pd_corpora():
    """Материализует синтетический PD-корпус в advisors/<slug>/build/corpus.jsonl, ТОЛЬКО если
    реальный не собран (CI). Локально — no-op: демо гоняется по живому корпусу. Созданное
    прибирается на teardown; advisors/* gitignored → FS-песочница запись не видит."""
    import shutil
    created = []
    for slug in _DEMO_SLUGS:
        dest = os.path.join(_REPO_ROOT, "advisors", slug, "build", "corpus.jsonl")
        if os.path.isfile(dest):
            continue                                        # живой корпус НЕ трогаем никогда
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(_DEMO_FIXTURES, slug + ".jsonl"), dest)
        created.append(dest)
    yield
    for dest in created:
        os.remove(dest)
        for d in (os.path.dirname(dest), os.path.dirname(os.path.dirname(dest))):
            try:
                os.rmdir(d)                                 # убираем build/ и advisors/<slug>/, если пусты
            except OSError:
                pass                                        # не пусто (свои артефакты) — оставляем
