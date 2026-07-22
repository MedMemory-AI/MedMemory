# ⚡ MedMemory AI –  Core Backend Server Engine

> An open-source, AI-native clinical intelligence engine. Track, parse, and map longitudinal patient medical history locally.

This repository houses the high-performance local RAG backend server engineered with FastAPI, LangChain, LangGraph, Qdrant Vector DB, and PostgreSQL, completely powered by offline Ollama models.

---

## 📚 Central Documentation Portal
For enterprise architecture blueprints, detailed multi-agent workflows, database designs, and front-end interface integrations, please visit our centralized tracking zones:

* **Install App APK:** [Latest Release](https://github.com/MedMemory-AI/frontend-app/releases/latest)
* 🌐 **Live Documentation Portal:** [medmemory-ai.github.io/docs](https://medmemory-ai.github.io/docs/)
* 🏛️ **Global Organization Workspace:** [@MedMemory-AI](https://github.com/MedMemory-AI)

---

## 🛠️ Tech Stack Primitives (Backend Specific)
* **API Framework:** FastAPI (Asynchronous request handling)
* **Orchestration Framework:** LangChain & LangGraph (Stateful multi-agent cycles)
* **OCR & Layout Parser:** Docling (Structured JSON extraction)
* **Local LLM Engine:** Ollama (`llama3.2` & `mxbai-embed-large`)
* **Relational Database:** PostgreSQL (Chronological metrics & schemas)
* **Vector Database:** Qdrant DB (Dense spatial vector search metrics)

---

## 🚀 3-Step Local Quick Start

If you are a contributor working specifically on the Python codebase, you can fire up the local development engine using these steps:

### Detailed Guide: [Local Setup Guide](https://medmemory-ai.github.io/docs/Guides/Local-Setup/)

---

### 1. Initialize Your Environment
```bash
git clone [https://github.com/MedMemory-AI/server.git](https://github.com/MedMemory-AI/server.git)
cd server
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

### 2. Boot Local Infrastructure Layers
Ensure your local Ollama instance is active and pull the model signatures:
```bash
ollama pull llama3.2
ollama pull mxbai-embed-large
```
Spin up your local storage instances via Docker:
```bash
docker run -d -p 6333:6333 qdrant/qdrant
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=local_secret postgres
```

### 3. Run the Backend Server
```bash
uvicorn app.main:app --reload --port 8000
```
The API interactive sandbox environment will immediately be available at http://localhost:8000/docs.

---

## 🤝 How to Contribute
Before submitting a Pull Request, please read our centralized [Contributing Guidelines](https://github.com/MedMemory-AI/.github/blob/main/CONTRIBUTING.md). Ensure you match local code-style rules and always execute your task variations on a dedicated feature branch (feat/your-patch).
