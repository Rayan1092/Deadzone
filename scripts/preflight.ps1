# Run from any directory; all diagnostics come from the shared secret-safe checker.
$ErrorActionPreference = 'Stop'
$preflightRoot = Split-Path -Parent $PSScriptRoot
$preflightPython = Join-Path $preflightRoot '.venv/Scripts/python.exe'
$preflightActivation = 'failed'
try {
    . (Join-Path $preflightRoot '.venv/Scripts/Activate.ps1') *> $null
    $preflightActivation = 'ok'
} catch { } # the checker reports this without echoing exception contents
if (-not (Test-Path -LiteralPath $preflightPython)) {
    $preflightFallback = Get-Command py,python3,python -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $preflightFallback) {
        Write-Output 'FAIL .venv activation: Python unavailable'
        exit 1
    }
    $preflightPython = $preflightFallback.Source
}
& $preflightPython (Join-Path $PSScriptRoot 'preflight.py') --activation $preflightActivation
exit $LASTEXITCODE
