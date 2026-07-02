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
import os, re, sys, json, datetime
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


def _embedded_v4s(ip):
    """IPv4-адреса, СПРЯТАННЫЕ внутри туннельных v6-форм: IPv4-mapped (::ffff:a.b.c.d),
    6to4 (2002::/16) и Teredo (2001::/32). Без этого приватный v4 (10.0.0.1) прячется в
    публично-выглядящем v6 (2002:a00:1::1 с is_global=True) и обходит блоклист."""
    out = []
    for attr in ("ipv4_mapped", "sixtofour"):
        v = getattr(ip, attr, None)
        if v is not None:
            out.append(v)
    teredo = getattr(ip, "teredo", None)               # (server_v4, client_v4)
    if teredo is not None:
        out.extend(teredo)
    return out


def _is_public_ip(addr):
    """АЛЛОУЛИСТ по is_global (а не позитивный блоклист): закрывает CGNAT 100.64.0.0/10
    (is_private=False на 3.11, но внутреннее облако — AWS internal / GKE pod-svc) и прочие
    не-глобальные диапазоны одним движением. Плюс рекурсивная проверка встроенного v4 в
    туннельных v6-формах (6to4 is_global=True флагом не ловится). multicast/reserved
    исключаем явно (::ffff:-mapped помечен reserved → блок, безопасное направление сохранено)."""
    ip = ipaddress.ip_address(addr)
    for emb in _embedded_v4s(ip):                      # спрятанный приватный v4 → блок
        if not _is_public_ip(str(emb)):
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved)


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


# Потолок скачивания: PD-книги — единицы МБ; всё сильно больше — не «источник советника»,
# а заливка (истощение диска/памяти через отравленный URL или бесконечный стрим).
MAX_FETCH_BYTES = 20 * 1024 * 1024


def _read_capped(resp, max_bytes):
    """Тело ответа с жёстким потолком байт. Content-Length (если сервер прислал) режется ДО
    чтения; лживый/отсутствующий Content-Length ловится почанковым счётчиком (стрим без
    заголовка не обойдёт лимит)."""
    try:
        cl = resp.getheader("Content-Length")
    except Exception:
        cl = None
    if cl and cl.isdigit() and int(cl) > max_bytes:
        raise ValueError(f"источник больше лимита {max_bytes // (1024 * 1024)} МБ — отказ (анти-заливка)")
    chunks, total = [], 0
    while True:
        chunk = resp.read(65536)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"источник больше лимита {max_bytes // (1024 * 1024)} МБ — отказ (анти-заливка)")
        chunks.append(chunk)


def _check_scheme(scheme, prev_scheme, allow_http):
    """Политика схем: https-only по умолчанию; http — только по явному allow_http;
    даунгрейд https→http на редиректе запрещён ВСЕГДА (даже с allow_http)."""
    if scheme not in ("http", "https"):
        raise ValueError(f"схема '{scheme or '—'}' запрещена — только https (http лишь с allow_http)")
    if scheme == "http":
        if prev_scheme == "https":
            raise ValueError("редирект-даунгрейд https→http запрещён — дальше по пути текст шёл бы открытым")
        if not allow_http:
            raise ValueError("http без шифрования запрещён по умолчанию — используй https-URL "
                             "(или явно allow_http=True, если источник доступен только по http)")


def _fetch_once(url, timeout, max_bytes=MAX_FETCH_BYTES):
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
        return resp.status, None, _read_capped(resp, max_bytes)
    finally:
        raw_sock.close()


def fetch(url, timeout=30, allow_http=False, max_bytes=MAX_FETCH_BYTES):
    """GET → текст, ВСЕГДА через слои защиты (что каждый даёт и чего НЕ даёт — честно):

      1. https-only по умолчанию: http-URL → отказ, если не allow_http=True явно; даунгрейд
         https→http на редиректе запрещён всегда. Защищает от MITM-подмены текста по пути.
         НЕ защищает от вредоносного КОНТЕНТА на легитимном https-хосте.
      2. SSRF-гард: host обязан резолвиться в ПУБЛИЧНЫЙ IP (аллоулист по is_global +
         извлечение встроенного v4 из туннелей; CGNAT/private/loopback/link-local → отказ).
         Защищает метадату облака и внутренние сервисы от фетча по инъецированному URL. НЕ
         покрывает OLLAMA_HOST (env-only, осознанно: localhost там легитимен) и публичные
         хосты под контролем атакующего.
      3. IP-pinning: host резолвится ОДИН раз, коннект идёт ровно к проверенному IP; TLS
         SNI/серт валидируются по ИМЕНИ хоста. Закрывает DNS-rebinding окно «проверил одно,
         соединился с другим». НЕ защищает, если сам легитимный DNS-ответ уже указывает на
         хост атакующего (публичный IP с валидным сертом — это «настоящий» чужой сервер).
      4. Редиректы: максимум 6 хопов, каждый хоп заново проходит слои 1-3 (схема, SSRF,
         pinning). Защищает от open-redirect в приватную зону/на http. НЕ защищает от
         редиректа на другой ПУБЛИЧНЫЙ https-хост — это легитимный веб.
      5. Потолок размера (max_bytes, дефолт 20 МБ): Content-Length ДО чтения + почанковый
         счётчик (лживый заголовок не обходит). Защищает от заливки диска/памяти. НЕ
         защищает от медленного стрима (это режет timeout).

    Небезопасного bypass-пути (сырой urlopen без слоёв 2-3) НЕТ намеренно — единственный
    путь наружу проходит все гарды."""
    _check_scheme(urlparse(url or "").scheme, None, allow_http)   # слой 1 — ДО любого DNS/коннекта
    cur, prev_scheme = url, None
    for _ in range(6):                                            # лимит редиректов
        _check_scheme(urlparse(cur).scheme, prev_scheme, allow_http)  # ре-валидация КАЖДОГО хопа
        status, location, body = _fetch_once(cur, timeout, max_bytes)
        if body is not None:
            return _decode(body)
        if not location:
            raise ValueError(f"редирект {status} без Location")
        prev_scheme = urlparse(cur).scheme
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
