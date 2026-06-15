@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM workbench-autostart.bat - unattended "ensure the stack is UP + healthy".
REM
REM For Windows Task Scheduler (run daily before the Mon 10:00 ET weekly
REM rebalance). Idempotent + non-interactive + NO --build (fast): brings the
REM stack up if down, then polls /healthz. Distinct from start-workbench.bat
REM (Jay's interactive `up --build` launcher).
REM
REM It does NOT (re)activate any strategy. An activated PAPER strategy
REM AUTO-RESUMES on every backend boot (lifespan resume-on-boot), so the
REM momentum-portfolio book keeps running once activated ONCE via
REM scripts/paper_activate_momentum.py. Running activation daily would create a
REM duplicate strategy each day - don't.
REM
REM Norton can stay ON (ADR 0017 truststore). If the healthz output shows the
REM broker subsystem down/degraded, that's the Docker/Linux container CA caveat
REM (docs/runbook/factor-data.md 5d) - only then toggle Norton / run host-venv.
REM Prereq: Docker Desktop set to start on login.
REM ============================================================================

REM Repo root = parent of this script's dir.
cd /d "%~dp0.."
if not exist "logs" mkdir "logs"
set "LOG=%cd%\logs\workbench-launch.log"

echo. >> "%LOG%"
echo [%date% %time%] === autostart === >> "%LOG%"

docker info >nul 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: Docker daemon not running ^(start Docker Desktop^) >> "%LOG%"
  exit /b 1
)

echo [%date% %time%] docker compose up -d >> "%LOG%"
docker compose up -d >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: docker compose up -d failed >> "%LOG%"
  exit /b 2
)

REM Poll /healthz until HTTP 200 (backend cold-boot + Alpaca connect ~ up to 180s).
set /a tries=0
:healthcheck
set "CODE="
for /f %%C in ('curl -s -o "logs\healthz.json" -w "%%{http_code}" -m 5 http://localhost:8000/healthz 2^>nul') do set "CODE=%%C"
if "!CODE!"=="200" (
  echo [%date% %time%] healthz HTTP 200: >> "%LOG%"
  type "logs\healthz.json" >> "%LOG%"
  echo. >> "%LOG%"
  exit /b 0
)
set /a tries+=1
if !tries! geq 36 (
  echo [%date% %time%] ERROR: healthz not 200 after ~180s ^(last=!CODE!^) >> "%LOG%"
  if exist "logs\healthz.json" type "logs\healthz.json" >> "%LOG%"
  exit /b 3
)
timeout /t 5 /nobreak >nul
goto healthcheck
