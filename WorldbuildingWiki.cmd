@echo off
setlocal
title Worldbuilding Wiki Launcher

wsl.exe -d Ubuntu -- bash -lc "cd /home/hcj/dev/worldbuilding-wiki && if curl -fsS http://127.0.0.1:3764/api/health >/dev/null 2>&1; then exit 0; fi; if [ ! -x .venv/bin/worldbuilding-wiki ]; then echo 'Missing .venv/bin/worldbuilding-wiki' >&2; exit 1; fi; mkdir -p runtime; nohup .venv/bin/worldbuilding-wiki serve --no-browser --port 3764 >runtime/windows-launcher.log 2>&1 & for i in {1..60}; do curl -fsS http://127.0.0.1:3764/api/health >/dev/null 2>&1 && exit 0; sleep 0.5; done; exit 1"
if errorlevel 1 (
  echo.
  echo Worldbuilding Wiki failed to start.
  echo Log: \wsl.localhost\Ubuntu\home\hcj\dev\worldbuilding-wiki\runtime\windows-launcher.log
  pause
  exit /b 1
)

start "" "http://127.0.0.1:3764"
exit /b 0
