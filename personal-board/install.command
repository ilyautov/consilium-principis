#!/bin/bash
# macOS — двойной клик. Первый раз: правый клик → «Открыть» (обход Gatekeeper, если скачан).
cd "$(dirname "$0")" || exit 1
echo "Ставлю personal-board (Consilium)…"
python3 install.py "$@"
echo
read -r -p "Готово. Нажми Enter, чтобы закрыть."
