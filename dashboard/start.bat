@echo off
cd /d "%~dp0"
echo Iniciando Maxi Portas Dashboard...
echo Acesse: http://localhost:8000
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
