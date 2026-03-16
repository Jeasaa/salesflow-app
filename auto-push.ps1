# Script d'auto-commit-push SalesFlow
# Usage: .\auto-push.ps1 "mon message"
# ou: .\auto-push.ps1 (utilise un message par défaut avec timestamp)

param(
    [string]$message = ""
)

$ErrorActionPreference = "Stop"

# Si pas de message, on en génère un avec timestamp
if ([string]::IsNullOrWhiteSpace($message)) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $message = "Update $timestamp"
}

Write-Host "📦 Auto-push SalesFlow" -ForegroundColor Cyan
Write-Host "Message: $message" -ForegroundColor Yellow
Write-Host ""

try {
    # Stage all changes
    Write-Host "📝 Stage all changes..." -ForegroundColor Blue
    git add .
    if ($LASTEXITCODE -ne 0) { throw "git add failed" }

    # Commit
    Write-Host "💾 Commit..." -ForegroundColor Blue
    git commit -m $message
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

    # Push
    Write-Host "🚀 Push to GitHub..." -ForegroundColor Blue
    git push
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }

    Write-Host ""
    Write-Host "✅ Success! Changes deployed." -ForegroundColor Green
    Write-Host "🌐 Backend: https://salesflow-api-production.up.railway.app" -ForegroundColor Gray
    Write-Host "🌐 Frontend: Check your Vercel deployment" -ForegroundColor Gray
}
catch {
    Write-Host ""
    Write-Host "❌ Error: $_" -ForegroundColor Red
    exit 1
}
