# ============================================================================
# LokerBang — 1-Click Dashboard & API Launcher (Windows PowerShell)
# ============================================================================
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Starting LokerBang FastAPI Backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000 --reload"

Write-Host "Starting LokerBang React Dashboard on http://localhost:5173 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; npm run dev"
