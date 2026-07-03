@echo off
rem Double-click this file (Windows) to open the Literature Surveillance GUI.
rem On first run -- or on a machine it was shared to -- it sets up its own
rem Python environment automatically. No manual command line needed.
rem (Mac users: use "Run Surveillance.command" instead.)

setlocal enabledelayedexpansion
cd /d "%~dp0"
set "ROOT=%CD%"

if not exist "%ROOT%\pipeline\gui.py" (
    echo Could not find pipeline\gui.py in "%ROOT%".
    echo Keep this file inside the Hildegard project folder.
    pause
    exit /b 1
)

rem Find a system Python to bootstrap: prefer the "py" launcher, then "python".
set "PYBOOT="
where py >nul 2>nul && set "PYBOOT=py -3"
if not defined PYBOOT (
    where python >nul 2>nul && set "PYBOOT=python"
)
if not defined PYBOOT (
    echo Python 3 is required but was not found.
    echo Install it from https://www.python.org/downloads/ and run this again.
    echo During installation, tick "Add Python to PATH".
    pause
    exit /b 1
)

set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"

rem (Re)create the environment if it's missing or broken (e.g. a .venv copied
rem from another machine). Validate by importing the compiled dependencies.
set "NEED_SETUP="
if not exist "%VENV_PY%" (
    set "NEED_SETUP=1"
) else (
    "%VENV_PY%" -c "import anthropic, pydantic_core, markdown, xhtml2pdf" >nul 2>nul || set "NEED_SETUP=1"
)

if defined NEED_SETUP (
    echo First-time setup: creating the Python environment ^(this runs once^)...
    if exist "%ROOT%\.venv" rmdir /s /q "%ROOT%\.venv"
    %PYBOOT% -m venv "%ROOT%\.venv" || (echo Failed to create virtual environment. & pause & exit /b 1)
    "%VENV_PY%" -m pip install --upgrade pip >nul 2>nul
    echo Installing dependencies...
    "%VENV_PY%" -m pip install -r "%ROOT%\requirements.txt" || (echo Failed to install dependencies. & pause & exit /b 1)
    echo Setup complete.
)

rem Warn (don't block) if no Anthropic API key is configured.
set "HAVE_KEY="
if exist "%ROOT%\.env" (
    findstr /r /c:"^ANTHROPIC_API_KEY=." "%ROOT%\.env" >nul 2>nul && set "HAVE_KEY=1"
)
if not defined HAVE_KEY (
    echo.
    echo NOTE: no Anthropic API key found in .env.
    echo       The GUI will open and "dry run" works, but live extraction needs a key.
    echo       Copy .env.example to .env and add ANTHROPIC_API_KEY ^(and NCBI_API_KEY^).
    echo.
)

echo Launching Literature Surveillance GUI...
"%VENV_PY%" -m pipeline.gui
if errorlevel 1 (
    echo.
    echo GUI exited with an error. See the messages above.
    pause
)
endlocal
