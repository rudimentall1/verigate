param(
    [switch]$Live
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:VERIGATE_ENABLE_DEMO_TAMPER = "true"
$env:VERIGATE_ENABLE_DEMO_ENDPOINTS = if ($Live) { "true" } else { "false" }

Write-Host "Starting Verigate local demo..." -ForegroundColor Cyan
if ($Live) {
    Write-Host "LIVE MODE: Solana Devnet execution endpoint is enabled." -ForegroundColor Yellow
} else {
    Write-Host "SAFE MODE: only the deterministic tamper proof is enabled." -ForegroundColor Green
}

$python = Get-Command python -ErrorAction Stop
$args = @("-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8000")
$proc = Start-Process -FilePath $python.Source -ArgumentList $args -WorkingDirectory $root -PassThru

try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:8000/health"
            if ($health.status -eq "ok") { $ready = $true; break }
        } catch {}
    }
    if (-not $ready) { throw "Verigate API did not become ready on port 8000." }

    Start-Process "http://localhost:8000/demo/"
    Write-Host ""
    Write-Host "Demo: http://localhost:8000/demo/" -ForegroundColor Green
    Write-Host "API PID: $($proc.Id)"
    if ($Live) {
        Write-Host "Stop the API when finished: Stop-Process -Id $($proc.Id)"
    } else {
        Write-Host "For real Devnet execution, rerun: .\scripts\demo.ps1 -Live"
    }
} catch {
    if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    throw
}
