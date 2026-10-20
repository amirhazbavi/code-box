@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYEXE="
if defined CODEBOX_PYTHON set "PYEXE=%CODEBOX_PYTHON%"
if not defined PYEXE if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYEXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYEXE for /f "delims=" %%P in ('where py 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%P"
if not defined PYEXE (
  echo Python was not found. Install Python or set CODEBOX_PYTHON to your python.exe path.
  pause
  exit /b 1
)
echo Using: "%PYEXE%"
echo Installing server requirements if needed...
"%PYEXE%" -m pip install -r requirements_server.txt
if errorlevel 1 goto :fail
echo.
echo Starting CodeBox website and account server...
echo Open http://127.0.0.1:8765 in your browser. Keep this window open.
"%PYEXE%" CodeBox_Server.py
if errorlevel 1 goto :fail
exit /b 0
:fail
echo Setup or server failed. Check the error above.
pause
exit /b 1
