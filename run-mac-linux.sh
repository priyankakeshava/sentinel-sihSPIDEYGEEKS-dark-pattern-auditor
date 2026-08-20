#!/bin/sh
set -e
echo "Starting Sentinel MVP..."
(cd darkshop && npm install && npm start) &
python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -r backend/requirements.txt
python -m playwright install chromium
uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
(cd frontend && npm install && npm run dev) &
echo "Open http://127.0.0.1:5173"
wait
