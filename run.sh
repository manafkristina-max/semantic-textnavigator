#!/usr/bin/env bash
# Запуск одной командой: ./run.sh            — приложение на http://localhost:8501
#                        ./run.sh test       — автотесты
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

if [ "${1:-}" = "test" ]; then
  exec .venv/bin/python -m pytest -q
fi
exec .venv/bin/python -m streamlit run app.py
