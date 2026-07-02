"""Слоёная защита collect_common.fetch для open-source (R3-остаток аудита 2026-06-30):
https-only по умолчанию · запрет даунгрейда https→http на редиректах · SSRF (публичный IP)
· IP-pinning · потолок размера. ВСЁ офлайн: сокеты/резолвер/хопы замоканы — сети в тестах нет.
"""
import io
import os
import socket
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import collect_common as cc


# ─────────────────────────── слой 1: https-only по умолчанию ───────────────────────────

def test_http_refused_by_default_before_any_network(monkeypatch):
    # Отказ обязан случиться ДО DNS/коннекта: любое обращение к сети в тесте — провал.
    def _boom(*a, **kw):
        raise AssertionError("схема должна резаться ДО резолва/коннекта")
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    with pytest.raises(ValueError, match="http без шифрования"):
        cc.fetch("http://example.com/book.txt")


def test_http_allowed_only_with_explicit_flag(monkeypatch):
    monkeypatch.setattr(cc, "_fetch_once", lambda url, t, mb=None: (200, None, b"plain ok"))
    assert cc.fetch("http://example.com/x", allow_http=True) == "plain ok"


def test_non_web_scheme_refused():
    with pytest.raises(ValueError, match="запрещена"):
        cc.fetch("file:///etc/passwd")
    with pytest.raises(ValueError, match="запрещена"):
        cc.fetch("ftp://example.com/x")


# ─────────────────────── слой 4: редиректы — ре-валидация каждого хопа ───────────────────────

def test_redirect_downgrade_https_to_http_refused(monkeypatch):
    # Открытый редирект https→http = текст дальше идёт открытым; запрещён ДАЖЕ с allow_http=True.
    monkeypatch.setattr(cc, "_fetch_once",
                        lambda url, t, mb=None: (302, "http://example.com/plain", None))
    with pytest.raises(ValueError, match="даунгрейд"):
        cc.fetch("https://example.com/start", allow_http=True)


def test_redirect_upgrade_http_to_https_allowed(monkeypatch):
    hops = []

    def fake(url, t, mb=None):
        hops.append(url)
        if url.startswith("http://"):
            return 301, "https://example.com/secure", None
        return 200, None, b"upgraded"

    monkeypatch.setattr(cc, "_fetch_once", fake)
    assert cc.fetch("http://example.com/x", allow_http=True) == "upgraded"
    assert hops == ["http://example.com/x", "https://example.com/secure"]


def test_redirect_hop_cap(monkeypatch):
    monkeypatch.setattr(cc, "_fetch_once",
                        lambda url, t, mb=None: (301, "https://example.com/again", None))
    with pytest.raises(ValueError, match="слишком много редиректов"):
        cc.fetch("https://example.com/loop")


def test_redirect_without_location_refused(monkeypatch):
    monkeypatch.setattr(cc, "_fetch_once", lambda url, t, mb=None: (302, None, None))
    with pytest.raises(ValueError, match="без Location"):
        cc.fetch("https://example.com/x")


# ─────────────────── слой 2: SSRF — private/loopback/link-local IP режутся ───────────────────

def _addrinfo(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


@pytest.mark.parametrize("ip", ["10.0.0.1", "127.0.0.1", "169.254.169.254", "192.168.1.7"])
def test_private_loopback_linklocal_ip_refused(monkeypatch, ip):
    # 169.254.169.254 — метадата облака: классическая цель SSRF при инъекции URL из контента.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo(ip))
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **kw: pytest.fail("коннект к непубличному IP не должен случиться"))
    with pytest.raises(ValueError, match="SSRF"):
        cc.fetch("https://internal.example/secret")


def test_redirect_into_private_zone_refused(monkeypatch):
    # Хоп 1 — обычный ответ-редирект; хоп 2 резолвится в приватную зону → отказ на ре-валидации.
    real_once = cc._fetch_once

    def fake(url, t, mb=None):
        if "public.example" in url:
            return 302, "https://internal.example/admin", None
        return real_once(url, t, mb)                      # настоящий путь → SSRF-гард сработает

    monkeypatch.setattr(cc, "_fetch_once", fake)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo("10.13.13.13"))
    with pytest.raises(ValueError, match="SSRF"):
        cc.fetch("https://public.example/start")


def test_unresolvable_host_refused(monkeypatch):
    def _nope(*a, **kw):
        raise socket.gaierror("NXDOMAIN")
    monkeypatch.setattr(socket, "getaddrinfo", _nope)
    with pytest.raises(ValueError, match="не резолвится"):
        cc.fetch("https://no-such-host.example/")


# ─────────────────────────── слой 5: потолок размера ───────────────────────────

class _FakeResp:
    def __init__(self, body, content_length=None):
        self._buf = io.BytesIO(body)
        self._cl = content_length

    def getheader(self, name):
        return self._cl if name == "Content-Length" else None

    def read(self, n=-1):
        return self._buf.read(n)


def test_size_cap_cuts_honest_content_length_before_reading():
    resp = _FakeResp(b"x", content_length=str(cc.MAX_FETCH_BYTES + 1))
    with pytest.raises(ValueError, match="больше лимита"):
        cc._read_capped(resp, cc.MAX_FETCH_BYTES)


def test_size_cap_catches_lying_or_missing_content_length():
    # Content-Length молчит, тело льётся сверх лимита → почанковый счётчик режет.
    resp = _FakeResp(b"A" * 300, content_length=None)
    with pytest.raises(ValueError, match="больше лимита"):
        cc._read_capped(resp, 100)


def test_size_cap_passes_body_within_limit():
    assert cc._read_capped(_FakeResp(b"small body", content_length="10"), 100) == b"small body"


def test_fetch_pipes_size_cap_through(monkeypatch):
    def fake(url, t, mb=cc.MAX_FETCH_BYTES):
        cc._read_capped(_FakeResp(b"B" * 64), mb)         # как в настоящем _fetch_once
        return 200, None, b"never"
    monkeypatch.setattr(cc, "_fetch_once", fake)
    with pytest.raises(ValueError, match="больше лимита"):
        cc.fetch("https://example.com/big", max_bytes=10)
