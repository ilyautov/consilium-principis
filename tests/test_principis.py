"""Загрузчик модели Принцепса — память о юзере + адаптация подачи + журнал решений."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from principis import load_principis, DEFAULT_MODE

SAMPLE = """---
name: Илья Утов
interface_mode: rigor      # rigor | support
owner: principis
---

# Принцепс

> преамбула

## Кто ты
строка про контекст.

## Журнал решений
- 2026-06-26 · форум: исход ⏳ pending
"""


def _mk(tmp, text):
    p = os.path.join(tmp, "principis.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def test_loads_frontmatter_and_strips_inline_comment():
    with tempfile.TemporaryDirectory() as t:
        r = load_principis(_mk(t, SAMPLE))
        assert r["ok"] is True
        assert r["interface_mode"] == "rigor"      # inline-комментарий "# rigor | support" срезан
        assert r["owner"] == "principis"
        assert r["fields"]["name"] == "Илья Утов"


def test_parses_sections():
    with tempfile.TemporaryDirectory() as t:
        r = load_principis(_mk(t, SAMPLE))
        assert "Кто ты" in r["sections"]
        assert "контекст" in r["sections"]["Кто ты"]
        assert "Журнал решений" in r["sections"]
        assert "pending" in r["sections"]["Журнал решений"]


def test_missing_file_fails_safe_to_rigor():
    with tempfile.TemporaryDirectory() as t:
        r = load_principis(os.path.join(t, "nope.md"))
        assert r["ok"] is False
        assert r["interface_mode"] == DEFAULT_MODE == "rigor"
        assert r["sections"] == {}


def test_invalid_mode_falls_back_to_rigor():
    with tempfile.TemporaryDirectory() as t:
        bad = SAMPLE.replace("interface_mode: rigor      # rigor | support", "interface_mode: clown")
        r = load_principis(_mk(t, bad))
        assert r["interface_mode"] == "rigor"      # неизвестный режим → fail-closed к строгому
