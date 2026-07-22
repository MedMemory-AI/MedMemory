#!/bin/bash
set -e

echo ""
echo "===================================="
echo "  MedMemory Local Setup"
echo "===================================="
echo ""

if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running."
    exit 1
fi

echo "[1/7] Starting containers..."
docker compose up -d --build

echo ""
echo "[2/7] Waiting for Ollama healthcheck..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' medmemory-ollama)" = "healthy" ]
do
    echo "Waiting for Ollama..."
    sleep 5
done
echo "Ollama is healthy."

echo "[3/7] Checking Chat Model..."
if ! docker exec medmemory-ollama ollama list | grep -q "^qwen2.5:3b"; then
    docker exec medmemory-ollama ollama pull qwen2.5:3b
else
    echo "qwen2.5:3b already installed."
fi

echo "[4/7] Checking Embedding Model..."
if ! docker exec medmemory-ollama ollama list | grep -q "^mxbai-embed-large"; then
    docker exec medmemory-ollama ollama pull mxbai-embed-large
else
    echo "mxbai-embed-large already installed."
fi

echo "[5/7] Waiting for FastAPI..."
until [ "$(docker inspect -f '{{.State.Health.Status}}' medmemory-backend)" = "healthy" ]
do
    echo "Waiting for FastAPI..."
    sleep 5
done
echo "FastAPI healthy."

echo ""
echo "[6/7] Running Prisma DB Push..."
docker compose exec backend sh -c \
  "prisma db push --schema=app/prisma/schema.prisma"

echo ""
echo "[7/7] Checking Services..."
docker ps

echo ""
echo "===================================="
echo " MedMemory Ready"
echo "===================================="
echo ""

echo "FastAPI API:"
echo "http://localhost:8000"

echo ""
echo "Swagger Docs:"
echo "http://localhost:8000/docs"

echo ""
echo "Qdrant Dashboard:"
echo "http://localhost:6333/dashboard"

echo ""
echo "Postgres:"
echo "localhost:5432"

echo ""
echo "Ollama:"
echo "http://localhost:11434"

echo ""
echo "Setup Complete!"

echo ""
echo "Useful Commands"
echo "---------------"
echo "docker compose logs -f backend"
echo "docker compose logs -f ollama"
echo "docker compose down"
echo "docker compose restart backend"
