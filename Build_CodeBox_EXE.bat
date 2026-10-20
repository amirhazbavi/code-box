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
echo [1/4] Installing Python dependencies...
"%PYEXE%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%PYEXE%" -m pip install -r requirements_build.txt
if errorlevel 1 goto :fail
echo.
echo [2/4] Building CodeBox Free EXE...
"%PYEXE%" -m PyInstaller --noconfirm --clean --windowed --onefile --collect-all pygments --name CodeBox_Free --icon CodeBox.ico --distpath dist CodeBox_Free.py
if errorlevel 1 goto :fail
echo.
echo [3/4] Building CodeBox Plus EXE...
"%PYEXE%" -m PyInstaller --noconfirm --clean --windowed --onefile --collect-all pygments --name CodeBox_Plus --icon CodeBox.ico --distpath dist CodeBox_Plus.py
if errorlevel 1 goto :fail
echo.
echo [4/4] Copying release builds into the gated website downloads folder...
if not exist downloads mkdir downloads
copy /Y "dist\CodeBox_Free.exe" "downloads\CodeBox_Free.exe" >nul
if errorlevel 1 goto :fail
copy /Y "dist\CodeBox_Plus.exe" "downloads\CodeBox_Plus.exe" >nul
if errorlevel 1 goto :fail
echo.
echo Build complete!
echo Free: %CD%\dist\CodeBox_Free.exe
echo Plus: %CD%\dist\CodeBox_Plus.exe
echo Website serves EXE files when present and source files if no EXE exists.
echo Note: Plus downloads remain locked by server-side account entitlement.
pause
exit /b 0
:fail
echo.
echo Build failed. Read the error above. If PyInstaller is incompatible with this Python version, try Python 3.12 or 3.13.
pause
exit /b 1
