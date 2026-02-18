@echo off
setlocal enabledelayedexpansion

:: hotmic.bat — Windows-native launcher for HotMic
:: Auto-detects Python, installs dependencies on first run,
:: and forwards all CLI arguments to voice_type.py.

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "SCRIPT_PY=%SCRIPT_DIR%\voice_type.py"
set "APP_DIR=%LOCALAPPDATA%\HotMic"
set "PROD_DIR=%APP_DIR%\prod"
set "PID_FILE=%APP_DIR%\hotmic.pid"

:: ── Find Python ──
call :find_python
if not defined PY (
    echo Error: Could not find Python.
    echo.
    echo Install it with:
    echo   winget install Python.Python.3.12
    echo.
    echo Then restart your terminal and try again.
    exit /b 1
)

:: ── Route command ──
if "%~1"=="--install" goto install
if "%~1"=="--uninstall" goto uninstall
if "%~1"=="--build" goto build
if "%~1"=="--stop" goto stop

:: ── Normal launch ──
call :ensure_deps
%PY% "%SCRIPT_PY%" %*
exit /b %errorlevel%

:: =====================================================================
:install
echo Installing HotMic...

call :ensure_deps
echo   Python dependencies: OK

if not exist "%APP_DIR%" mkdir "%APP_DIR%"

:: Copy icon
if exist "%SCRIPT_DIR%\hotmic.ico" (
    copy /y "%SCRIPT_DIR%\hotmic.ico" "%APP_DIR%\hotmic.ico" >nul
)

:: Detect prod snapshot or fall back to source tree
set "LAUNCH_PY=%SCRIPT_PY%"
set "LAUNCH_DIR=%SCRIPT_DIR%"
if exist "%PROD_DIR%\voice_type.py" (
    set "LAUNCH_PY=%PROD_DIR%\voice_type.py"
    set "LAUNCH_DIR=%PROD_DIR%"
    echo   Using prod snapshot: %PROD_DIR%\
) else (
    echo   No prod snapshot — using source tree
)

:: Create VBS launcher (hides the console window)
for /f "delims=" %%p in ('%PY% -c "import sys; print(sys.executable)"') do set "WIN_PY=%%p"
set "VBS_PATH=%APP_DIR%\hotmic.vbs"
> "%VBS_PATH%" echo Set WshShell = CreateObject("WScript.Shell")
>> "%VBS_PATH%" echo WshShell.Run """%WIN_PY%"" ""%LAUNCH_PY%""", 0, False

:: Create Start Menu shortcut
set "LNK_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\HotMic.lnk"
set "ICO_PATH=%APP_DIR%\hotmic.ico"
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LNK_PATH%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_PATH%\"'; $s.WorkingDirectory = '%LAUNCH_DIR%'; $s.IconLocation = '%ICO_PATH%'; $s.Description = 'HotMic - Whisper-powered voice dictation'; $s.Save()"
echo   Start Menu shortcut: HotMic

echo.
echo Done! You can now:
echo   - Win+S: type "HotMic" and hit Enter
echo   - Or run: hotmic.bat [options]
exit /b 0

:: =====================================================================
:uninstall
echo Uninstalling HotMic...

set "LNK_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\HotMic.lnk"
if exist "%LNK_PATH%" (
    del "%LNK_PATH%"
    echo   Removed Start Menu shortcut
) else (
    echo   No Start Menu shortcut found
)

if exist "%APP_DIR%" (
    rmdir /s /q "%APP_DIR%"
    echo   Removed app data: %APP_DIR%
)

echo Done.
exit /b 0

:: =====================================================================
:build
echo Building prod snapshot...
if not exist "%PROD_DIR%" mkdir "%PROD_DIR%"
copy /y "%SCRIPT_DIR%\voice_type.py" "%PROD_DIR%\voice_type.py" >nul
if exist "%SCRIPT_DIR%\config.toml" (
    copy /y "%SCRIPT_DIR%\config.toml" "%PROD_DIR%\config.toml" >nul
)
echo   Copied voice_type.py to %PROD_DIR%\
echo   Copied config.toml   to %PROD_DIR%\
echo.
echo Done! Run 'hotmic.bat --install' to update the Start Menu shortcut.
exit /b 0

:: =====================================================================
:stop
if not exist "%PID_FILE%" (
    echo No PID file found — HotMic may not be running.
    exit /b 0
)
set /p PID=<"%PID_FILE%"
if "%PID%"=="" (
    echo PID file is empty. Cleaning up.
    del "%PID_FILE%"
    exit /b 0
)
echo Stopping HotMic (PID %PID%)...
taskkill /PID %PID% /F >nul 2>&1
if not errorlevel 1 (
    echo   Killed process %PID%
) else (
    echo   Process %PID% not found (already stopped?)
)
if exist "%PID_FILE%" del "%PID_FILE%"
echo Done.
exit /b 0

:: =====================================================================
:find_python
:: 1. py.exe launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PY=py -3"
        exit /b 0
    )
)
:: 2. python.exe on PATH
where python >nul 2>&1
if not errorlevel 1 (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PY=python"
        exit /b 0
    )
)
:: 3. Common install locations
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%d\python.exe" (
        set "PY=%%d\python.exe"
        exit /b 0
    )
)
exit /b 1

:: =====================================================================
:ensure_deps
set "MISSING="
for %%m in (RealtimeSTT keyboard requests) do (
    %PY% -c "import importlib; importlib.import_module('%%m')" >nul 2>&1
    if errorlevel 1 (
        if defined MISSING (
            set "MISSING=!MISSING! %%m"
        ) else (
            set "MISSING=%%m"
        )
    )
)
if defined MISSING (
    echo Installing missing dependencies: %MISSING%
    %PY% -m pip install --quiet %MISSING%
)
exit /b 0
