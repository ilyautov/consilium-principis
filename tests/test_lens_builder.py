"""Интерактивный билдер линз: текст-основа автора → P1 (🔵 его слова), твои заметки-прочтение →
U1 (fail-closed → 🟡). Линза = advisor-каталог; строится тем же pipeline.build, читается контуром
(fidelity_check/cite) идентично. Стережёт: честные тиры (заметки НЕ становятся 🔵), линза грузится
и honest, ров цел (заметка-прочтение никогда не выдаётся за дословные слова автора)."""
import os, sys, json, collections, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from lens_builder import build_lens
from engine.fidelity import best_match

# реальный PD-отрывок Макиавелли (Discourses, Thomson) — его дословные слова
GROUND = ("But since a people may happen to be deceived as regards the character, reputation, "
          "and actions of a man, thinking them greater than in reality they are.")
# твоё прочтение — интерпретация, НЕ его слова
NOTES = ("Я читаю это как предупреждение: репутация — рычаг, но она хрупкая, и её нельзя путать "
         "с реальной добродетелью. Применяю к найму: проверяй вклад, а не образ.")


def _build(tmp, **kw):
    dest = os.path.join(tmp, "machiavelli-my-reading")
    return build_lens(dest, name="Макиавелли — как читаю я", ground_text=GROUND,
                      reading_notes=NOTES, author="Niccolò Machiavelli", kind="personality",
                      run_kernels=False, **kw), dest


def test_author_words_are_p1_blue_notes_are_u1_yellow():
    with tempfile.TemporaryDirectory() as tmp:
        res, dest = _build(tmp)
        tiers = collections.Counter()
        for line in open(os.path.join(dest, "build", "corpus.jsonl"), encoding="utf-8"):
            line = line.strip()
            if line:
                tiers[json.loads(line)["tier"]] += 1
        assert tiers["P1"] >= 1 and tiers["U1"] >= 1            # оба слоя в корпусе
        # слова автора (подстрока ground) → 🔵 (P1)
        m = best_match("a people may happen to be deceived", dest)
        assert m and m[0] == "P1"
        # фраза из твоих заметок → НЕ дословный авторский тир: не P1/P2 → 🟡 (fail-closed)
        mn = best_match("проверяй вклад, а не образ", dest)
        assert mn is None or mn[0] not in ("P1", "P2")          # прочтение не выдаётся за слова автора


def test_lens_loads_and_is_honest():
    with tempfile.TemporaryDirectory() as tmp:
        res, dest = _build(tmp)
        assert os.path.isfile(os.path.join(dest, "lens.md"))
        from lenses import load_lens, is_lens_honest
        lens = load_lens(dest)
        assert lens["name"]
        assert is_lens_honest(lens, has_corpus=True) is True    # есть корпус → 🔵 честно


def test_self_kind_grounds_user_words_as_p1():
    # «линза себя»: твои слова = авторитет твоей персоны → P1 (🔵), как в Telegram-ингесте
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "self")
        build_lens(dest, name="Я", ground_text="Я строю на доказуемом результате, не на образе.",
                   kind="self", run_kernels=False)
        m = best_match("на доказуемом результате", dest)
        assert m and m[0] == "P1"


def test_result_reports_tiers_and_path():
    with tempfile.TemporaryDirectory() as tmp:
        res, dest = _build(tmp)
        assert res["dir"] == dest and res["n_chunks"] >= 2
        assert res["tiers"].get("P1", 0) >= 1 and res["tiers"].get("U1", 0) >= 1
