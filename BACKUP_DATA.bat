@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src=Join-Path $env:LOCALAPPDATA 'SMSGateDeskCommunity'; if (-not (Test-Path $src)) { Write-Host 'No existing SMSGate Desk data found.'; exit 0 }; $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'; $dest=Join-Path ([Environment]::GetFolderPath('Desktop')) ('SMSGateDeskCommunity-Backup-'+$stamp); Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force -ErrorAction Stop; Write-Host ('Backup created: '+$dest)"
if errorlevel 1 echo Backup failed. Do not upgrade until you have a backup.
pause
