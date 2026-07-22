#!/bin/bash
# Linux/macOS terminal launcher. It never installs Python or packages automatically.
cd "$(dirname "$0")" || exit 1

CONSILIUM_PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
    "$candidate" -c "import sys; assert sys.version_info >= (3, 10)" >/dev/null 2>&1; then
    CONSILIUM_PYTHON="$candidate"
    break
  fi
done

if [ -z "$CONSILIUM_PYTHON" ]; then
  echo "Python 3.10+ is required. Install it with your system package manager, then run this launcher again." >&2
  exit 1
fi

exec "$CONSILIUM_PYTHON" install.py "$@"
