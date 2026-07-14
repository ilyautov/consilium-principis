"""Общий плеер демо-сценариев (терминальная анимация под запись VHS).

Сценарий отдаёт список строк (style, text); харнесс печатает их в тёмной теме с
паузами (кадр-дифференциатор держим дольше). style-словарь — надмножество для всех
сценариев. Prompt печатается посимвольно (эффект набора). Ноль состояния, чистый вывод
(Rule 1/10): ни путей, ни JSON — это забота сценария, харнесс лишь красит и держит темп.
"""
import sys
import time

# ── ANSI (тёмная тема, крупный акцент) ──
_ANSI = {
    "prompt": "\033[1;37m",   # белый жирный — команда
    "dim": "\033[2;37m",      # приглушённый серый — повествование
    "quote": "\033[0;36m",    # голубой — текст цитаты
    "refuse": "\033[1;33m",   # жёлтый — отказ/предупреждение (дифференциатор)
    "warn": "\033[1;33m",     # жёлтый — то же семейство
    "proof": "\033[1;36m",    # ярко-голубой — 🔵 пруф
    "num": "\033[1;36m",      # ярко-голубой — числовой результат
    "bar": "\033[0;36m",      # голубой — ASCII-гистограмма
    "label": "\033[1;37m",    # белый — имя советника/фигуры
    "cta": "\033[1;37m",      # белый жирный — финальная строка
    "blank": "",
}
_RESET = "\033[0m"

# Паузы после строки (сек). Кадры-дифференциаторы держим дольше — дать прочитать.
_PAUSES = {
    "blank": 0.05,
    "refuse": 1.4,
    "warn": 1.4,
    "proof": 1.5,
    "num": 1.3,
    "cta": 1.2,
}
_DEFAULT_PAUSE = 0.55
_CHAR_DELAY = 0.028


def _type(text, style):
    color = _ANSI.get(style, "")
    if style == "prompt":                       # посимвольно — эффект набора команды
        sys.stdout.write(color)
        for ch in text:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(_CHAR_DELAY)
        sys.stdout.write(_RESET + "\n")
    else:
        sys.stdout.write(color + text + _RESET + "\n")
    sys.stdout.flush()


def render(lines, animate=True, pauses=None):
    """Проигрывает [(style, text), ...]. animate=False → плоский текст (тесты/проверка)."""
    if not animate:
        for _style, text in lines:
            print(text)
        return
    pause_map = dict(_PAUSES)
    if pauses:
        pause_map.update(pauses)
    for style, text in lines:
        _type(text, style)
        time.sleep(pause_map.get(style, _DEFAULT_PAUSE))
