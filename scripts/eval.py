#!/usr/bin/env python3
"""
eval.py — харнесс точности и безопасности совета (перенос логики Гефеста под fidelity).

Метрики (по образцу Гефеста: retrieval / extraction / abstention раздельно):

  [РАБОТАЕТ] FIDELITY — каждая цитата из quote_bank персоны ДОСЛОВНО есть в загруженном
             корпусе? Ловит: фабрикацию, рассинхрон издания/перевода (quote_bank из Hays,
             корпус из Casaubon = не совпадёт, и это ПРАВИЛЬНЫЙ сигнал).
  [СПЕКА]    RETRIEVAL — golden-набор {вопрос → ожидаемый чанк}: top-1/top-3 (нужен движок tier).
  [СПЕКА]    ABSTENTION — вопросы вне корпуса → доля честных отказов vs галлюцинаций (цель 0%).
  [СПЕКА]    CHALLENGE-RATE — доля заседаний, где совет реально оспорил пользователя (анти-эхо).

Запуск: python eval.py advisors/munger advisors/naval advisors/marcus-aurelius
"""
import sys, os, re, json

def norm(s):
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.U)
    return re.sub(r"\s+", " ", s).strip()

def parse_quote_bank(persona_path):
    if not os.path.isfile(persona_path):
        return []
    t = open(persona_path, encoding="utf-8").read()
    # секция между '## Quote bank' и следующим '## '
    m = re.search(r"##\s*Quote bank.*?\n(.*?)(?:\n##\s|\Z)", t, re.S | re.I)
    block = m.group(1) if m else t
    # цитаты в «...» или "..."
    quotes = re.findall(r"[«\"]([^«»\"]{12,})[»\"]", block)
    return quotes

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

def fidelity_eval(adv_dir):
    name = os.path.basename(adv_dir.rstrip("/"))
    quotes = parse_quote_bank(os.path.join(adv_dir, "persona.md"))
    corpus = load_corpus_text(adv_dir)
    if corpus is None:
        return name, len(quotes), None, []  # корпус не загружен
    grounded, ungrounded = 0, []
    for q in quotes:
        # дословное вхождение нормализованной цитаты (первые ~8 слов как якорь)
        anchor = " ".join(norm(q).split()[:8])
        if anchor and anchor in corpus:
            grounded += 1
        else:
            ungrounded.append(q[:70])
    return name, len(quotes), grounded, ungrounded

def main():
    paths = sys.argv[1:] or []
    if not paths:
        print("Дай папки советников: python eval.py advisors/munger ...", file=sys.stderr)
        sys.exit(1)

    print("=== FIDELITY (цитата дословно в корпусе?) ===")
    for p in paths:
        name, total, grounded, ung = fidelity_eval(p)
        if grounded is None:
            print(f"  {name}: {total} цитат · корпус НЕ загружен → проверка по источнику вручную "
                  f"(публичные цитаты, см. tier в quote_bank)")
            continue
        pct = (grounded / total * 100) if total else 0
        flag = "" if pct == 100 else "  ⚠️ есть негрунтованные (фабрикация ИЛИ другое издание/перевод)"
        print(f"  {name}: grounded {grounded}/{total} ({pct:.0f}%){flag}")
        for u in ung[:5]:
            print(f"      ✗ нет в корпусе: «{u}...»")

    print("\n=== RETRIEVAL / ABSTENTION / CHALLENGE-RATE ===")
    print("  [СПЕКА — реализовать в Claude Code, нужен движок tier + golden-набор]")
    print("  RETRIEVAL: golden {вопрос→чанк} → top-1/top-3 (как Гефест semantic_eval.py).")
    print("  ABSTENTION: N вопросов вне корпуса → % честных отказов; цель 0% галлюцинаций")
    print("             (порог из board_config.json abstain_threshold=0.62).")
    print("  CHALLENGE-RATE: парсить council/sessions/*.md → доля, где совет оспорил юзера.")

if __name__ == "__main__":
    main()
