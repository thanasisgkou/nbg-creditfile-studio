param([int]$Port = 8520, [switch]$Live)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path frontend/dist/index.html)) { throw 'Run npm ci and npm run build in frontend first.' }
$runArguments = @("$projectRoot/scripts/run.py", '--port', $Port)
if ($Live) { $runArguments += '--live' }
& "$projectRoot/.venv/Scripts/python.exe" @runArguments
exit $LASTEXITCODE
