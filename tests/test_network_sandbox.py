"""Позитивный тест сокет-песочницы conftest (M4): гард сам работает.

Инвариант: не-loopback connect падает ГРОМКО (RuntimeError «network blocked»),
loopback connect гард ПРОПУСКАЕТ до естественного отказа (мёртвый порт → ConnectionRefused).
Второй — регресс на «не переусердствовали»: офлайн-инвариант целит OLLAMA_HOST в
127.0.0.1:59999 и живёт на этом отказе; заблокируй loopback — сломаешь fallback.
"""
import socket

import pytest


def test_guard_blocks_non_loopback():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="network blocked"):
            s.connect(("8.8.8.8", 53))
    finally:
        s.close()


def test_guard_blocks_external_hostname():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="network blocked"):
            s.connect(("openrouter.ai", 443))
    finally:
        s.close()


def test_guard_allows_loopback_to_natural_refusal():
    """Loopback НЕ блокируется гардом: доходит до реального отказа ОС (мёртвый порт).
    RuntimeError тут = гард переусердствовал; ConnectionRefused/OSError = гард пропустил."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        with pytest.raises(OSError) as ei:
            s.connect(("127.0.0.1", 59999))
        assert not isinstance(ei.value, RuntimeError), "гард ошибочно заблокировал loopback"
    finally:
        s.close()


def test_guard_allows_localhost_name():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        with pytest.raises(OSError) as ei:
            s.connect(("localhost", 59999))
        assert not isinstance(ei.value, RuntimeError), "гард ошибочно заблокировал localhost"
    finally:
        s.close()
