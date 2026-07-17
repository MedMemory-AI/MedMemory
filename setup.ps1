# ====================================
# MedMemory Local Setup
# ====================================
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "===================================="
Write-Host "  MedMemory Local Setup"
Write-Host "===================================="
Write-Host ""

# ------------------------------------
# Docker Check
# ------------------------------------
try {
    docker info *> $null
}
catch {
    Write-Host "Docker is not running."
    exit 1
}

Write-Host "[1/7] Starting containers..."
docker compose up -d --build

Write-Host ""
Write-Host "[2/7] Waiting for Ollama healthcheck..."
while ($true) {
    try {
        $status = docker inspect `
            -f "{{.State.Health.Status}}" `
            medmemory-ollama 2>$null

        if ($status -eq "healthy") {
            break
        }
    }
    catch {}
    Write-Host "Waiting for Ollama..."
    Start-Sleep -Seconds 5
}
Write-Host "Ollama is healthy."

Write-Host "[3/7] Checking Chat Model..."
$models = docker exec medmemory-ollama ollama list

if ($models -notmatch "qwen2.5:3b") {
    Write-Host "Installing qwen2.5:3b..."
    docker exec medmemory-ollama ollama pull qwen2.5:3b
}
else {
    Write-Host "qwen2.5:3b already installed."
}

Write-Host "[4/7] Checking Embedding Model..."
$models = docker exec medmemory-ollama ollama list

if ($models -notmatch "mxbai-embed-large") {
    Write-Host "Installing mxbai-embed-large..."
    docker exec medmemory-ollama ollama pull mxbai-embed-large
}
else {
    Write-Host "mxbai-embed-large already installed."
}

Write-Host ""
Write-Host "[5/7] Waiting for FastAPI..."
while ($true) {
    try {
        $status = docker inspect `
            -f "{{.State.Health.Status}}" `
            medmemory-backend 2>$null

        if ($status -eq "healthy") {
            break
        }
    }
    catch {}
    Write-Host "Waiting for FastAPI..."
    Start-Sleep -Seconds 5
}
Write-Host "FastAPI healthy."

Write-Host ""
Write-Host "[6/7] Running Prisma DB Push..."
docker compose exec backend `
    prisma db push `
    --schema=app/prisma/schema.prisma

Write-Host ""
Write-Host "[7/7] Checking Services..."
docker ps


Write-Host ""
Write-Host "===================================="
Write-Host " MedMemory Ready"
Write-Host "===================================="
Write-Host ""

Write-Host "FastAPI API:"
Write-Host "http://localhost:8000"

Write-Host ""
Write-Host "Swagger Docs:"
Write-Host "http://localhost:8000/docs"

Write-Host ""
Write-Host "Qdrant Dashboard:"
Write-Host "http://localhost:6333/dashboard"

Write-Host ""
Write-Host "Postgres:"
Write-Host "localhost:5432"

Write-Host ""
Write-Host "Ollama:"
Write-Host "http://localhost:11434"

Write-Host ""
Write-Host "Setup Complete!"

Write-Host ""
Write-Host "Useful Commands"
Write-Host "---------------"
Write-Host "docker compose logs -f backend"
Write-Host "docker compose logs -f ollama"
Write-Host "docker compose down"
Write-Host "docker compose restart backend"
