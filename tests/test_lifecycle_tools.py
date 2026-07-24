"""Zero-code-edit жизненный цикл из чистого MCP-хоста: тюнинг конфига и подъём FULL-тира — тулами,
без правки файлов и шелла. Стережёт: config_get/set реально пишут board_config.json; ollama_* не
падают и честно сообщают про единственный ручной шаг (установка бинаря)."""
import os, sys, json
import pytest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import mcp_server
from mcp_server import dispatch, list_tools, _config_path


@pytest.fixture(autouse=True)
def _root_in_tmp(monkeypatch, tmp_path):
    # write-side traversal-гард ограничивает запись корнем репо; тесты пишут советников в tmp_path,
    # поэтому КОРНЕМ на время теста делаем сам tmp_path (advisor_dir под ним → гард пропускает).
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))


def test_config_set_get_roundtrip_persists(monkeypatch, tmp_path):
    cfg = tmp_path / "board_config.json"
    monkeypatch.setattr("mcp_server._config_path", lambda: str(cfg))
    dispatch("config_set", {"key": "retrieval_mode", "value": "hybrid"})
    assert dispatch("config_get", {"key": "retrieval_mode"})["value"] == "hybrid"
    on_disk = json.load(open(cfg, encoding="utf-8"))      # реально записан в файл
    assert on_disk["retrieval_mode"] == "hybrid"
    r = dispatch("config_get", {})
    assert "retrieval_mode" in r["config"] and "known_keys" in r


def test_config_set_rejects_unknown_key(monkeypatch, tmp_path):
    # M3 (breaking): было «warning на неизвестном ключе» — теперь fail-closed reject
    monkeypatch.setattr("mcp_server._config_path", lambda: str(tmp_path / "c.json"))
    r = dispatch("config_set", {"key": "frobnicate", "value": 1})
    assert "error" in r and r["rejected"] == 1
    assert not (tmp_path / "c.json").exists()


def test_ollama_status_shape_no_crash():
    r = dispatch("ollama_status", {})
    assert {"ollama_running", "bge_m3_present"} <= set(r)   # стабильная форма, без падений
    assert r["hint"] and "umni" not in r["hint"].lower()   # человеч. подсказка есть, не пустая


def test_ollama_ensure_reports_manual_when_binary_absent(monkeypatch):
    import mcp_server
    monkeypatch.setattr("setup_full.probe", lambda: {"ollama_running": False, "bge_m3_present": False})
    def _no_binary(*a, **k):
        raise FileNotFoundError("ollama")
    monkeypatch.setattr(mcp_server.subprocess if hasattr(mcp_server, "subprocess") else __import__("subprocess"),
                        "Popen", _no_binary, raising=False)
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", _no_binary)
    r = dispatch("ollama_ensure", {})
    assert r["running"] is False and "manual" in r          # честный единственный ручной шаг


def test_add_source_text_lands_and_sets_tier_then_builds(tmp_path):
    # без шелла: text → sources/ + tier-манифест → pipeline собирает корпус с этим тиром
    adv = str(tmp_path / "adv")
    r = dispatch("add_source", {"advisor_dir": adv,
                 "text": "All warfare is based on deception, the canon repeats.",
                 "basename": "canon", "tier": "P1"})
    assert r["ok"] and r["tier"] == "P1"
    man = json.load(open(os.path.join(adv, "sources", "manifest.json"), encoding="utf-8"))
    assert man[r["source_file"]]["tier"] == "P1"
    # сборка видит источник и проставленный тир → дословная фраза проходит гейт как 🔵
    # (детерминированно через fidelity_check; recall cite зависит от семантики — это не предмет add_source)
    from corpusbuild import pipeline
    pipeline.build(adv)
    fc = dispatch("fidelity_check", {"quote": "All warfare is based on deception",
                                     "advisor_dir": adv})
    assert fc["status"] == "🔵" and fc["verbatim"] is True


def test_add_source_url_uses_fetch_and_strips_gutenberg(monkeypatch, tmp_path):
    import collect_common as cc
    monkeypatch.setattr(cc, "fetch", lambda url, timeout=30:
                        "*** START OF THE PROJECT GUTENBERG EBOOK X ***\nReal body text here.\n"
                        "*** END OF THE PROJECT GUTENBERG EBOOK X ***")
    adv = str(tmp_path / "adv2")
    r = dispatch("add_source", {"advisor_dir": adv,
                 "url": "https://www.gutenberg.org/cache/epub/1/pg1.txt"})
    assert r["ok"]
    body = open(os.path.join(adv, "sources", r["source_file"]), encoding="utf-8").read()
    assert "Real body text" in body and "START OF THE PROJECT GUTENBERG" not in body  # boilerplate срезан


def test_add_source_rejects_non_pd_host_without_license(tmp_path):
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a3"),
                 "url": "https://example.com/some-copyrighted-book.txt"})
    assert "error" in r and "PD" in r["error"]


def test_add_source_blocks_ssrf_even_with_license(tmp_path):
    # license НЕ должен открывать egress: слоёный гард режет внутренний адрес независимо.
    # http-loopback теперь режется ещё РАНЬШЕ — https-only слоем (до DNS), тоже fail-closed:
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a4"),
                 "url": "http://127.0.0.1:11434/api/tags", "license": "public-domain"})
    assert "error" in r and "http без шифрования" in r["error"]
    # https-loopback проходит слой схемы и обязан упереться в SSRF-гард (лицензия не помогает):
    r2 = dispatch("add_source", {"advisor_dir": str(tmp_path / "a4"),
                  "url": "https://127.0.0.1:11434/api/tags", "license": "public-domain"})
    assert "error" in r2 and "SSRF" in r2["error"]          # loopback заблокирован, лицензия не помогла


def test_add_source_blocks_path_traversal(tmp_path):
    r = dispatch("add_source", {"advisor_dir": str(tmp_path / "a5"),
                 "path": "../../../../../../etc/passwd"})
    assert "error" in r and ("traversal" in r["error"].lower() or "вне корня" in r["error"])


def test_ssrf_check_passes_public_blocks_private(monkeypatch):
    import collect_common as cc
    monkeypatch.setattr(
        cc.socket,
        "getaddrinfo",
        lambda host, port, **_kwargs: [
            (None, None, None, None, (("127.0.0.1" if host == "127.0.0.1"
                                        else "93.184.216.34"), port))
        ],
    )
    assert cc.ssrf_check("https://www.gutenberg.org/cache/epub/1/pg1.txt") is None  # публичный → ок
    assert "SSRF" not in (cc.ssrf_check("ftp://x/y") or "")    # схема режется отдельно
    assert cc.ssrf_check("http://127.0.0.1/") and "127.0.0.1" in cc.ssrf_check("http://127.0.0.1/")
    assert cc.ssrf_check("file:///etc/passwd")                 # не-web схема → ошибка


def test_ollama_install_hint_is_platform_aware(monkeypatch):
    import setup_full, mcp_server
    monkeypatch.setattr(setup_full, "_norm_platform", lambda p: "windows")
    assert "ollama.com/download" in mcp_server._ollama_install_hint()   # не захардкожен Mac
    assert set(setup_full.INSTALL_HINTS) >= {"darwin", "linux", "windows"}


def test_add_source_provenance_header_not_citable(tmp_path):
    # P0: provenance-хедер `# SOURCE/# FETCHED/# LICENSE` не должен попадать в корпус/цитаты
    adv = str(tmp_path / "adv-hdr")
    dispatch("add_source", {"advisor_dir": adv, "basename": "canon", "tier": "P1",
             "text": "All warfare is based on deception, the canon repeats."})
    from corpusbuild import pipeline, paths
    pipeline.build(adv)
    corpus = open(paths.corpus_path(adv), encoding="utf-8").read()
    assert "# SOURCE" not in corpus and "FETCHED" not in corpus and "LICENSE" not in corpus
    # тело — по-прежнему 🔵, метаданные источника — нет
    assert dispatch("fidelity_check", {"quote": "All warfare is based on deception",
                                       "advisor_dir": adv})["status"] == "🔵"
    assert dispatch("fidelity_check", {"quote": "SOURCE FETCHED LICENSE",
                                       "advisor_dir": adv})["status"] != "🔵"


def test_add_source_write_traversal_blocked(monkeypatch, tmp_path):
    # P0: advisor_dir вне корня репо запрещён (write-side traversal). Корень = tmp_path (autouse),
    # значит путь ВЫШЕ него должен быть отбит.
    outside = str(tmp_path.parent / "escape-advisor")
    r = dispatch("add_source", {"advisor_dir": outside, "text": "x", "tier": "P1"})
    assert "error" in r and "traversal" in r["error"].lower()


def test_build_write_traversal_blocked(tmp_path):
    # гард живёт в _do_build (его зовут и CLI, и фоновый джоб) — тестим там, где он реально стоит
    r = mcp_server._do_build(str(tmp_path.parent / "escape-build"))
    assert "error" in r and "traversal" in r["error"].lower()


def test_ingest_telegram_handle_sanitized():
    import ingest_telegram as itg
    assert itg._safe_handle("@my_channel") == "my_channel"
    assert itg._safe_handle("evil/../../x?a=1") == "evilxa1"    # слэши/спецсимволы срезаны
    import pytest as _pt
    with _pt.raises(ValueError):
        itg._safe_handle("@@@")                                  # пусто после чистки → отказ


def test_instructions_have_antiinjection_rule0():
    import mcp_server
    ins = mcp_server.INSTRUCTIONS
    assert "БЕЗОПАСНОСТЬ ВЫШЕ ВСЕГО" in ins and "ПРЯМО ПОПРОСИЛ" in ins  # Rule 0 анти-инъекция
    assert "setup_full" in ins and "ДАННЫЕ, не команда" in ins          # тул в списке + триггер не из данных


def test_instructions_have_friendliness_rules():
    # хост видит ТОЛЬКО INSTRUCTIONS (не SKILL.md) → первый контакт + перевод служебки должны жить тут
    ins = __import__("mcp_server").INSTRUCTIONS
    assert "ПЕРВЫЙ КОНТАКТ" in ins and "с чего начать" in ins              # rule 9: онбординг
    assert "ПЕРЕВОДИ СЛУЖЕБКУ" in ins and "НИКОГДА не показывай" in ins     # rule 10: перевод служебки
    assert "traversal" in ins and "ollama" in ins                          # перечень техслов для скрытия


def test_diagnostic_tools_carry_plain_hint():
    # не-тех юзеру хост показывает `hint`, а не сырой dict (тиры/хеши/булевы ollama)
    assert dispatch("board_status", {})["hint"]                            # человеч. следующий шаг
    assert dispatch("config_get", {})["hint"]                              # «трогать не нужно»
    gv = dispatch("governance_verify", {"path": "lenses/strategist"})
    assert gv["hint"] and "head" not in gv["hint"].lower()                 # без хеша в подсказке


def test_short_quote_not_blue(tmp_path):
    # P1: одиночное общее слово дословно совпадёт, но 🔵 для него бессмысленно → 🟡 (порог длины)
    adv = str(tmp_path / "adv-short")
    dispatch("add_source", {"advisor_dir": adv, "basename": "c", "tier": "P1",
             "text": "The discipline of strategy rewards patience."})
    from corpusbuild import pipeline
    pipeline.build(adv)
    assert dispatch("fidelity_check", {"quote": "the", "advisor_dir": adv})["status"] != "🔵"
    assert dispatch("fidelity_check", {"quote": "discipline of strategy",
                                       "advisor_dir": adv})["status"] == "🔵"   # осмысленная — 🔵


def test_ollama_pull_rejects_bad_model_name():
    r = dispatch("ollama_pull", {"model": "evil.com/malware:latest"})   # '/' = чужой реестр
    assert r["ok"] is False and "недопустим" in r["error"]


def test_build_lens_slug_traversal_contained(tmp_path):
    # slug host-supplied: путь-обход через slug должен быть отбит/санитизирован, не писать вне корня
    r = dispatch("build_lens", {"name": "pwn", "ground_text": "All warfare is based on deception.",
                 "slug": "../../../../../../private/tmp/PWNED-lens"})
    if "error" in r:
        assert "traversal" in r["error"].lower()
    else:
        rp = os.path.realpath(r["advisor_dir"])
        assert rp.startswith(os.path.realpath(str(tmp_path)) + os.sep)   # внутри корня (tmp)
        assert not os.path.exists("/private/tmp/PWNED-lens")             # наружу не написалось


def test_resolve_under_root_edges(monkeypatch, tmp_path):
    import mcp_server
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    ok, err = mcp_server._resolve_under_root(str(tmp_path / "sub" / "x"))
    assert err is None and ok.startswith(os.path.realpath(str(tmp_path)))
    # sibling-prefix НЕ должен пройти (tmpEVIL vs tmp) — спасает `root + os.sep`
    _, err2 = mcp_server._resolve_under_root(str(tmp_path) + "EVIL")
    assert err2 and "traversal" in err2["error"].lower()


def test_ingest_out_path_env_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path=".env")
    assert "error" in out
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=1\n"

def test_ingest_out_path_code_overwrite_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "mcp_server.py").write_text("# code\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path="scripts/mcp_server.py")
    assert "error" in out

def test_ingest_out_path_existing_file_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    d = tmp_path / "principis_corpus"
    d.mkdir()
    (d / "x.jsonl").write_text("{}\n", encoding="utf-8")
    out = mcp_server._do_ingest("somehandle", out_path="principis_corpus/x.jsonl")
    assert "error" in out


def test_default_ingest_destination_uses_suffix_without_overwriting(tmp_path):
    """Повторный default ingest выбирает telegram-2.jsonl, а не перезаписывает историю."""
    import lifecycle
    corpus = tmp_path / "principis_corpus"
    corpus.mkdir()
    (corpus / "telegram.jsonl").write_text("old\n", encoding="utf-8")
    destination, error = lifecycle.prepare_ingest_destination(root=str(tmp_path))
    assert error is None and destination == str(corpus / "telegram-2.jsonl")


def test_embed_batch_rejects_count_mismatch(monkeypatch):
    pytest.importorskip("numpy")   # H8: tier_full тянет numpy транзитивно → SKIP без numpy
    import tier_full
    class _Resp:
        def __init__(self, p): self._p = p
        def read(self): return self._p
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(tier_full.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(json.dumps({"embeddings": [[0.1, 0.2]]}).encode()))
    import pytest as _pt
    with _pt.raises(RuntimeError):
        tier_full.embed_batch(["a", "b"])              # 1 вектор на 2 входа → ошибка, не молча
    assert tier_full.embed_batch([]) == []             # пустой вход → []


def test_embed_batch_happy_path(monkeypatch):
    pytest.importorskip("numpy")   # H8: tier_full тянет numpy транзитивно → SKIP без numpy
    import tier_full
    class _Resp:
        def __init__(self, p): self._p = p
        def read(self): return self._p
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(tier_full.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(json.dumps({"embeddings": [[0.1, 0.2], [0.3, 0.4]]}).encode()))
    v = tier_full.embed_batch(["one", "two"])
    assert v == [[0.1, 0.2], [0.3, 0.4]]               # вернул по вектору на вход


def test_fetch_channel_html_routes_through_guarded_fetch(monkeypatch):
    # P0-4 регрессия-пин: telegram идёт через collect_common.fetch (SSRF-гард), handle санитизирован
    import ingest_telegram as itg, collect_common as cc
    seen = {}
    monkeypatch.setattr(cc, "fetch", lambda url, timeout=20: seen.setdefault("url", url) or "<html>")
    itg.fetch_channel_html("@my/evil..channel")
    assert seen["url"] == "https://t.me/s/myevilchannel"   # host фиксирован, спецсимволы срезаны


def test_lifecycle_tools_registered():
    names = {t["name"] for t in list_tools()}
    assert {"config_get", "config_set", "ollama_status", "ollama_ensure", "ollama_pull",
            "add_source"} <= names


def test_add_source_text_with_apparatus_auto_tiers(tmp_path):
    body = ("Translator intro about Wellington and Waterloo.\n" * 6 +
            "I. LAYING PLANS\n" +
            "War is based on deception. [Tu Mu: deceive the foe.]\n" * 4 +
            "APPENDIX\nbibliography\n")
    r = dispatch("add_source", {"advisor_dir": "advisors/x-apparatus",
                                "text": body, "basename": "book", "tier": "P1"})
    assert r["ok"] and r["mode"] == "tier"
    assert r["hint"] and "🔵" in r["hint"] and "🟢" in r["hint"]
    assert any(a["mode"] == "clean" for a in r["adjustments"])
    man = json.load(open(os.path.join(r["advisor_dir"], "sources", "manifest.json")))
    entry = next(v for k, v in man.items() if k.startswith("book"))
    assert entry["apparatus"]["mode"] == "tier"


def test_instructions_have_apparatus_rule():
    ins = __import__("mcp_server").INSTRUCTIONS
    assert "АППАРАТ" in ins or "аппарат" in ins
    assert "🔵 автор" in ins or ("🔵" in ins and "🟢" in ins and "толков" in ins.lower())
    assert "не как обязательный выбор" in ins or "не блокируй" in ins.lower()


def test_add_source_clean_mode_writes_clean_file(tmp_path):
    body = "intro\nI. LAYING PLANS\nWar is deception. [Tu Mu: yes.]\nAPPENDIX\nx\n"
    r = dispatch("add_source", {"advisor_dir": "advisors/x-clean", "text": body,
                                "basename": "book", "tier": "P1", "mode": "clean",
                                "front_until": "I. LAYING PLANS", "back_from": "APPENDIX"})
    assert r["ok"] and r["mode"] == "clean"
    sources = os.path.join(r["advisor_dir"], "sources")
    files = os.listdir(sources)
    assert any(f.endswith(".clean.txt") for f in files)
    # сырой backup лежит в подкаталоге originals/ → pipeline его НЕ ингестит
    assert os.path.isfile(os.path.join(sources, "originals", "book.txt"))
    from corpusbuild import pipeline, paths
    pipeline.build(r["advisor_dir"])
    corpus = [json.loads(l) for l in open(paths.corpus_path(r["advisor_dir"]))]
    assert corpus and all(c["tier"] == "P1" for c in corpus)        # только чистый автор, без A-мусора
    assert not any("Tu Mu" in c["text"] for c in corpus)            # аппарат исчез из корпуса


def test_add_source_clean_mode_preserves_colliding_source_pairs(tmp_path):
    """Два clean-источника с одним basename получают согласованные суффиксы, без перезаписи."""
    body = "I. LAYING PLANS\nWar is deception.\nAPPENDIX\nx\n"
    first = dispatch("add_source", {"advisor_dir": "advisors/x-clean-pair", "text": body,
                                    "basename": "book", "tier": "P1", "mode": "clean",
                                    "front_until": "I. LAYING PLANS", "back_from": "APPENDIX"})
    second = dispatch("add_source", {"advisor_dir": "advisors/x-clean-pair", "text": body + "two",
                                     "basename": "book", "tier": "P1", "mode": "clean",
                                     "front_until": "I. LAYING PLANS", "back_from": "APPENDIX"})
    assert [first["source_file"], second["source_file"]] == ["book.clean.txt", "book-2.clean.txt"]
    sources = os.path.join(first["advisor_dir"], "sources")
    assert os.path.isfile(os.path.join(sources, "originals", "book.txt"))
    assert os.path.isfile(os.path.join(sources, "originals", "book-2.txt"))


def test_add_source_env_path_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-x\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path=".env")

def test_load_source_pem_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "server.pem").write_text("-----BEGIN\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path="server.pem")

def test_load_source_regular_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "book.txt").write_text("some public domain text\n", encoding="utf-8")
    text, hint, prov, lic = mcp_server._load_source_text(path="book.txt")
    assert "public domain" in text


def test_load_source_env_example_template_allowed(tmp_path, monkeypatch):
    # задокументированное исключение denylist: .env.example/.sample/.template — публичные
    # шаблоны, не секреты → читаемы (без исключения regex ловил бы их как .env*).
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    text, hint, prov, lic = mcp_server._load_source_text(path=".env.example")
    assert "OPENROUTER_API_KEY" in text


def test_load_source_git_config_rejected(tmp_path, monkeypatch):
    # M1-follow: файлы ВНУТРИ .git/ запрещены (в .git/config remote-URL часто с токеном) —
    # старый regex был заякорен на $ и ловил только хвост '.git', пропуская '.git/config'.
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    gitdir = tmp_path / ".git"
    gitdir.mkdir()
    (gitdir / "config").write_text("[remote]\n\turl = https://tok@example/x.git\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path=".git/config")


def test_load_source_pem_bak_rejected(tmp_path, monkeypatch):
    # M1-follow: бэкап ключа server.pem.bak — старый regex требовал .pem строго в КОНЦЕ пути.
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / "server.pem.bak").write_text("-----BEGIN\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_server._load_source_text(path="server.pem.bak")


def test_load_source_gitignore_ok(tmp_path, monkeypatch):
    # позитивный контроль: .gitignore — НЕ VCS-метаданные и не секрет, читается нормально
    # (расширение .git-правила на весь сегмент не должно задевать имена с префиксом .git*).
    monkeypatch.setattr(mcp_server, "_root", lambda: str(tmp_path))
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    text, hint, prov, lic = mcp_server._load_source_text(path=".gitignore")
    assert "*.pyc" in text


# ── Kimi LOW: голое имя при ЗАПИСИ вкладывается в advisors/<name>, не rogue <root>/<name> ──
# (симметрия с read-side _resolve_advisor_corpus: голое имя работает и на чтении, и на записи)

def test_add_source_bare_name_lands_under_advisors_not_root(tmp_path):
    # голое имя (без разделителя) → advisors/<name>, НЕ <root>/<name> (rogue в корне репо)
    r = dispatch("add_source", {"advisor_dir": "test-sage", "basename": "canon", "tier": "P1",
                 "text": "All warfare is based on deception, the canon repeats."})
    assert r["ok"]
    landed = os.path.realpath(r["advisor_dir"])
    assert landed == os.path.realpath(str(tmp_path / "advisors" / "test-sage"))
    assert not os.path.isdir(str(tmp_path / "test-sage"))                 # rogue-каталог не создан
    assert os.path.isfile(os.path.join(landed, "sources", "manifest.json"))


def test_add_source_path_form_unchanged(tmp_path):
    # путь-форма ('advisors/x') резолвится как раньше — без двойного вложения advisors/advisors/x
    r = dispatch("add_source", {"advisor_dir": "advisors/test-path-sage", "basename": "c",
                 "tier": "P1", "text": "War is based on deception here, the source says."})
    assert r["ok"]
    assert os.path.realpath(r["advisor_dir"]) == os.path.realpath(
        str(tmp_path / "advisors" / "test-path-sage"))


def test_add_source_bare_name_targets_existing_advisor(tmp_path):
    # голое имя УЖЕ существующего советника → целимся в него, не плодим дубль
    existing = tmp_path / "advisors" / "test-existing"
    (existing / "sources").mkdir(parents=True)
    r = dispatch("add_source", {"advisor_dir": "test-existing", "basename": "c", "tier": "P1",
                 "text": "Strategy rewards patience and disciplined study."})
    assert r["ok"]
    assert os.path.realpath(r["advisor_dir"]) == os.path.realpath(str(existing))


def test_add_source_dotdot_still_traversal_blocked(tmp_path):
    # '..' — НЕ голое имя (есть смысл обхода) → путь-форма → write-traversal-гард отбивает
    r = dispatch("add_source", {"advisor_dir": "..", "text": "x", "tier": "P1"})
    assert "error" in r


def test_resolve_advisor_write_bare_vs_path(tmp_path):
    # ядро фикса: голое имя → advisors/<name>; путь-форма → как _resolve_under_root
    d1, e1 = mcp_server._resolve_advisor_write("test-build-sage")
    assert e1 is None
    assert os.path.realpath(d1) == os.path.realpath(str(tmp_path / "advisors" / "test-build-sage"))
    d2, e2 = mcp_server._resolve_advisor_write("advisors/test-build-sage")
    assert e2 is None and os.path.realpath(d2) == os.path.realpath(d1)   # обе формы → один каталог


def test_build_advisor_dedup_key_matches_write_dir(tmp_path):
    # дедуп-ключ фонового джоба и реальный каталог сборки должны совпасть (голое имя)
    key, err = mcp_server._resolve_advisor_write("test-sage")
    build_dir, berr = mcp_server._resolve_advisor_write("test-sage")
    assert err is None and berr is None and key == build_dir


# ── Kimi LOW: validate_manifest различает «провалидировано» и «проверять было нечего/нельзя» ──

def test_validate_manifest_real_validation_marks_checked(tmp_path):
    dispatch("add_source", {"advisor_dir": "advisors/test-vm", "basename": "c", "tier": "P1",
             "text": "War is based on deception, the canon says plainly."})
    out = mcp_server._validate_manifest("advisors/test-vm")
    assert out["checked"] is True and "ok" in out            # реальная валидация → checked:true


def test_validate_manifest_no_manifest_is_unchecked_but_safe(tmp_path):
    (tmp_path / "advisors" / "test-nm" / "sources").mkdir(parents=True)   # dir есть, manifest нет
    out = mcp_server._validate_manifest("advisors/test-nm")
    assert out["checked"] is False and out["ok"] is True and out["problems"] == []


def test_validate_manifest_traversal_not_ok_and_unchecked(tmp_path):
    out = mcp_server._validate_manifest("../outside")
    assert out["checked"] is False and out["ok"] is False and out["problems"] == []
