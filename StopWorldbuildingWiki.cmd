@echo off
setlocal
title Stop Worldbuilding Wiki

wsl.exe -d Ubuntu -- bash -lc "if ! curl -fsS http://127.0.0.1:3764/api/health >/dev/null 2>&1; then exit 0; fi; curl -fsS -X POST http://127.0.0.1:3764/api/application/exit >/dev/null; for i in {1..20}; do curl -fsS http://127.0.0.1:3764/api/health >/dev/null 2>&1 || exit 0; sleep 0.25; done; exit 1"
if errorlevel 1 (
  echo Worldbuilding Wiki did not stop cleanly.
  pause
  exit /b 1
)
exit /b 0
