# Rayan runs this manually after starting the server. Ctrl+C stops this tunnel.
$ErrorActionPreference = 'Stop'
$tunnelCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $tunnelCommand) {
    Write-Output 'FAIL cloudflared PATH: missing; install with winget install Cloudflare.cloudflared'
    exit 1
}

Write-Output 'Starting tunnel to http://localhost:8000; waiting for the HTTPS URL...'
$tunnelFound = $false
$tunnelExit = 1
try {
    # Native cloudflared writes normal informational logs to stderr. Windows
    # PowerShell must not treat those lines as terminating NativeCommandErrors.
    $ErrorActionPreference = 'Continue'
    & $tunnelCommand tunnel --url http://localhost:8000 2>&1 | ForEach-Object {
        $line = $_.ToString()
        if (-not $tunnelFound -and $line -match '(?i)(https://[a-z0-9-]+\.trycloudflare\.com)(?=$|[^a-z0-9.-])') {
            $tunnelFound = $true
            $tunnelOrigin = $Matches[1].ToLowerInvariant()
            Write-Output "HTTPS URL: $tunnelOrigin"
            Write-Output "Phone URL: $tunnelOrigin/phone"
            Write-Output 'Keep this terminal open. Ctrl+C stops the tunnel.'
        }
    }
    $tunnelExit = if ($null -eq $LASTEXITCODE) { 0 } else { $LASTEXITCODE }
} catch {
    $tunnelExit = 1
} finally {
    $ErrorActionPreference = 'Stop'
}
if (-not $tunnelFound -or $tunnelExit -ne 0) {
    Write-Output 'FAIL tunnel: cloudflared exited or did not return an HTTPS URL'
    exit 1
}
exit 0
