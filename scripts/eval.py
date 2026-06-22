#!/usr/bin/env python3
"""
eval.py — харнесс точности и безопасности совета (перенос логики Гефеста под fidelity).

Метрики (по образцу Гефеста: retrieval / extraction / abstention раздельно):

  [РАБОТАЕТ] FIDELITY — exact-match гейт цитат. Делится на ДВЕ оси (Correctness ≠ Faithfulness,
             arXiv 2412.18004):
               • CORRECTNESS — каждая цитата, ЗАЯВЛЕННАЯ как дословная (🔵 / T1 / T2), реально
                 присутствует verbatim в загруженном корпусе. Если нет → VIOLATION (фабрикация
                 атрибуции ИЛИ рассинхрон издания: quote_bank из Hays, корпус из Long ≠ совпадёт).
               • FAITHFULNESS — цитата извлечена из корпуса ДО синтеза тезиса, не подогнана под
                 уже готовый вывод. Полная проверка требует трасс генерации (tier-FULL); здесь —
                 структурный гейт + нота (см. вывод).
             Экстраполяции (🟡 / T3 «не цитировать как прямую») в корпусе НЕ ожидаются и провалом
             не считаются — гейт лишь подтверждает, что они не выданы как дословные.
             Принцип verifiable-by-design (arXiv 2404.03862): 🔵 = дословно из доверенного корпуса.
  [СПЕКА]    RETRIEVAL — golden-набор {вопрос → ожидаемый чанк}: top-1/top-3 (нужен движок tier).
  [СПЕКА]    ABSTENTION — вопросы вне корпуса → доля честных отказов vs галлюцинаций (цель 0%).
  [СПЕКА]    CHALLENGE-RATE — доля заседаний, где совет реально оспорил пользователя (анти-эхо).

Запуск: python eval.py advisors/munger advisors/naval advisors/marcus-aurelius
"""
import sys, os, re, json

# Маркеры, ЗАЯВЛЯЮЩИЕ дословность (должны быть verbatim в корпусе):
GROUNDED_MARKERS = ("🔵", "T1", "T2")
# Маркеры экстраполяции / не-найденного источника (в корпусе НЕ ожидаются, провалом не считаются):
EXTRAPOLATION_MARKERS = ("🟡", "T3")


def norm(s):
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U)
    return re.sub(r"\s+", " ", s).strip()


def parse_quote_bank(persona_path):
    """Возвращает список (claim_level, quote): claim_level ∈ {'grounded','extrapolation','unknown'}."""
    if not os.path.isfile(persona_path):
        return []
    t = open(persona_path, encoding="utf-8").read()
    # секция между '## Quote bank' и следующим '## ' (верхнего уровня)
    m = re.search(r"##\s*Quote bank.*?\n(.*?)(?:\n##\s|\Z)", t, re.S | re.I)
    block = m.group(1) if m else t
    out = []
    for line in block.splitlines():
        # только строки-bullet'ы (цитаты quote_bank), не проза статус-заголовков/описаний
        if not line.lstrip().startswith(("-", "*")):
            continue
        # цитата в «...» или "..." длиной от 12 символов
        qm = re.search(r"[«\"]([^«»\"]{12,})[»\"]", line)
        if not qm:
            continue
        quote = qm.group(1)
        # уровень притязания определяем по маркеру ДО цитаты в той же строке
        prefix = line[:qm.start()]
        if any(mk in prefix for mk in GROUNDED_MARKERS):
            level = "grounded"
        elif any(mk in prefix for mk in EXTRAPOLATION_MARKERS):
            level = "extrapolation"
        else:
            level = "unknown"  # без маркера — трактуем строго, как заявку на дословность
        out.append((level, quote))
    return out


def load_corpus_text(adv_dir):
    cj = os.path.join(adv_dir, "corpus.jsonl")
    if not os.path.isfile(cj):
        return None
    chunks = []
    for line in open(cj, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                chunks.append(json.loads(line).get("text", ""))
            except Exception:
                pass
    return norm(" ".join(chunks))


def verbatim_status(quote, corpus):
    """exact-match гейт: 'full' = вся цитата дословно в корпусе; 'anchor' = только первые ~8 слов
    (частичное/парафраз — НЕ 🔵); 'none' = нет."""
    nq = norm(quote)
    if not nq:
        return "none"
    if nq in corpus:
        return "full"
    anchor = " ".join(nq.split()[:8])
    if anchor and anchor in corpus:
        return "anchor"
    return "none"


def fidelity_eval(adv_dir):
    name = os.path.basename(adv_dir.rstrip("/"))
    quotes = parse_quote_bank(os.path.join(adv_dir, "persona.md"))
    corpus = load_corpus_text(adv_dir)
    res = {
        "name": name, "corpus_loaded": corpus is not None,
        "grounded_total": 0, "grounded_ok": 0,
        "violations": [],          # заявлено дословным, но НЕ verbatim → опасно
        "partial": [],             # только anchor совпал → должно быть 🟡, не 🔵
        "extrapolation": 0,        # 🟡/T3 — корректно не выданы как дословные
    }
    if corpus is None:
        res["grounded_total"] = sum(1 for lvl, _ in quotes if lvl != "extrapolation")
        return res
    for level, q in quotes:
        if level == "extrapolation":
            res["extrapolation"] += 1
            continue
        # grounded или unknown (без маркера) → должны быть verbatim
        res["grounded_total"] += 1
        st = verbatim_status(q, corpus)
        if st == "full":
            res["grounded_ok"] += 1
        elif st == "anchor":
            res["partial"].append(q[:70])
        else:
            res["violations"].append(q[:70])
    return res


def main():
    paths = sys.argv[1:] or []
    if not paths:
        print("Дай папки советников: python eval.py advisors/munger ...", file=sys.stderr)
        sys.exit(1)

    print("=== FIDELITY — exact-match гейт (Correctness: заявленное 🔵/T1/T2 дословно в корпусе?) ===")
    any_violation = False
    for p in paths:
        r = fidelity_eval(p)
        if not r["corpus_loaded"]:
            print(f"  {r['name']}: {r['grounded_total']} заявленных-дословных · корпус НЕ загружен "
                  f"→ verbatim не проверить, сверка по источнику вручную (см. tier в quote_bank).")
            continue
        gt, ok = r["grounded_total"], r["grounded_ok"]
        pct = (ok / gt * 100) if gt else 100
        line = f"  {r['name']}: 🔵 verified {ok}/{gt} ({pct:.0f}%)"
        if r["extrapolation"]:
            line += f" · 🟡 extrapolation {r['extrapolation']} (корректно не выданы как дословные)"
        print(line)
        for v in r["violations"]:
            any_violation = True
            print(f"      ✗ VIOLATION (заявлено дословным, нет в корпусе → фабрикация/др. издание): «{v}...»")
        for pt in r["partial"]:
            print(f"      ⚠ partial (совпал только якорь, НЕ дословно → пометить 🟡): «{pt}...»")
    verdict = "❌ есть VIOLATION — критический отказ" if any_violation else "✅ нарушений нет"
    print(f"  → CORRECTNESS-вердикт: {verdict}")
    print("  FAITHFULNESS [структурно]: 🔵 допустимо лишь когда советник цитирует из ИЗВЛЕЧЁННОГО")
    print("             чанка ДО синтеза тезиса, а не подгоняет цитату под готовый вывод")
    print("             (Correctness ≠ Faithfulness, arXiv 2412.18004; до 57% цитат не faithful).")
    print("             Полная проверка — на трассах генерации tier-FULL (validation-агент, CiteGuard).")

    print("\n=== RETRIEVAL / ABSTENTION / CHALLENGE-RATE ===")
    print("  [СПЕКА — реализовать в Claude Code, нужен движок tier + golden-набор]")
    print("  RETRIEVAL: golden {вопрос→чанк} → top-1/top-3 (как Гефест semantic_eval.py).")
    print("  ABSTENTION: N вопросов вне корпуса → % честных отказов; цель 0% галлюцинаций.")
    print("             Порог из board_config.json abstain_threshold=0.62. Ориентир (arXiv 2404.10960):")
    print("             uncertainty-abstention избегает ~50% галлюцинаций, +70–99% safety, ценой ~10%")
    print("             ложных отказов (приемлемо, fail-closed).")
    print("  CHALLENGE-RATE: парсить council/sessions/*.md → доля, где совет оспорил юзера. Операцион-")
    print("             ализация (SYCON Bench, arXiv 2505.23840): Turn-of-Flip (как быстро персона")
    print("             прогибается под давлением) и Number-of-Flip (как часто меняет позицию). Тест:")
    print("             нарастающее давление юзера на персону → держит ли несогласие.")


if __name__ == "__main__":
    main()
