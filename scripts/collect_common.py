#!/usr/bin/env python3
"""
collect_common.py — общая база для сборщиков корпусов (collect_pd / collect_web / collect_transcript).

Принцип (ЛЕГАЛЬНАЯ ГРАНИЦА, см. SKILL.md):
  - сборщики НЕ дублируют пайплайн build_advisor.py; они легально НАПОЛНЯЮТ advisors/{name}/sources/
    текстом, дальше build_advisor.py делает чанкинг/провенанс/кандидаты-цитаты.
  - каждый файл получает provenance-заголовок (URL + дата + лицензия), чтобы fidelity-гейт и
    атрибуция знали происхождение.
  - public-domain тянется свободно; публичное-но-копирайтное (эссе/твиты/блоги/транскрипты) —
    только с явным подтверждением personal-use + дисклеймер «персона = симуляция».
  - большие тексты пишутся В ФАЙЛ, наружу печатается только сводка.
"""
import os, re, sys, json, urllib.request, urllib.error, datetime
import socket, ipaddress, ssl, http.client
from urllib.parse import urlparse, urljoin

UA = "Mozilla/5.0 (Consilium-Principis corpus collector; personal use)"

# Хосты, заведомо отдающие public-domain (для collect_pd авто-подтверждение PD).
PD_HOSTS = ("gutenberg.org", "www.gutenberg.org", "gutenberg.net",
            "wikisource.org", "standardebooks.org", "sacred-texts.com")


def today():
    return datetime.date.today().isoformat()


def host_of(url):
    m = re.match(r"https?://([^/]+)/?", url or "")
    return (m.group(1).lower() if m else "")


def is_pd_host(url):
    h = host_of(url)
    return any(h == d or h.endswith("." + d) for d in PD_HOSTS)


def _is_public_ip(addr):
    ip = ipaddress.ip_address(addr)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def _pick_public_ip(host, port):
    """getaddrinfo(host) → (первый ПУБЛИЧНЫЙ IP, None) или (None, ошибка с непубличным IP)."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as e:
        return None, f"host не резолвится: {e}"
    blocked = []
    for info in infos:
        addr = info[4][0]
        if _is_public_ip(addr):
            return addr, None
        blocked.append(addr)
    return None, f"host резолвится в непубличный IP ({blocked[0] if blocked else '?'}) — заблокировано (SSRF)"


def ssrf_check(url):
    """SSRF-гард: возвращает строку-ошибку или None. Тул дёргается хостом (возможна инъекция из
    веб-контента) → фетч во внутренние сервисы/метадату облака недопустим. Схема только http(s);
    host обязан резолвиться в публичный IP."""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https"):
        return f"схема '{p.scheme or '—'}' запрещена — только http/https"
    if not p.hostname:
        return "не разобрал host из url"
    _, err = _pick_public_ip(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    return err


def _decode(raw):
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _fetch_once(url, timeout):
    """Один GET к ЗАКРЕПЛЁННОМУ публичному IP (host резолвится ОДИН раз и коннект идёт ровно к
    тому IP — закрывает DNS-rebinding окно между проверкой и коннектом). TLS: SNI/валидация серта
    по ИМЕНИ хоста, не по IP. Возвращает (status, location|None, body|None)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"SSRF-гард: схема '{p.scheme or '—'}' запрещена")
    host, port = p.hostname, p.port or (443 if p.scheme == "https" else 80)
    ip, err = _pick_public_ip(host, port)
    if err:
        raise ValueError(f"SSRF-гард: {err}")
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    raw_sock = socket.create_connection((ip, port), timeout=timeout)
    try:
        sock = (ssl.create_default_context().wrap_socket(raw_sock, server_hostname=host)
                if p.scheme == "https" else raw_sock)              # SNI=host → серт валидится по host
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.sock = sock                                            # коннект уже к проверенному IP
        conn.request("GET", path, headers={"User-Agent": UA, "Host": host})
        resp = conn.getresponse()
        if resp.status in (301, 302, 303, 307, 308):
            return resp.status, resp.getheader("Location"), None
        return resp.status, None, resp.read()
    finally:
        raw_sock.close()


def fetch(url, timeout=30, public_only=True):
    """GET → текст. public_only (дефолт): SSRF-гард с IP-pinning (резолв+валидация+коннект к тому же
    IP) и ре-валидацией каждого редирект-хопа — без DNS-rebinding окна."""
    if not public_only:                                            # явный небезопасный путь (не юзается)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _decode(r.read())
    cur = url
    for _ in range(6):                                            # лимит редиректов
        status, location, body = _fetch_once(cur, timeout)
        if body is not None:
            return _decode(body)
        if not location:
            raise ValueError(f"редирект {status} без Location")
        cur = urljoin(cur, location)                              # следующий хоп ре-валидируется в _fetch_once
    raise ValueError("слишком много редиректов")


def html_to_text(html, selector=None):
    """HTML → читаемый текст. selector (CSS) — если задан, берём только этот контейнер."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        # грубый фолбэк без bs4
        txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        txt = re.sub(r"(?s)<[^>]+>", "\n", txt)
        return re.sub(r"\n{3,}", "\n\n", txt)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    node = soup.select_one(selector) if selector else (
        soup.select_one("article") or soup.select_one("main") or soup.body or soup)
    lines = [ln.strip() for ln in node.get_text("\n").splitlines()] if node else []
    return "\n".join(ln for ln in lines if ln)


def slugify(s):
    s = re.sub(r"[^\w\s-]", "", (s or "").lower(), flags=re.U)
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:60] or "source"


def land_to_sources(advisor_dir, basename, text, *, url, license_note, extra_meta=None):
    """Пишет текст в advisors/{name}/sources/{basename}.txt с provenance-заголовком.
    Возвращает путь. sources/ — gitignored (чужие тексты в историю не уходят)."""
    src_dir = os.path.join(advisor_dir, "sources")
    os.makedirs(src_dir, exist_ok=True)
    path = os.path.join(src_dir, f"{slugify(basename)}.txt")
    header = [
        f"# SOURCE: {url}",
        f"# FETCHED: {today()}",
        f"# LICENSE: {license_note}",
    ]
    if extra_meta:
        for k, v in extra_meta.items():
            header.append(f"# {k.upper()}: {v}")
    header.append("# " + "-" * 60)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(header) + "\n" + text.strip() + "\n")
    # сайдкар-манифест провенанса (для аудита; sources/ всё равно gitignored)
    man = os.path.join(src_dir, "_provenance.jsonl")
    with open(man, "a", encoding="utf-8") as f:
        rec = {"file": os.path.basename(path), "url": url, "fetched": today(),
               "license": license_note, "chars": len(text)}
        if extra_meta:
            rec.update(extra_meta)
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def require_advisor_dir(advisor_dir):
    if not os.path.isdir(advisor_dir):
        print(f"Нет папки советника: {advisor_dir}", file=sys.stderr)
        sys.exit(1)


def summary(path, text, kind):
    print(f"  ✓ {kind}: {len(text)} симв (~{len(text)//4} токенов) → {path}")
    print(f"    дальше: python scripts/build_advisor.py {os.path.dirname(os.path.dirname(path))} "
          f"--name \"{{Имя}}\"  → corpus.jsonl + quote_candidates")
