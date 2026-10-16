"""Подписочные бэкенды LLM: Claude Code / Codex / Kimi Code CLI в неинтерактивном режиме.

Зачем. У массового юзера нет API-ключа и нет ollama с большой чат-моделью, зато есть ПОДПИСКИ
(Claude, ChatGPT/Codex, Kimi) и их CLI. Этот модуль превращает каждую подписку в «мозг»:
  • независимый судья релевантности (judge_backend="api" при LLM_BACKEND=claude|codex|kimi);
  • исполнитель федерации (federation/sub_worker.py) — разные модели играют советников,
    что и есть честное разнообразие совета (docs/FEDERATION.md, северная звезда).

Рамка — та же, что у федерации: personal / attended / себе-в-пользу. Вызывает ТОЛЬКО сам юзер на
СВОЕЙ машине под СВОИМ логином CLI; мы не храним и не читаем токены (auth целиком у CLI), не пулим
аккаунты и не отдаём подписку бэкендом чужому сервису.

Изоляция вызова (каждый пункт закрывает конкретный риск):
  • argv-список, shell=False — промпт НИКОГДА не интерполируется в shell;
  • cwd = свежий пустой temp-каталог — агент CLI не видит ни репо, ни advisors/, ни home-файлов;
  • инструменты выключены там, где CLI это умеет: claude `--tools ""`, codex `--sandbox read-only`;
    Kimi в `-p` без `--yolo/--auto` действия не одобряет, плюс промпт явно запрещает тулы;
  • MCP выключен: claude `--strict-mcp-config` (без --mcp-config = ноль серверов), codex
    `-c mcp_servers={}`. Иначе CLI поднял бы НАШ же mcp_server → рекурсия совета в самого себя;
  • без сохранения сессий: claude `--no-session-persistence`, codex `--ephemeral`.
  `--bare` у claude НЕ используем: он пропускает чтение keychain → ломает вход по подписке.

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

# Env-оверрайд модели на бэкенд: CONSILIUM_CLAUDE_MODEL / CONSILIUM_CODEX_MODEL / CONSILIUM_KIMI_MODEL.
# Пусто → дефолт самого CLI (то, что юзер выбрал в своей подписке).
_MODEL_ENV = {b: "CONSILIUM_%s_MODEL" % b.upper() for b in BACKENDS}

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
        cand = os.path.join(home, "bin", "kimi")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def available(backend):
    """CLI установлен? Без сетевого пробинга и без трат квоты: живость логина проверяет probe()."""
    return binary(backend) is not None


def detect():
    """Список установленных подписочных CLI в каноническом порядке."""
    return [b for b in BACKENDS if available(b)]


def model_for(backend, model=None):
    """Явная модель → env-оверрайд → None (дефолт CLI)."""
    return model or os.environ.get(_MODEL_ENV.get(backend, ""), "").strip() or None


def _argv(backend, exe, model, prompt, out_file):
    """argv + stdin для бэкенда. Промпт идёт через stdin везде, где CLI это умеет."""
    if backend == "claude":
        argv = [exe, "-p", "--output-format", "json", "--tools", "",
                "--strict-mcp-config", "--no-session-persistence"]
        if model:
            argv += ["--model", model]
        return argv, prompt
    if backend == "codex":
        argv = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                "-c", "mcp_servers={}", "-o", out_file]
        if model:
            argv += ["-m", model]
        return argv + ["-"], prompt
    # kimi: промпт только аргументом -p. Ведущий «-» commander принял бы за флаг → экранируем пробелом.
    p = (" " + prompt) if prompt.startswith("-") else prompt
    argv = [exe, "-p", p, "--output-format", "text"]
    if model:
        argv += ["-m", model]
    return argv, None


def _run(argv, stdin_text, cwd, timeout):
    """ЕДИНСТВЕННАЯ точка запуска процесса (монкипатчится в тестах). → (returncode, stdout, stderr)."""
    r = subprocess.run(argv, input=stdin_text, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, shell=False)
    return r.returncode, r.stdout or "", r.stderr or ""


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
    exe = binary(backend)
    if not exe:
        raise CLIBackendError(backend, "missing", "CLI не установлен")
    if not isinstance(prompt, str) or not prompt.strip():
        raise CLIBackendError(backend, "empty", "пустой промпт")
    full = (_NO_TOOLS_PREAMBLE + prompt) if no_tools else prompt
    with tempfile.TemporaryDirectory(prefix="consilium-cli-") as cwd:
        out_file = os.path.join(cwd, "last-message.txt")
        argv, stdin_text = _argv(backend, exe, model_for(backend, model), full, out_file)
        try:
            code, out, err = _run(argv, stdin_text, cwd, timeout)
        except subprocess.TimeoutExpired:
            raise CLIBackendError(backend, "timeout", "нет ответа за %d с" % timeout)
        except OSError as e:
            raise CLIBackendError(backend, "missing", str(e))
        if backend == "codex" and code == 0:
            try:
                with open(out_file, encoding="utf-8") as fh:
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
