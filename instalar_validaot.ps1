[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$PythonExe = Join-Path $Backend '.venv\Scripts\python.exe'

function Invoke-PythonStep {
    param([string]$Description, [string[]]$Arguments)
    Write-Host "`n$Description" -ForegroundColor Cyan
    & $script:PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Falha na etapa: $Description (cÃ³digo $LASTEXITCODE). Consulte a mensagem acima."
    }
}

if (-not (Test-Path -LiteralPath $Backend -PathType Container)) {
    throw 'Pasta backend nÃ£o encontrada. Execute este instalador na pasta extraÃ­da do ValidaOT.'
}

$generatedPaths = @(
    (Join-Path $Backend '.env'),
    (Join-Path $Backend 'validaot_dev_v013.db'),
    (Join-Path $Backend 'audit_dev_genesis.json'),
    (Join-Path $Backend '.venv')
)
$existingGenerated = @($generatedPaths | Where-Object { Test-Path -LiteralPath $_ })
if ($existingGenerated.Count -gt 0) {
    Write-Host 'A instalaÃ§Ã£o jÃ¡ possui artefatos gerados. Para proteger os dados, o instalador nÃ£o continuarÃ¡:' -ForegroundColor Yellow
    $existingGenerated | ForEach-Object { Write-Host " - $_" }
    throw 'InstalaÃ§Ã£o nÃ£o iniciada. NÃ£o apague arquivos automaticamente; verifique o estado desta pasta.'
}

if (-not (Get-Command 'py.exe' -ErrorAction SilentlyContinue)) {
    throw 'Python Launcher (py.exe) nÃ£o encontrado. Instale Python 3.14 de 64 bits com o Python Launcher e tente novamente.'
}

Write-Host 'Verificando Python 3.14 de 64 bits...' -ForegroundColor Cyan
$pythonInfo = & py -3.14 -c "import sys, struct; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor)+'|'+str(struct.calcsize('P')*8))"
if ($LASTEXITCODE -ne 0 -or $pythonInfo.Trim() -ne '3.14|64') {
    throw "Ã‰ necessÃ¡rio Python 3.14 de 64 bits. Resultado encontrado: $pythonInfo"
}
Write-Host "Python compatÃ­vel: $pythonInfo" -ForegroundColor Green

Push-Location $Backend
try {
    Write-Host "`nCriando ambiente virtual..." -ForegroundColor Cyan
    & py -3.14 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'NÃ£o foi possÃ­vel criar o ambiente virtual.' }

    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw 'ExecutÃ¡vel Python do ambiente virtual nÃ£o foi encontrado.'
    }

    $script:PythonExe = $PythonExe
    Invoke-PythonStep -Description 'Instalando dependÃªncias fixadas' -Arguments @('-m', 'pip', 'install', '--timeout', '60', '--retries', '10', '-r', '.\requirements-lock-py314-win64.txt')
    Invoke-PythonStep -Description 'Verificando dependÃªncias' -Arguments @('-m', 'pip', 'check')

    Write-Host "`nGerando configuraÃ§Ã£o privada..." -ForegroundColor Cyan
    Write-Host 'A senha DEMO_PASSWORD serÃ¡ exibida pelo gerador. Guarde-a em local seguro.' -ForegroundColor Yellow
    Invoke-PythonStep -Description 'Criando .env local' -Arguments @('.\gerar_config_demo.py')

    Invoke-PythonStep -Description 'Inicializando banco e cadeia de auditoria' -Arguments @('.\initialize_dev_audit.py')
    Invoke-PythonStep -Description 'Criando contas e dados demonstrativos' -Arguments @('.\seed_demo_seguro.py')
    Invoke-PythonStep -Description 'Verificando integridade inicial da auditoria' -Arguments @('.\verify_dev_audit.py')

    Write-Host "`nINSTALAÃ‡ÃƒO VALIDAOT CONCLUÃDA." -ForegroundColor Green
    Write-Host 'Contas: tecnico@validaot.com, aprovador1@validaot.com, aprovador2@validaot.com, admin@validaot.com e auditor@validaot.com.'
    Write-Host 'Todas utilizam a DEMO_PASSWORD mostrada durante a geraÃ§Ã£o da configuraÃ§Ã£o.'
    Write-Host 'Para iniciar a aplicaÃ§Ã£o, volte Ã  raiz do pacote e execute iniciar_validaot.bat.'
}
finally {
    Pop-Location
}