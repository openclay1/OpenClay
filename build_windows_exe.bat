@echo off
REM build_windows_exe.bat — Package OpenClay for Windows
REM Run from the Open Clay directory

echo Building OpenClay.exe...

REM Ensure dependencies
pip install pyinstaller pillow 2>nul

REM Generate icon if missing
python openclay_icon.py 2>nul

REM Build with PyInstaller
pyinstaller --onefile --windowed ^
  --icon=openclay.ico ^
  --name="OpenClay" ^
  --add-data "SOUL.md;." ^
  --add-data "BRAIN.md;." ^
  --add-data "AGENTS.md;." ^
  --add-data "lang_detect.py;." ^
  --add-data "daily_agents.py;." ^
  --add-data "predict_engine.py;." ^
  --add-data "vibe_brain.py;." ^
  --add-data "model_config.py;." ^
  --add-data "voice_input.py;." ^
  --add-data "audit_log.py;." ^
  --add-data "first_screen.py;." ^
  --add-data "integration_detector.py;." ^
  openclay_app.py

echo.
echo === NSIS Installer (manual step) ===
echo To create OpenClay Setup.exe, install NSIS and use:
echo   makensis openclay_installer.nsi
echo.
echo The installer will:
echo   - Copy to Program Files\OpenClay\
echo   - Create Desktop shortcut
echo   - Add Start Menu entry
echo   - Offer taskbar pin on completion
echo.
echo Build complete. / Listo.
pause
