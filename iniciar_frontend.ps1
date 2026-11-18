$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Frontend = Join-Path $Root 'frontend'
$Python = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$Server = Join-Path $Frontend 'dev_server.py'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Ambiente Python nÃ£o encontrado. Execute instalar_validaot.ps1 primeiro.'
}
if (-not (Test-Path -LiteralPath $Server -PathType Leaf)) {
    throw 'Servidor frontend nÃ£o encontrado.'
}

Set-Location $Frontend
Write-Host 'Iniciando ValidaOT Frontend em http://127.0.0.1:5175' -ForegroundColor Green
& $Python $Server --host 127.0.0.1 --port 5175 --backend http://127.0.0.1:8002
if ($LASTEXITCODE -ne 0) {
    throw "Frontend encerrou com cÃ³digo $LASTEXITCODE. Consulte as mensagens acima."
}