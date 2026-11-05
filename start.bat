@echo off
REM ============================================
REM Start script para Windows
REM ============================================

cd /d "%~dp0"

echo 🤖 Iniciando LinkedIn Job Bot...
echo.

REM Verificar entorno virtual
if not exist "venv\Scripts\activate.bat" (
    echo ❌ Entorno virtual no encontrado.
    echo Creando...
    python -m venv venv
    if errorlevel 1 (
        echo Error creando venv. ¿Python en PATH?
        pause
        exit /b 1
    )
    echo Instalando dependencias...
    venv\Scripts\pip install -r requirements.txt
    if errorlevel 1 (
        echo Error instalando dependencias.
        pause
        exit /b 1
    )
)

REM Verificar config
if not exist "config.local.yaml" (
    if not exist ".env" (
        echo ⚠️  No hay config.local.yaml ni .env
        echo Copia config.local.yaml.example a config.local.yaml y edita tus keys
        echo O copia .env.example a .env
        pause
        exit /b 1
    )
)

echo ✅ Entorno listo. Iniciando bot...
echo Presiona Ctrl+C para parar.
echo.

venv\Scripts\python main.py

pause