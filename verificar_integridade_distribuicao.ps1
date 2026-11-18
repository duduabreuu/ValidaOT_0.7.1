$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Manifest = Join-Path $Root 'MANIFEST_SHA256.txt'
if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
    throw 'MANIFEST_SHA256.txt nÃ£o encontrado.'
}

$failures = @()
$checked = 0
foreach ($line in Get-Content -LiteralPath $Manifest) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -notmatch '^([A-Fa-f0-9]{64})\s+(.+)$') {
        $failures += "Linha invÃ¡lida no manifesto: $line"
        continue
    }
    $expected = $matches[1].ToUpperInvariant()
    $relative = $matches[2].Replace('/', '\')
    $target = Join-Path $Root $relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        $failures += "AUSENTE: $relative"
        continue
    }
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $expected) {
        $failures += "HASH DIVERGENTE: $relative"
        continue
    }
    $checked++
}

$forbiddenFiles = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File | Where-Object {
    $_.Name -eq '.env' -or $_.Name -eq 'audit_dev_genesis.json' -or $_.Extension -in @('.db', '.sqlite', '.sqlite3', '.pyc')
})
$forbiddenDirs = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory | Where-Object {
    $_.Name -in @('.venv', '__pycache__')
})
if ($forbiddenFiles.Count -gt 0) {
    $forbiddenFiles | ForEach-Object { $failures += "ARQUIVO PRIVADO/GERADO INDEVIDO: $($_.FullName)" }
}
if ($forbiddenDirs.Count -gt 0) {
    $forbiddenDirs | ForEach-Object { $failures += "PASTA DE AMBIENTE/CACHE INDEVIDA: $($_.FullName)" }
}

if ($failures.Count -gt 0) {
    Write-Host 'VERIFICAÃ‡ÃƒO DA DISTRIBUIÃ‡ÃƒO: FALHOU' -ForegroundColor Red
    $failures | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    exit 1
}

Write-Host 'VERIFICAÃ‡ÃƒO DA DISTRIBUIÃ‡ÃƒO: OK' -ForegroundColor Green
Write-Host "Arquivos verificados: $checked"
Write-Host 'Arquivos privados, banco e ambiente virtual: nÃ£o encontrados.'