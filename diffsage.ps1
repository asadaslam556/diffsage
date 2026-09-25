<#
  DiffSage helper for Windows (the Makefile does the same on macOS/Linux).

    .\diffsage.ps1 setup         create .env with a random JWT secret
    .\diffsage.ps1 up            build and start everything in Docker, wait until healthy
    .\diffsage.ps1 down          stop it (data volumes are kept)
    .\diffsage.ps1 logs          follow the backend logs
    .\diffsage.ps1 health        print the live component report
    .\diffsage.ps1 infra         only Postgres/Redis/Qdrant/Ollama, for local dev
    .\diffsage.ps1 deps          install backend venv + frontend node_modules
    .\diffsage.ps1 dev-backend   run the API on :8000 with reload (needs infra + deps)
    .\diffsage.ps1 dev-frontend  run Vite on :5173 (proxies /api to :8000)
    .\diffsage.ps1 test          backend pytest + frontend vitest
    .\diffsage.ps1 lint          ruff

  If PowerShell refuses to run it: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  or run it once as:  powershell -ExecutionPolicy Bypass -File .\diffsage.ps1 up
#>
param([Parameter(Position = 0)][string]$Command = "help")

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Py = Join-Path $Root "backend\.venv\Scripts\python.exe"

function Need($exe, $hint) {
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { throw "$exe not found. $hint" }
}

function Ensure-Env {
  $envFile = Join-Path $Root ".env"
  if (Test-Path $envFile) { return }
  $bytes = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
  (Get-Content (Join-Path $Root ".env.example")) -replace "^JWT_SECRET=.*", "JWT_SECRET=$secret" |
    Set-Content -Encoding utf8 $envFile
  Write-Host "created .env with a random JWT_SECRET" -ForegroundColor Green
}

function Env-Port($name, $default) {
  $m = Select-String -Path (Join-Path $Root ".env") -Pattern "^$name=(\d+)" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($m) { return $m.Matches[0].Groups[1].Value }
  return $default
}

function Wait-Healthy {
  Write-Host "waiting for the API (first run also downloads the models, that can take a while)..."
  $api = Env-Port "API_PORT" 8000
  for ($i = 0; $i -lt 180; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:$api/api/health/live"
      if ($r.StatusCode -eq 200) { Write-Host "API is up." -ForegroundColor Green; return }
    } catch { Start-Sleep -Seconds 5 }
  }
  throw "API didn't come up. Check: .\diffsage.ps1 logs"
}

Push-Location $Root
try {
  switch ($Command) {
    "setup" { Ensure-Env }
    "up" {
      Need docker "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
      Ensure-Env
      docker compose up --build -d
      if ($LASTEXITCODE) { throw "docker compose failed" }
      Wait-Healthy
      $port = Env-Port "WEB_PORT" 8080
      $api = Env-Port "API_PORT" 8000
      Write-Host "open http://localhost:$port   (API health: http://localhost:$api/api/health)" -ForegroundColor Cyan
      Start-Process "http://localhost:$port"
    }
    "down" { docker compose down }
    "logs" { docker compose logs -f backend }
    "health" {
      # 503 still carries the JSON report, so read the body either way (works on PowerShell 5.1)
      $api = Env-Port "API_PORT" 8000
      try { $body = (Invoke-WebRequest -UseBasicParsing "http://localhost:$api/api/health").Content }
      catch { if (-not $_.Exception.Response) { throw }; $body = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() }
      $body | ConvertFrom-Json | ConvertTo-Json -Depth 6
    }
    "infra" { Ensure-Env; docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis qdrant ollama ollama-pull }
    "deps" {
      Need python "Install Python 3.11+ from https://www.python.org/downloads/ (tick 'Add to PATH')"
      Need npm "Install Node 22 LTS from https://nodejs.org/"
      if (-not (Test-Path $Py)) { python -m venv backend\.venv }
      & $Py -m pip install -r backend\requirements-dev.txt
      Push-Location frontend; npm install; Pop-Location
    }
    "dev-backend" {
      # talk to the dockerised stores from the host
      $env:DATABASE_URL = "postgresql+asyncpg://app:app@localhost:5432/diffsage"
      $env:REDIS_URL = "redis://localhost:6379/0"
      $env:QDRANT_URL = "http://localhost:6333"
      $env:PROVIDERS__OLLAMA__BASE_URL = "http://localhost:$(Env-Port "OLLAMA_PORT" 11434)"
      # compose maps OLLAMA_MODEL for the container; do the same when running on the host
      $m = Select-String -Path .env -Pattern "^OLLAMA_MODEL=(.+)$" -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($m) { $env:PROVIDERS__OLLAMA__MODEL = $m.Matches[0].Groups[1].Value.Trim() }
      Push-Location backend
      & $Py -m alembic upgrade head
      & $Py -m uvicorn app.main:create_app --factory --reload --port 8000
      Pop-Location
    }
    "dev-frontend" { Push-Location frontend; npm run dev; Pop-Location }
    "test" {
      Push-Location backend; & $Py -m pytest -q; $b = $LASTEXITCODE; Pop-Location
      Push-Location frontend; npm test; $f = $LASTEXITCODE; Pop-Location
      if ($b -or $f) { throw "tests failed" }
    }
    "lint" { Push-Location backend; & $Py -m ruff check app tests; Pop-Location }
    default { Get-Content $PSCommandPath -TotalCount 17 | Select-Object -Skip 1 }
  }
} finally {
  Pop-Location
}
