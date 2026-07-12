1. python -m venv venv
2. venv\Scripts\Activate

3. pip install -r requirements.txt

4. docker run -d --name medmemory-postgres -p 5432:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=local_secret -e POSTGRES_DB=medmemory postgres:16
5. docker run -d --name medmemory-qdrant -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant:v1.9.0

6. uvicorn app.main:app --reload --port 8000

7. prisma db push --schema=app/prisma/schema.prisma
