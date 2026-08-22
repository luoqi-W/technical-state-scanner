@echo off
setlocal

cd /d "%~dp0"

if not exist "frontend\dist\index.html" (
    echo Building frontend...
    pushd frontend
    if not exist "node_modules" (
        npm.cmd install
        if errorlevel 1 (
            echo Failed to install frontend dependencies.
            pause
            exit /b 1
        )
    )
    npm.cmd run build
    if errorlevel 1 (
        echo Failed to build frontend.
        pause
        exit /b 1
    )
    popd
)

echo Starting Technical State Scanner website...
echo Website: http://127.0.0.1:8000
start "" "http://127.0.0.1:8000"

python main.py server --host 127.0.0.1 --port 8000

pause
