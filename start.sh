#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  echo "Missing .venv. Run ./install.sh first."
  exit 1
fi

source .venv/bin/activate
python app.py
