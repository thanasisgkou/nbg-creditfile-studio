$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
python -m venv .venv
if ($LASTEXITCODE) { throw 'Python environment creation failed' }
& ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
Push-Location frontend
try {
 npm.cmd ci
 if ($LASTEXITCODE) { throw 'Frontend dependency installation failed' }
 npm.cmd run build
 if ($LASTEXITCODE) { throw 'Frontend build failed' }
} finally { Pop-Location }
