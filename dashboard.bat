@echo off
REM Launch the BoxBoxF1Fantasy Streamlit dashboard.
REM Activates the project venv if present, otherwise uses the system python.

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

streamlit run dashboard\app.py
