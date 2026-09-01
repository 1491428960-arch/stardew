@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PWSH="

where pwsh.exe >nul 2>&1
if not errorlevel 1 set "PWSH=pwsh.exe"

if not defined PWSH if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" (
    set "PWSH=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe"
)

if not defined PWSH (
    echo PowerShell 7 was not found.
    echo Install PowerShell 7 and try again.
    pause
    exit /b 1
)

"%PWSH%" -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_ai_npc_test.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Launcher failed. Exit code: %EXIT_CODE%
)
pause
exit /b %EXIT_CODE%
