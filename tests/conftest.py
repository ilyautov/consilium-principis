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
"""
import ipaddress
import socket

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
