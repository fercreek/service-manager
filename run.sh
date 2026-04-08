#!/bin/bash
set -e
cd "$(dirname "$0")"

# Load .env if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt --quiet
fi

echo "Starting Service Manager on http://localhost:${SM_PORT:-9000}"
.venv/bin/python app.py
