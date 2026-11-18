@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_validaot.ps1"
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar o ValidaOT. Leia a mensagem acima.
    pause
)
endlocal