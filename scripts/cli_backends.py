"""Подписочные бэкенды LLM: Claude Code / Codex / Kimi Code CLI в неинтерактивном режиме.

Зачем. У массового юзера нет API-ключа и нет ollama с большой чат-моделью, зато есть ПОДПИСКИ
(Claude, ChatGPT/Codex, Kimi) и их CLI. Этот модуль превращает каждую подписку в «мозг»:
  • независимый судья релевантности (judge_backend="api" при LLM_BACKEND=claude|codex; kimi —
    только по явному CONSILIUM_ALLOW_KIMI_JUDGE=1, см. JUDGE_SAFE);
  • исполнитель федерации (federation/sub_worker.py) — разные модели играют советников,
    что и есть честное разнообразие совета (docs/FEDERATION.md, северная звезда).

Рамка — та же, что у федерации: personal / attended / себе-в-пользу. Вызывает ТОЛЬКО сам юзер на
СВОЕЙ машине под СВОИМ логином CLI; мы не храним и не читаем токены (auth целиком у CLI), не пулим
аккаунты и не отдаём подписку бэкендом чужому сервису.

Изоляция вызова (каждый пункт закрывает конкретный риск):
  • argv-список, shell=False — промпт НИКОГДА не интерполируется в shell;
  • cwd = свежий пустой temp-каталог — агент CLI не видит ни репо, ни advisors/, ни home-файлов;
  • инструменты выключены там, где CLI это умеет: claude `--tools ""`, codex `--sandbox read-only`;
    Kimi — `-p` без `--yolo/--auto` плюс `--plan` (режим планирования: без правок и команд), и
    промпт явно запрещает тулы. Текст корпуса в промпте мог бы prompt-инъекцией толкнуть агента
    к тулам — plan-режим это второй слой поверх запрета в промпте;
  • MCP выключен: claude `--strict-mcp-config` (без --mcp-config = ноль серверов), codex
    `-c mcp_servers={}`. Иначе CLI поднял бы НАШ же mcp_server → рекурсия совета в самого себя.
    Страховка для всех трёх (и для Kimi, у которого такого флага нет): в env ребёнка
    CONSILIUM_NO_MCP=1 — mcp_server, поднятый из-под CLI, сразу выходит;
  • env ребёнка — белый список (system/прокси/CA + собственные auth-переменные CLI): НЕ получает
    OPENROUTER_API_KEY, GITHUB_TOKEN, пароли и прочие чужие секреты родителя;
  • без сохранения сессий: claude `--no-session-persistence`, codex `--ephemeral`.
  `--bare` у claude НЕ используем: он пропускает чтение keychain → ломает вход по подписке.
  • модель — белый список символов и ОДИН токен `--model=<v>`: имя не станет отдельным флагом CLI;
  • Windows: .cmd/.bat-шим НЕ запускаем (BatBadBut, CVE-2024-24576: аргументы идут через
    cmd.exe, его кавычки не совпадают с list2cmdline → промпт исполняется как команда);
  • таймаут убивает ВСЮ группу процессов: CLI порождают node/helper-внуков; subprocess.run убил бы
    только ребёнка, внук держит пайп → communicate висит вечно, квота горит в фоне.

Kimi принимает промпт только аргументом `-p` → промпт ВИДЕН в `ps` другим локальным юзерам машины
и упирается в лимит argv (KIMI_PROMPT_MAX). Claude/Codex читают промпт из stdin — не видны.

Ошибки fail-closed: ненулевой выход, таймаут, пустой ответ или ТЕКСТ ошибки при exit 0 (Kimi на
исчерпанной квоте печатает `error: … 403 …` и выходит с 0 — проверено 2026-10-13) → CLIBackendError.
Вызыватели (llm_local, судья, воркер) трактуют исключение как «бэкенд недоступен», а не как ответ.

Тесты не трогают реальные CLI: единственная точка запуска — `_run`, её монкипатчат.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

BACKENDS = ("claude", "codex", "kimi")
DEFAULT_TIMEOUT = 180

# Бэкенды, которым доверен путь СУДЬИ релевантности (llm_local.generate). Судья кормится сырым
# текстом корпуса (поверхность инъекций), а у Kimi нет жёсткого выключателя тулов — только
# plan-режим. Поэтому kimi в судьи только по явному CONSILIUM_ALLOW_KIMI_JUDGE=1.
JUDGE_SAFE = ("claude", "codex")

# Kimi: промпт в argv. Лимит командной строки Windows ~32К UTF-16, POSIX ARG_MAX больше, но длинный
# argv ещё и висит в `ps`. Длиннее — честный отказ, а не молчаливая обрезка вопроса.
KIMI_PROMPT_MAX = 60000

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$")

# Env-оверрайд модели на бэкенд: CONSILIUM_CLAUDE_MODEL / CONSILIUM_CODEX_MODEL / CONSILIUM_KIMI_MODEL.
# Пусто → дефолт самого CLI (то, что юзер выбрал в своей подписке).
_MODEL_ENV = {b: "CONSILIUM_%s_MODEL" % b.upper() for b in BACKENDS}

# Env ребёнка — БЕЛЫЙ список имён, а не копия окружения целиком. Почему не «копия минус секреты»:
# (1) агент CLI мог бы по prompt-инъекции из корпуса «прочитать» любой унаследованный секрет
# (OPENROUTER_API_KEY, GITHUB_TOKEN, пароли БД), а чёрный список по маске всегда что-то пропустит;
# (2) перебор os.environ целиком — HIGH-правило установочного сканера Hermes (tests/test_skillignore).
# Здесь: системное (PATH/HOME/локаль/temp, Windows-база), прокси и CA (корпоративные сети), и
# СОБСТВЕННЫЕ auth/config-переменные трёх CLI — без них вход по ключу/нестандартный home сломается.
# Нужна ещё переменная для CLI → добавь имя сюда (осознанно, по одному).
_ENV_SYSTEM = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
    "LC_MESSAGES", "TERM", "TZ", "TMPDIR", "TEMP", "TMP",
    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA",
    "USERPROFILE", "USERNAME", "HOMEDRIVE", "HOMEPATH", "PROGRAMDATA", "PROGRAMFILES",
    "PROGRAMFILES(X86)", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "all_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
)
_ENV_CLI_AUTH = (
    # Claude Code
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_OAUTH_TOKEN",
    # Codex
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_HOME", "CODEX_API_KEY",
    # Kimi Code
    "KIMI_CODE_HOME", "KIMI_API_KEY", "KIMI_BASE_URL", "MOONSHOT_API_KEY", "MOONSHOT_BASE_URL",
)

# Строка-маркер ошибки в stdout при exit 0 (Kimi) и типовые сигналы исчерпанной квоты/логина.
_ERROR_LINE = re.compile(r"^\s*error:", re.IGNORECASE | re.MULTILINE)
_QUOTA_HINT = re.compile(r"usage limit|quota|rate.?limit|\b403\b|\b429\b", re.IGNORECASE)
_AUTH_HINT = re.compile(r"not logged in|login required|unauthori[sz]ed|\b401\b|please (log|sign) ?in",
                        re.IGNORECASE)

_NO_TOOLS_PREAMBLE = ("Отвечай одним текстовым ответом. Не используй инструменты, не читай и не "
                      "пиши файлы, не запускай команды.\n\n")


class CLIBackendError(RuntimeError):
    """Подписочный бэкенд не дал ответа. kind: missing|timeout|quota|auth|exit|empty|parse."""

    def __init__(self, backend, kind, detail=""):
        self.backend, self.kind, self.detail = backend, kind, detail
        super().__init__("%s: %s%s" % (backend, kind, (" — " + detail) if detail else ""))


def binary(backend):
    """Путь к бинарю CLI или None. Kimi Code ставится в ~/.kimi-code/bin — его нет в PATH у части юзеров."""
    if backend not in BACKENDS:
        return None
    found = shutil.which(backend)
    if found:
        return found
    if backend == "kimi":
        home = os.environ.get("KIMI_CODE_HOME") or os.path.join(os.path.expanduser("~"), ".kimi-code")
        names = ("kimi.exe", "kimi") if os.name == "nt" else ("kimi",)
        for name in names:
            cand = os.path.join(home, "bin", name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def _is_shim(path):
    return str(path).lower().endswith((".cmd", ".bat"))


def safe_exe(backend, path):
    """Путь, который МОЖНО запускать с произвольным промптом, или CLIBackendError(missing).

    Почему: на Windows npm ставит CLI .cmd-шимом; CreateProcess исполняет его через cmd.exe, чьи
    правила кавычек не совпадают с list2cmdline → `"` и `&` в промпте/модели становятся командой
    (BatBadBut). Fail-closed: шим берём, только если рядом лежит настоящий .exe с тем же именем."""
    if not path or not _is_shim(path):
        return path
    exe = os.path.splitext(path)[0] + ".exe"
    if os.path.isfile(exe):
        return exe
    raise CLIBackendError(backend, "missing",
                          "найден только шим %s — .cmd/.bat запускается через cmd.exe и небезопасен "
                          "для произвольного промпта (BatBadBut); поставь нативный .exe CLI"
                          % os.path.basename(str(path)))


def available(backend):
    """CLI установлен и запускаем безопасно? Без сетевого пробинга и без трат квоты: живость
    логина проверяет probe()."""
    path = binary(backend)
    if path is None:
        return False
    try:
        safe_exe(backend, path)
    except CLIBackendError:
        return False
    return True


def detect():
    """Список установленных подписочных CLI в каноническом порядке."""
    return [b for b in BACKENDS if available(b)]


def valid_model(value):
    """Имя модели из белого списка (opus, gpt-5.1, kimi-k2:latest, org/model)? Белый, а не чёрный
    список: имя уходит в argv чужого CLI и в командную строку фонового воркера."""
    return isinstance(value, str) and bool(_MODEL_RE.match(value))


def model_for(backend, model=None):
    """Явная модель → env-оверрайд → None (дефолт CLI).
    Явная невалидная модель → CLIBackendError(parse): юзер просил конкретную, молча подменять её
    дефолтом нельзя. Невалидный env-оверрайд игнорируется (дефолт CLI): это фон, не запрос."""
    if model is not None and model != "":
        if not valid_model(model):
            raise CLIBackendError(backend, "parse", "недопустимое имя модели %r" % (str(model)[:80],))
        return model
    env = os.environ.get(_MODEL_ENV.get(backend, ""), "").strip()
    return env if valid_model(env) else None


def child_env(base=None):
    """Env для CLI-ребёнка: только белый список имён + CONSILIUM_NO_MCP=1 (гард рекурсии
    mcp_server). base (тесты) — словарь-источник вместо окружения процесса."""
    get = base.get if base is not None else (lambda k: os.environ.get(k))
    env = {}
    for k in _ENV_SYSTEM + _ENV_CLI_AUTH:
        v = get(k)
        if v is not None:
            env[k] = v
    env["CONSILIUM_NO_MCP"] = "1"
    return env


def _argv(backend, exe, model, prompt, out_file):
    """argv + stdin для бэкенда. Промпт идёт через stdin везде, где CLI это умеет.
    Модель — одним токеном `--model=<v>` (clap у codex, commander у claude/kimi принимают `=`)."""
    if backend == "claude":
        argv = [exe, "-p", "--output-format", "json", "--tools", "",
                "--strict-mcp-config", "--no-session-persistence"]
        if model:
            argv.append("--model=" + model)
        return argv, prompt
    if backend == "codex":
        argv = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                "-c", "mcp_servers={}", "-o", out_file]
        if model:
            argv.append("--model=" + model)
        return argv + ["-"], prompt
    # kimi: промпт только аргументом -p → виден в `ps`, ограничен длиной (KIMI_PROMPT_MAX).
    # Ведущий «-» commander принял бы за флаг → экранируем пробелом.
    if len(prompt) > KIMI_PROMPT_MAX:
        raise CLIBackendError(backend, "parse", "промпт слишком длинный для argv kimi (%d > %d символов)"
                              % (len(prompt), KIMI_PROMPT_MAX))
    p = (" " + prompt) if prompt.startswith("-") else prompt
    argv = [exe, "-p", p, "--output-format", "text", "--plan"]
    if model:
        argv.append("--model=" + model)
    return argv, None


def _kill_tree(proc):
    """Убить процесс ВМЕСТЕ с потомками (своя группа/сессия). Ошибки глотаем: мог выйти сам."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()                     # группы уже нет, а сам процесс жив — добиваем напрямую
    except OSError:
        pass


def _spawn_and_wait(argv, stdin_text, cwd, timeout, env=None):
    """Реальный запуск в СВОЕЙ группе процессов: таймаут убивает и внуков (node-хелперы CLI).
    После kill даём 5 с дочитать пайпы; не успели — всё равно TimeoutExpired (не виснем)."""
    kw = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
          "cwd": cwd, "env": env, "shell": False, "text": True, "encoding": "utf-8",
          "errors": "replace"}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen(argv, **kw)
    try:
        out, err = proc.communicate(input=stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        raise subprocess.TimeoutExpired(argv, timeout)
    except BaseException:
        _kill_tree(proc)        # KeyboardInterrupt и пр.: не оставляем сирот
        raise
    return proc.returncode, out or "", err or ""


def _run(argv, stdin_text, cwd, timeout, env=None):
    """ЕДИНСТВЕННАЯ точка запуска процесса (монкипатчится в тестах). → (returncode, stdout, stderr)."""
    return _spawn_and_wait(argv, stdin_text, cwd, timeout, env)


def _tail(s, n=300):
    s = (s or "").strip()
    return s[-n:]


def _classify_failure(backend, text):
    if _QUOTA_HINT.search(text):
        return CLIBackendError(backend, "quota", "лимит подписки исчерпан: " + _tail(text, 200))
    if _AUTH_HINT.search(text):
        return CLIBackendError(backend, "auth", "CLI не залогинен: " + _tail(text, 200))
    return None


def _parse_claude(stdout):
    try:
        obj = json.loads(stdout)
    except ValueError:
        raise CLIBackendError("claude", "parse", "ожидался JSON от --output-format json")
    if not isinstance(obj, dict):
        raise CLIBackendError("claude", "parse", "JSON не объект")
    if obj.get("is_error"):
        text = str(obj.get("result", ""))
        raise _classify_failure("claude", text) or CLIBackendError("claude", "exit", _tail(text))
    return str(obj.get("result", ""))


def generate(prompt, backend, model=None, timeout=DEFAULT_TIMEOUT, no_tools=True):
    """Prompt → ответ модели через подписочный CLI. Любой сбой → CLIBackendError (fail-closed)."""
    if backend not in BACKENDS:
        raise CLIBackendError(str(backend), "missing", "неизвестный бэкенд; есть: " + ", ".join(BACKENDS))
    exe = safe_exe(backend, binary(backend))
    if not exe:
        raise CLIBackendError(backend, "missing", "CLI не установлен")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CLIBackendError(backend, "empty", "пустой промпт")
    full = (_NO_TOOLS_PREAMBLE + prompt) if no_tools else prompt
    chosen = model_for(backend, model)
    with tempfile.TemporaryDirectory(prefix="consilium-cli-") as cwd:
        out_file = os.path.join(cwd, "last-message.txt")
        argv, stdin_text = _argv(backend, exe, chosen, full, out_file)
        try:
            code, out, err = _run(argv, stdin_text, cwd, timeout, child_env())
        except subprocess.TimeoutExpired:
            raise CLIBackendError(backend, "timeout", "нет ответа за %d с" % timeout)
        except OSError as e:
            raise CLIBackendError(backend, "missing", str(e))
        except AssertionError:
            raise           # гард тестов (conftest) обязан падать ГРОМКО, а не тонуть в fallback
        except Exception as e:
            # Неожиданное (ValueError из пайпов, сбой кодека…) — тоже «бэкенд не ответил»:
            # fail-closed, а не смерть потока воркера/судьи на голом исключении.
            raise CLIBackendError(backend, "exit", "сбой запуска: %s" % type(e).__name__)
        if backend == "codex" and code == 0:
            try:
                with open(out_file, encoding="utf-8", errors="replace") as fh:
                    out = fh.read()
            except OSError:
                out = ""
        if code != 0:
            raise (_classify_failure(backend, err + "\n" + out)
                   or CLIBackendError(backend, "exit", "код %d: %s" % (code, _tail(err or out))))
    if backend == "claude":
        out = _parse_claude(out)
    elif _ERROR_LINE.search(out) and len(out.strip()) < 2000:
        # Kimi: ошибка провайдера печатается в stdout при exit 0. Длинный осмысленный ответ, где
        # случайно встретилась строка «error:», ошибкой не считаем (порог длины).
        raise _classify_failure(backend, out) or CLIBackendError(backend, "exit", _tail(out))
    if not out.strip():
        raise CLIBackendError(backend, "empty", "пустой ответ")
    return out.strip()


def probe(backend, timeout=60):
    """Живой пробник: CLI установлен И подписка отвечает (тратит крошечный кусок квоты).
    → {"backend", "ok", "kind"?, "detail"?}. Для doctor/статуса, не для горячего пути."""
    try:
        generate("Ответь одним словом: ok", backend, timeout=timeout)
        return {"backend": backend, "ok": True}
    except CLIBackendError as e:
        return {"backend": backend, "ok": False, "kind": e.kind, "detail": e.detail}
