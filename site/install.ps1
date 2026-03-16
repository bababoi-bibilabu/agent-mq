# agent-mq installer for Windows
# irm https://agent-mq.com/install.ps1 | iex

$ErrorActionPreference = "Stop"
$installDir = "$HOME\.agent-mq"
$repo = "https://github.com/bababoi-bibilabu/agent-mq/archive/refs/heads/main.zip"

Write-Host "agent-mq installer" -ForegroundColor Cyan
Write-Host "==================="

# Download and extract
$zip = "$env:TEMP\agent-mq.zip"
Invoke-WebRequest -Uri $repo -OutFile $zip
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
Expand-Archive $zip -DestinationPath $env:TEMP -Force
Move-Item "$env:TEMP\agent-mq-main" $installDir
Remove-Item $zip

# Create mq.cmd in a PATH-accessible location
$binDir = "$HOME\.local\bin"
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
@"
@echo off
python3 "$installDir\skills\mq\scripts\mq.py" %*
"@ | Set-Content "$binDir\mq.cmd"

# Add to PATH if needed
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$binDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$binDir;$userPath", "User")
    Write-Host "[!!] Added $binDir to PATH. Restart your terminal." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[ok] agent-mq installed to $installDir" -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:"
Write-Host "  mq add backend"
Write-Host "  mq send backend 'hello' --from frontend"
Write-Host "  mq recv backend"
