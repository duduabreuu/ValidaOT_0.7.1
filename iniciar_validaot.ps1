$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$BackendScript = Join-Path $Root 'iniciar_backend.ps1'
$FrontendScript = Join-Path $Root 'iniciar_frontend.ps1'

function Test-LocalPort {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(400)
        if ($connected -and $client.Connected) {
            $client.EndConnect($async)
            return $true
        }
        return $false
    }
    catch { return $false }
    finally { $client.Close() }
}

foreach ($port in @(8002, 5175)) {
    if (Test-LocalPort -Port $port) {
        throw "A porta $port jÃ¡ estÃ¡ em uso. Encerre a instÃ¢ncia anterior do ValidaOT antes de iniciar outra."
    }
}

Write-Host 'Abrindo janela do backend...' -ForegroundColor Cyan
$backendArgs = '-NoExit -ExecutionPolicy Bypass -File "' + $BackendScript + '"'
Start-Process -FilePath 'powershell.exe' -ArgumentList $backendArgs -WorkingDirectory $Root

Write-Host 'Aguardando backend na porta 8002...' -ForegroundColor Cyan
$backendReady = $false
for ($i = 0; $i -lt 45; $i++) {
    if (Test-LocalPort -Port 8002) { $backendReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $backendReady) {
    throw 'O backend nÃ£o abriu a porta 8002 em 45 segundos. Verifique a janela do backend antes de tentar novamente.'
}

Write-Host 'Backend disponÃ­vel. Abrindo janela do frontend...' -ForegroundColor Green
$frontendArgs = '-NoExit -ExecutionPolicy Bypass -File "' + $FrontendScript + '"'
Start-Process -FilePath 'powershell.exe' -ArgumentList $frontendArgs -WorkingDirectory $Root

Write-Host 'Aguardando frontend na porta 5175...' -ForegroundColor Cyan
$frontendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    if (Test-LocalPort -Port 5175) { $frontendReady = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $frontendReady) {
    throw 'O frontend nÃ£o abriu a porta 5175. Verifique a janela do frontend.'
}

Write-Host 'ValidaOT disponÃ­vel em http://127.0.0.1:5175' -ForegroundColor Green
Start-Process 'http://127.0.0.1:5175'