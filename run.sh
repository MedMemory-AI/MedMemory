1. python -m venv venv
2. venv\Scripts\Activate

3. pip install -r requirements.txt

4. docker run -d --name medmemory-postgres -p 5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=local_secret -e POSTGRES_DB=medmemory postgres:16
5. docker run -d --name medmemory-qdrant -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:latest

6. winget install -e --id UB-Mannheim.TesseractOCR

7. Setup Ollama (qwen2.5:3b & mxbai-embed-large:latest)

8. prisma db push --schema=app/prisma/schema.prisma

9. uvicorn app.main:app --reload --port 8000

10. Postgres Dashboard -->> npx prisma studio --url=postgresql://postgres:local_secret@localhost:5432/medmemory

11. Qdrant Dashboard -->> http://localhost:6333/dashboard
