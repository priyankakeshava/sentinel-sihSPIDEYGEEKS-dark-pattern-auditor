@echo off
echo Starting Sentinel MVP...
start "Sentinel Store" cmd /k "cd darkshop && npm install && npm start"
start "Sentinel API" cmd /k "python -m venv .venv 2>nul & call .venv\Scripts\activate & pip install -r backend\requirements.txt & python -m playwright install chromium & uvicorn backend.main:app --host 127.0.0.1 --port 8000"
start "Sentinel UI" cmd /k "cd frontend && npm install && npm run dev"
echo Open http://127.0.0.1:5173
