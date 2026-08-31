#!/usr/bin/env bash
# Tekarai backend — یک‌دستوره ساخت محیط مجازی و اجرای کل تست‌ها.
# پوشهٔ .venv عمداً از اسنپ‌شات ورک‌اسپیس حذف است (حجم بالا)؛ این اسکریپت
# در صورت نبود/خرابی‌اش، آن را تازه می‌سازد و سپس تست‌ها را اجرا می‌کند.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-/usr/local/bin/python3}"

if [ ! -x ".venv/bin/python" ] || ! .venv/bin/python -c "import django, channels, daphne" 2>/dev/null; then
  echo ">> ساخت/بازسازی .venv ..."
  rm -rf .venv
  "$PY" -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/python -m pip install -q -r requirements/development.txt
fi

echo ">> Django system check ..."
./.venv/bin/python manage.py check --settings=config.settings.testing

echo ">> اجرای کل سوییت تست ..."
./.venv/bin/python manage.py test --settings=config.settings.testing "$@"
