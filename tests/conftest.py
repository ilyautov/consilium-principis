"""Сьютовый пин судьи релевантности на "ollama" (single-phase, сервер судит).

§2.1 moat-v2 ввёл двухфазный host-протокол: при judge_backend=host cite возвращает
judgment_request вместо готовых цитат. В CI-среде (без ollama, без API-ключа) auto
резолвился бы в host — и ВЕСЬ легаси-контракт single-phase cite (early-exit, 🔵-приоритет,
fail-closed) перестал бы быть покрыт. Пин фиксирует легаси-режим как дефолт сьюта;
host-протокол и сама резолюция тестируются в своих файлах, переопределяя/снимая env
(monkeypatch function-scoped — пин восстанавливается после каждого теста).
"""
import pytest


@pytest.fixture(autouse=True)
def _pin_judge_backend_single_phase(monkeypatch):
    monkeypatch.setenv("CONSILIUM_JUDGE_BACKEND", "ollama")
