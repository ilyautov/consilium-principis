#!/usr/bin/env python3
"""Decisions-домен MCP-сервера: карта решения, Decision Card, петля исхода, calibrated consult.

Первый срез декомпозиции god-module mcp_server.py (H2, Task 5.4): handler'ы тулов
validate/run/save decision map, save/close decision card, prediction_calibration, петля
исхода (advisor_weights / pending_outcomes / loop_status), decision_record и
calibrated_consult_* плюс их приватные хелперы. Перенос ВЕРБАТИМ; mcp_server реэкспортирует
имена (фасад) — TOOLS-реестр, dispatch и тесты не тронуты.

Дизайн-решение по цикличности: mcp_server импортирует mcp_decisions (TOOLS-реестр) →
mcp_decisions НЕ может импортировать mcp_server на уровне модуля. Шаренные гарды/утилы
(_root / _resolve_under_root / _validate_slug / _unique_path_under_root) НЕ копируются —
единственная реализация остаётся в mcp_server (M11), здесь ленивые делегаты, читающие
атрибут модуля В МОМЕНТ ВЫЗОВА (вариант (а) брифа; DI-коллбэки lifecycle.py не подходят —
сигнатуры handler'ов запинены TOOLS-схемами). Побочный плюс: monkeypatch.setattr(mcp_server,
"_root", tmp) в тестах действует и на перенесённый код — контракт write-гарда сохранён.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from file_atomic import atomic_update_json, atomic_write_json, exclusive_file_lock


# ── Шаренные гарды mcp_server: ленивые делегаты (НЕ копии — единая реализация там) ──

def _root():
    from mcp_server import _root as _impl
    return _impl()


def _resolve_under_root(p):
    from mcp_server import _resolve_under_root as _impl
    return _impl(p)


def _validate_slug(slug):
    from mcp_server import _validate_slug as _impl
    return _impl(slug)


def _unique_path_under_root(base, ext):
    from mcp_server import _unique_path_under_root as _impl
    return _impl(base, ext)


# ── Петля исхода (U1): калибровка голосов совета по факту + сёрфейс висящих ⏳ ──

def _advisor_weights(records):
    from advisor_calibration import advisor_scores, vote_weights
    return {"scores": advisor_scores(records), "weights": vote_weights(records)}


def _pending_outcomes(journal_text):
    from outcome_loop import pending_from_journal
    return {"pending": pending_from_journal(journal_text)}


def _loop_status(ledger=None):
    """§4.3: без ledger (старт новой сессии — хосту его неоткуда взять) тул САМ читает
    существующие журналы (principis.md + advisors/*/relationship.md) и отдаёт висящие ⏳.
    Ноль висящих → тихий минимум без hint (не шумим, где юзер просто исследует).
    С ledger — прежний контракт (total/resolved/pending/accuracy) без изменений."""
    from outcome_loop import loop_status, pending_from_files
    if ledger is not None:
        return loop_status(ledger)
    pend = pending_from_files(_root())
    out = {"pending": pend, "count": len(pend)}
    if pend:
        out["hint"] = ("У юзера %d незакрыт(ых) решений(я) — исход ещё не зафиксирован. "
                       "МЯГКО и ОДИН РАЗ предложи вернуться: «как легло — сработало или нет?» "
                       "Ответил — обнови запись в её файле (source): строку ИСХОД ⏳ → ✅/❌ и "
                       "добавь «Одобрено: да/нет». Отказался/молчит — не дави." % len(pend))
        # Ф4 (§6): запись с прогнозом расчёта → при резолюции сравнить predicted vs actual
        if any("predicted" in p for p in pend):
            out["hint"] += (" У записи с полем predicted есть прогноз «📐» — при закрытии "
                            "исхода сравни ВСЛУХ прогноз и факт: расхождение — не провал, "
                            "а калибровка модели юзера.")
    return out


def _decision_record(session, surface="md"):
    from decision_record import build_record
    from session_render import render_decision_record
    record = build_record(session)
    return {"record": record, "content": render_decision_record(record, surface=surface)}


# ── «Principis-расчёт» Ф2 (спека §§5,7): карта решения → детерминированный МК ──
# Тонкие обёртки ядра Ф1 (decision_map.validate_map / mc_run.mc_run): логика гейтов и
# счёта живёт ТОЛЬКО там; здесь MCP-контракт, «📐 рамка» и point-of-use директивы.
# Ошибки — RU-строки: хост доносит их до юзера как ВОПРОСЫ совета, не как техдамп.

_RELAY_AS_QUESTIONS_HINT = (
    "Карта пока не готова — донеси каждую ошибку до юзера как ВОПРОС совета (голосом "
    "советника, простыми словами), не как техдамп; исправь карту его ответами и "
    "провалидируй снова.")


def _validate_decision_map(map):
    """Гейты честности карты решения БЕЗ счёта (fail-closed, спека §2). Хост зовёт после
    допроса круглого стола, ПЕРЕД run_calculation; errors → вопросы совета юзеру."""
    from decision_map import validate_map
    errors = validate_map(map)
    if errors:
        return {"valid": False, "errors": errors, "hint": _RELAY_AS_QUESTIONS_HINT}
    return {"valid": True, "errors": [],
            "hint": "Карта проходит гейты — можно считать: run_calculation(map)."}


_CALC_SEED_DEFAULT = 2026    # фикс-дефолт сида: вызов без seed воспроизводим байт-в-байт


def _calc_label_text(label):
    """Готовая «📐 рамка» (RU, одной строкой) из label-блока mc_run — хост показывает
    расчёт ТОЛЬКО с ней (честный лейбл: модель юзера, не истина)."""
    return ("📐 расчёт по ТВОЕЙ модели: %d величин (подтверждены тобой), сид %d, "
            "%d сценариев. Это не истина — это твоя модель, прогнанная %d раз."
            % (label["n_uncertainties"], label["seed"], label["n"], label["n"]))


def _run_calculation(map, seed=_CALC_SEED_DEFAULT, n=None):
    """Валидация (fail-closed, errors → вопросы совета) → mc_run (считает ТОЛЬКО код,
    детерминированно) → результат ядра + label_text («📐 рамка») + point-of-use директива.
    Ф3: histogram=True прокидывается сам, `render` несёт ГОТОВУЮ подачу (md + widget,
    calc_render) — гистограмма исходов, торнадо, сводка; рамка уже внутри."""
    import calc_render
    from decision_map import validate_map
    from mc_run import N_DEFAULT, mc_run
    errors = validate_map(map)
    if errors:
        return {"error": "Карта решения не проходит гейты честности — расчёт не запущен "
                         "(fail-closed).",
                "errors": errors, "hint": _RELAY_AS_QUESTIONS_HINT}
    try:
        res = mc_run(map, seed, N_DEFAULT if n is None else n, histogram=True)
    except ValueError as e:
        return {"error": str(e)}
    res["label_text"] = _calc_label_text(res["label"])
    names = {o["id"]: (o.get("name") or o["id"]) for o in map["options"]}
    res["render"] = {
        "md": calc_render.render_calc_md(res, label_text=res["label_text"],
                                         option_names=names),
        "widget": calc_render.render_calc_widget(res, label_text=res["label_text"],
                                                 option_names=names),
    }
    res["note"] = (
        "Показывай расчёт юзеру ТОЛЬКО вместе с рамкой label_text — без неё «📐» не существует. "
        "Подача ГОТОВА в render: в Cowork скорми render.widget в mcp__visualize__show_widget "
        "(гистограмма исходов + торнадо + сводка, рамка уже внутри), иначе покажи render.md. "
        "Лейбл «📐 расчёт» ставь РЯДОМ с мнениями советников (🔵/🟢/🟡), НЕ смешивая: расчёт — "
        "не цитата и не истина. top_uncertainties — величины, которые реально решают исход: "
        "предложи юзеру разыграть 2×2, назвав их осями (сам формат 2×2 — заседание совета, "
        "не счёт). В конце ОДИН РАЗ предложи сохранить карту — согласился → save_decision_map.")
    return res


_DECISIONS_DIR = "decisions"     # артефакты карт — в корне доски, рядом с principis.md


def _decision_predicted(map, res):
    """RU-сводка прогноза из результата МК: лучший вариант по P(лучший) + ожидание метрики.
    Это `predicted` записи §4.3/§6 — при резолюции ⏳→✅/❌ сравнивается с фактом."""
    best = max(res["p_best"], key=res["p_best"].get)
    name = next((o.get("name") or o["id"] for o in map["options"] if o.get("id") == best), best)
    # name/metric — хостовый текст; переводы строк режем, чтобы journal_line не могла
    # инъецировать структуру журнала (строку ИСХОД и т.п.)
    return (("лучший вариант — «%s»: P(лучший) %.2f, ожидание %.4g (%s)"
             % (name, res["p_best"][best], res["options"][best]["mean"],
                map["stakes"]["metric"])).replace("\n", " ").replace("\r", " "))


def _save_decision_map(map, slug=None, seed=_CALC_SEED_DEFAULT, n=None):
    """Артефакт карты decisions/<дата>-<slug>.json под _root() — МУТИРУЮЩИЙ тул, зовётся
    ТОЛЬКО с явного согласия юзера (правило 0). Внутри файла — карта + МК-сводка (predicted);
    наружу — journal_line («Прогноз: 📐 …») для записи журнала §4.3. Fail-closed: невалидная
    карта / кривой слаг / путь вне корня → отказ ДО любой записи."""
    import re
    from decision_map import validate_map
    from mc_run import N_DEFAULT, mc_run
    errors = validate_map(map)
    if errors:
        return {"error": "Карта решения не проходит гейты честности — сохранять нечего "
                         "(fail-closed).",
                "errors": errors, "hint": _RELAY_AS_QUESTIONS_HINT}
    if slug is not None:
        s = _validate_slug(slug)                      # общий строгий гард (M11)
        if s is None:
            return {"error": "Слаг карты должен быть из строчной латиницы, цифр и дефисов "
                             "(a-z0-9-), без путей и юникода — например ship-or-wait.",
                    "hint": "Дай простой латинский слаг или опусти его — я построю сам."}
    else:
        s = re.sub(r"[^a-z0-9]+", "-",
                   str(map.get("question") or "").lower()).strip("-")[:40] or "decision"
    n_eff = N_DEFAULT if n is None else n
    try:
        res = mc_run(map, seed, n_eff)                # сводка в файле = тот же детерминизм
    except ValueError as e:
        return {"error": str(e)}
    day = time.strftime("%Y-%m-%d")
    base = os.path.join(_DECISIONS_DIR, "%s-%s" % (day, s))
    predicted = _decision_predicted(map, res)
    with exclusive_file_lock(os.path.join(_root(), _DECISIONS_DIR, ".allocation"), private=True):
        p, err = _unique_path_under_root(base, ".json")  # selection and publication are one critical section
        if err:
            return err
        rel = os.path.relpath(p, os.path.realpath(_root())).replace(os.sep, "/")
        atomic_write_json(
            p, {"kind": "decision_map", "saved": day, "map": map,
                "calculation": {"seed": seed, "n": n_eff,
                                "predicted": predicted, "result": res}},
            ensure_ascii=False, indent=2, private=True,
        )
    return {"ok": True, "path": rel, "predicted": predicted,
            "journal_line": "- Прогноз: 📐 %s (карта: %s)" % (predicted, rel),
            "note": ("Карта сохранена (этот тул зовут ТОЛЬКО с согласия юзера). journal_line — "
                     "готовая строка прогноза: при записи решения в журнал (§4.3) вставь её в "
                     "запись перед строкой ИСХОД, либо передай блок calculation={journal_line} "
                     "в render_session — outcome_nudge сам расширится прогнозом.")}


# ── Decision Card: жизненный цикл прогноз → исход → калибровка (спека decision-lifecycle) ──
# Card — единственный персистентный узел цикла (§2). Тонкие обёртки ядра decision_card /
# prediction_calibration (логика гейтов/метрик — там). Пишущие тулы (save/close) зовут ТОЛЬКО
# с согласия юзера (Rule 0). Артефакты — под decisions/ (gitignored, личные данные, §7).

def _card_path(root, name):
    return os.path.join(root, _DECISIONS_DIR, name)


def _load_cards(root):
    """Все Decision Card из decisions/*.card.json (fail-closed: битый/не-Card → пропуск)."""
    ddir = os.path.join(root, _DECISIONS_DIR)
    try:
        names = sorted(n for n in os.listdir(ddir) if n.endswith(".card.json"))
    except OSError:
        return []
    out = []
    for name in names:
        try:
            with open(os.path.join(ddir, name), encoding="utf-8") as f:
                card = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(card, dict) and card.get("kind") == "decision_card":
            out.append((name, card))
    return out


def _save_decision_card(map, chosen_option, slug=None, seed=_CALC_SEED_DEFAULT, n=None,
                        form=None, owner="self", review_date=None, review_horizon_days=None,
                        assumptions=None, success_criterion=None, reversibility=None,
                        statement=None, map_path=None, session_id=None, situation_ref=None):
    """Записать Decision Card артефактом decisions/<дата>-<slug>.card.json (МУТИРУЮЩИЙ, Rule 0).

    Card = момент РЕШЕНИЯ («я выбрал вариант X»): UUID, prediction contract (числа из mc_run,
    ХРАНЯТСЯ ЧИСЛАМИ), допущения, критерий успеха, дата ревью. chosen_option = id варианта из
    карты или null (явный defer → прогноз строится по статус-кво). Нужна дата ревью: либо
    review_date (ISO), либо review_horizon_days (дней от сегодня). form: event|metric|null
    (null → metric, если у ставки есть единицы). Fail-closed: невалидная карта/Card/слаг/путь
    → отказ ДО записи. Возвращает card_id + journal_line с якорем <!-- card: dc_… -->."""
    import re
    import datetime
    from decision_map import validate_map
    from mc_run import N_DEFAULT, mc_run
    import decision_card as dc

    errors = validate_map(map)
    if errors:
        return {"error": "Карта решения не проходит гейты честности — Card не собрать "
                         "(fail-closed).", "errors": errors, "hint": _RELAY_AS_QUESTIONS_HINT}

    option_ids = [o.get("id") for o in map.get("options", []) if isinstance(o, dict)]
    if chosen_option is not None and chosen_option not in option_ids:
        return {"error": "Выбранный вариант «%s» не из вариантов карты." % chosen_option,
                "hint": "chosen_option — id одного из map.options, либо null (defer)."}
    # прогноз строится по варианту решения; при defer (null) — по статус-кво (что будет, если ничего)
    pred_option = chosen_option
    if pred_option is None:
        pred_option = next((o.get("id") for o in map["options"] if o.get("status_quo") is True),
                           option_ids[0] if option_ids else None)

    created = time.strftime("%Y-%m-%d")
    # горизонт/дата ревью: одно выводится из другого; без обоих — отказ (петля обязана вернуться)
    horizon_days = review_horizon_days
    if review_date is None and isinstance(horizon_days, int) and not isinstance(horizon_days, bool):
        review_date = (dc._parse_date(created) + datetime.timedelta(
            days=horizon_days)).isoformat()
    if review_date is not None and (horizon_days is None):
        rd, cd = dc._parse_date(review_date), dc._parse_date(created)
        if rd is not None and cd is not None:
            horizon_days = (rd - cd).days
    if review_date is None or horizon_days is None:
        return {"error": "Нужна дата возврата к решению: задай review_date (ISO YYYY-MM-DD) "
                         "или review_horizon_days (дней).",
                "hint": "Совет обязан назначить, КОГДА вернуться и закрыть исход."}

    n_eff = N_DEFAULT if n is None else n
    try:
        res = mc_run(map, seed, n_eff)
        prediction = dc.build_prediction_from_mc(map, res, pred_option, form=form,
                                                 horizon_days=horizon_days, created=created,
                                                 statement=statement)
    except ValueError as e:
        return {"error": str(e)}

    card = {
        "schema_version": dc.SCHEMA_VERSION, "id": dc.new_card_id(), "created": created,
        "owner": owner if (isinstance(owner, str) and owner.strip()) else "self",
        "kind": dc.KIND_CARD,
        "links": {"map_path": map_path, "session_id": session_id, "situation_ref": situation_ref},
        "question": str(map.get("question") or ""), "chosen_option": chosen_option,
        "assumptions": assumptions if isinstance(assumptions, list) else [],
        "success_criterion": success_criterion, "review_date": review_date,
        "review_horizon_days": horizon_days, "prediction": prediction, "outcome": None,
    }
    if reversibility is not None:
        card["reversibility"] = reversibility

    card_errors = dc.validate_card(card, map=map)
    if card_errors:
        return {"error": "Decision Card не проходит гейты (fail-closed).", "errors": card_errors,
                "hint": _RELAY_AS_QUESTIONS_HINT}

    # слаг: тот же строгий контракт, что save_decision_map (fail-closed, без тихой санации)
    if slug is not None:
        s = _validate_slug(slug)                      # общий строгий гард (M11)
        if s is None:
            return {"error": "Слаг Card — строчная латиница/цифры/дефисы (a-z0-9-), без путей "
                             "и юникода.", "hint": "Дай простой латинский слаг или опусти его."}
    else:
        s = re.sub(r"[^a-z0-9]+", "-", str(map.get("question") or "").lower()).strip("-")[:40] \
            or "decision"
    base = os.path.join(_DECISIONS_DIR, "%s-%s" % (created, s))
    with exclusive_file_lock(os.path.join(_root(), _DECISIONS_DIR, ".allocation"), private=True):
        p, err = _unique_path_under_root(base, ".card.json")  # selection and publication are one critical section
        if err:
            return err
        rel = os.path.relpath(p, os.path.realpath(_root())).replace(os.sep, "/")
        atomic_write_json(p, card, ensure_ascii=False, indent=2, private=True)
    predicted = _decision_predicted(map, res)
    journal_line = ("- Прогноз: 📐 %s (карта: %s) <!-- card: %s -->"
                    % (predicted, map_path or rel, card["id"]))
    return {"ok": True, "path": rel, "card_id": card["id"], "predicted": predicted,
            "journal_line": journal_line,
            "note": ("Decision Card сохранена (тул зовут ТОЛЬКО с согласия юзера, Rule 0). "
                     "journal_line несёт невидимый якорь <!-- card: … --> — вставь строку в "
                     "запись журнала перед ИСХОД: при закрытии зови close_decision_card(card_id, "
                     "outcome) — числа (occurred/actual в тех же единицах) идут в Card, глиф ✅/❌ "
                     "остаётся человеку. Точность прогнозов копит prediction_calibration.")}


def _close_decision_card(outcome, card_id=None, path=None):
    """Закрыть Decision Card фактом исхода (МУТИРУЮЩИЙ, Rule 0). outcome: {resolved_on,
    occurred|actual, endorsed?, note?} — occurred(bool) для event / actual(число, ТЕ ЖЕ
    единицы) для metric. Ищет карту по card_id (скан decisions/) или по path. Fail-closed:
    исход не в тех единицах / дата раньше created / путь вне корня → отказ ДО записи."""
    import decision_card as dc
    root = _root()
    target = None
    if path is not None:
        p, err = _resolve_under_root(path)
        if err:
            return err
        if not p.endswith(".card.json") or not os.path.isfile(p):
            return {"error": "По пути нет Decision Card (.card.json): %s" % path}
        target = p
    elif card_id is not None:
        for name, card in _load_cards(root):
            if card.get("id") == card_id:
                target = _card_path(root, name)
                break
        if target is None:
            return {"error": "Не нашёл Decision Card с id %s в decisions/." % card_id}
    else:
        return {"error": "Укажи card_id или path закрываемой Card."}

    try:
        closed = atomic_update_json(
            target, lambda card: dc.close_card(card, outcome), private=True
        )
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return {"error": str(e), "hint": _RELAY_AS_QUESTIONS_HINT}
    rel = os.path.relpath(target, os.path.realpath(root)).replace(os.sep, "/")
    return {"ok": True, "path": rel, "card_id": closed.get("id"),
            "note": ("Исход записан числом в Card. Обнови и markdown-запись (глиф ИСХОД ⏳ → "
                     "✅/❌). Прогон prediction_calibration покажет Brier/MAE/покрытие по "
                     "сопоставимым решениям — расхождение прогноза и факта = калибровка, не провал.")}


def _prediction_calibration():
    """Числовая калибровка ПРОГНОЗОВ (не подачи): сканирует закрытые Decision Card в decisions/
    и считает Brier/log (события) + MAE/покрытие интервала (величины) по группам kind+unit.
    Малый N шумен → группа помечается trustworthy=False (порог prediction_calibration)."""
    from prediction_calibration import calibration_journal, MIN_TRUSTWORTHY_N
    cards = [c for _, c in _load_cards(_root())]
    journal = calibration_journal(cards)
    journal["min_trustworthy_n"] = MIN_TRUSTWORTHY_N
    if journal["closed"] == 0:
        journal["hint"] = ("Пока нет ЗАКРЫТЫХ решений с исходом — калибровать нечего. Закрывай "
                           "Card через close_decision_card, когда исход ляжет.")
    else:
        journal["hint"] = ("Показывай юзеру ТОЛЬКО группы с trustworthy=true (иначе N мал и "
                           "Brier/MAE шумны). Покрытие интервала ≈0.80 при честных p10/p90; "
                           "систематический промах — сигнал, что диапазоны узки/широки.")
    return journal


# ── Calibrated Consult: анти-оверрелайанс инструмент (спека 2026-07-18-calibrated-consult) ──
# Тонкие обёртки ядра calibrated_consult. Пишущие тулы зовут ТОЛЬКО с согласия юзера (Rule 0).
# Артефакты — consults/*.consult.json (gitignored, личные данные).
_CONSULTS_DIR = "consults"
# Свой relay-хинт: в потоке консульта нет карты решения — общий _RELAY_AS_QUESTIONS_HINT
# (текст про Decision Card) ввёл бы в заблуждение. Ошибки гейтов = вопросы к юзеру.
_CONSULT_RELAY_HINT = ("Ошибки — это вопросы к тебе: уточни свою позицию/уверенность/прогноз "
                       "и повтори.")


def _consult_slug(question):
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(question or "").lower()).strip("-")[:40] or "consult"


def _write_consult(record):
    """Записать запись consults/<created>-<slug>.consult.json под _root(), traversal-гард,
    коллизия→суффикс. → {ok, path} | {error}."""
    day = record.get("created") or time.strftime("%Y-%m-%d")
    base = os.path.join(_CONSULTS_DIR, "%s-%s" % (day, _consult_slug(record.get("question"))))
    with exclusive_file_lock(os.path.join(_root(), _CONSULTS_DIR, ".allocation"), private=True):
        p, err = _resolve_under_root(base + ".consult.json")
        if err:
            return err
        i = 1
        while os.path.exists(p):
            i += 1
            p, err = _resolve_under_root("%s-%d.consult.json" % (base, i))
            if err:
                return err
        rel = os.path.relpath(p, os.path.realpath(_root())).replace(os.sep, "/")
        atomic_write_json(p, record, ensure_ascii=False, indent=2, private=True)
    return {"ok": True, "path": rel}


def _load_consults(root):
    """Все записи consults/*.consult.json (fail-closed: битый/не-consult → пропуск).
    → [(name, record)]."""
    import calibrated_consult as ccm
    cdir = os.path.join(root, _CONSULTS_DIR)
    try:
        names = sorted(n for n in os.listdir(cdir) if n.endswith(".consult.json"))
    except OSError:
        return []
    out = []
    for name in names:
        try:
            with open(os.path.join(cdir, name), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and rec.get("kind") == ccm.KIND_CONSULT:
            out.append((name, rec))
    return out


def _find_consult(root, consult_id):
    """Путь+запись по id (скан consults/). → (path, record) | (None, None)."""
    for name, rec in _load_consults(root):
        if rec.get("id") == consult_id:
            return os.path.join(root, _CONSULTS_DIR, name), rec
    return None, None


def _open_consult(question, prior_call, prior_confidence, prior_abstain=False):
    """Зафиксировать ПРИОР ДО совета (МУТИРУЮЩИЙ, Rule 0). Fail-closed валидация → отказ до записи."""
    import calibrated_consult as ccm
    record = ccm.build_consult(question, prior_call, prior_confidence,
                               prior_abstain=prior_abstain)
    errs = ccm.validate_consult(record)
    if errs:
        return {"error": "Приор не проходит гейты (fail-closed) — фиксировать нечего.",
                "errors": errs, "hint": _CONSULT_RELAY_HINT}
    saved = _write_consult(record)
    if "error" in saved:
        return saved
    return {"ok": True, "consult_id": record["id"], "path": saved["path"],
            "next": "Теперь спроси совет как обычно. Когда получишь ответ, зафиксируй свою "
                    "позицию ПОСЛЕ через calibrated_consult_close(consult_id, …)."}


def _close_consult_tool(consult_id, posterior_call, posterior_confidence,
                        followed_council, posterior_abstain=False, prediction=None):
    """Зафиксировать ПОСТЕРИОР после совета + вернуть ЗЕРКАЛО (МУТИРУЮЩИЙ, Rule 0).
    Fail-closed: неизвестный/закрытый id, невалидный постериор/прогноз → отказ без записи."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    path, rec = _find_consult(root, consult_id)
    if rec is None:
        return {"error": "Не нашёл консульт с id %s в consults/ — сначала "
                         "calibrated_consult_open." % consult_id}
    try:
        closed = atomic_update_json(
            path,
            lambda current: ccm.close_consult(
                current, posterior_call, posterior_confidence,
                posterior_abstain=posterior_abstain,
                followed_council=followed_council, prediction=prediction,
            ),
            private=True,
        )
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return {"error": str(e), "hint": _CONSULT_RELAY_HINT}
    m = closed["mirror"]
    return {"ok": True, "mirror": m,
            "note": ("Зеркало: сдвиг позиции=%s, Δуверенности=%+.2f, «не знаю» подавлено=%s. "
                     "Это НЕ вердикт «оверрелайанс» (сдвиг мог быть честной коррекцией) — "
                     "вердикт даст лишь исход. Если решение отслеживаемо, приложи prediction "
                     "и закрой исход позже через calibrated_consult_resolve."
                     % (m["shifted"], m["confidence_delta"], m["abstention_dropped"]))}


def _resolve_consult_tool(consult_id, outcome):
    """Проставить исход консульту (МУТИРУЮЩИЙ, Rule 0). Fail-closed: неизвестный id / кривой
    исход / нет прогноза → отказ без записи."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    path, rec = _find_consult(root, consult_id)
    if rec is None:
        return {"error": "Не нашёл консульт с id %s в consults/." % consult_id}
    try:
        resolved = atomic_update_json(
            path, lambda current: ccm.resolve_consult(current, outcome), private=True
        )
    except (OSError, ValueError, TypeError, AttributeError) as e:
        return {"error": str(e), "hint": _CONSULT_RELAY_HINT}
    return {"ok": True, "consult_id": consult_id,
            "note": "Исход записан. Сводку оси оверрелайанса смотри calibrated_consult_journal."}


def _consult_journal_tool():
    """Сводка оси оверрелайанса по consults/ (реюз calibrated_consult.overreliance_journal).
    Малое N → trustworthy=False (честный «мало данных», не выдумка)."""
    import calibrated_consult as ccm
    root = os.path.realpath(_root())
    consults = [rec for _name, rec in _load_consults(root)]
    return ccm.overreliance_journal(consults)


def _calc_forecast_line(calculation):
    """Ф2×§4.3: опциональный calculation-блок канона сессии → строка «- Прогноз: 📐 …»
    для шаблона записи в outcome_nudge. Канал детекции — ЯВНЫЙ: хост кладёт в сессию
    calculation={journal_line} (из save_decision_map) или {predicted} (из run_calculation
    до сохранения). Нет блока / мусор → None — нудж остаётся байт-в-байт прежним (бэк-компат)."""
    if not isinstance(calculation, dict):
        return None
    jl = calculation.get("journal_line")
    if isinstance(jl, str) and jl.strip():
        line = jl.strip()
        return line if line.startswith("-") else "- " + line
    pred = calculation.get("predicted")
    if isinstance(pred, str) and pred.strip():
        return "- Прогноз: 📐 " + pred.strip()
    return None
