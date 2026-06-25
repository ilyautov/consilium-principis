#!/bin/bash
# Linux/macOS — запуск из терминала: bash install.sh
cd "$(dirname "$0")" || exit 1
python3 install.py "$@"
