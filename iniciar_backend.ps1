$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'

foreach ($required in @($Python, (Join-Path $Backend '.env'), (Join-Path $Backend 'validaot_dev_v013.db'), (Join-Path $Backend 'audit_dev_genesis.json'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Arquivo necessÃ¡rio nÃ£o encontrado: $required. Execute instalar_validaot.ps1 primeiro."
    }
}

Set-Location $Backend
$startupCode = "from dotenv import load_dotenv; load_dotenv('.env', override=True); import main; from pathlib import Path; actual = Path(main.engine.url.database).resolve(); expected = Path('validaot_dev_v013.db').resolve(); assert actual == expected, 'Banco incorreto'; import uvicorn; uvicorn.run(main.app, host='127.0.0.1', port=8002, reload=False)"
Write-Host 'Iniciando ValidaOT Backend 0.7.0 em http://127.0.0.1:8002' -ForegroundColor Green
& $Python -c $startupCode
if ($LASTEXITCODE -ne 0) {
    throw "Backend encerrou com cÃ³digo $LASTEXITCODE. Consulte as mensagens acima."
}