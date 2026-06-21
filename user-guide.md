# 📖 User Guide: Agent Memory System

A simple guide to help you set up, run, and integrate your Agent Memory System.

---

## ⚡ 1. Local Setup

### Prerequisite
Ensure Python 3.10+ and `uv` are installed on your computer.

### Start the Server
Run this command in your terminal to start the memory API backend:
```bash
uv run uvicorn app:app --port 8000 --reload
```
Once started, open your web browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🖥️ 2. Using the Dashboard Interface

Open `http://localhost:8000` in your browser. The dashboard gives you a visual way to manage memories:

- **📥 Store Tab**: Choose a memory class (`episodic` for decisions, `library` for documentation/notes) and write the content. Click **Record Memory** to save.
- **🔍 Search Tab**: Type a keyword (e.g. `database` or `frontend`) and click **Perform Hybrid Rerank Recall** to view matching memories.
- **🤖 Ask AI Tab**: Ask open-ended questions like *"Which database did we decide to use?"*. The system will fetch relevant memories and synthesize a structured response.
- **⚙️ Operations Card (Sidebar)**: Click **Safe Backup DB** to backup your database safely, or click **Sweep Expired TTL** to clear out unverified logs.

---

## 📡 3. REST API Integrations (curl examples)

Include these endpoints in your own scripts or agent pipelines. Always pass your API Key in the headers.

### A. Record a Fact (`POST /remember`)
```bash
curl -X POST http://localhost:8000/remember \
  -H "Authorization: Bearer mcp_localdev0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "default-agent",
    "memory_class": "episodic",
    "memory_type": "decision",
    "content": "We chose SQLite WAL mode for local storage."
  }'
```

### B. Search Memories (`POST /recall`)
```bash
curl -X POST http://localhost:8000/recall \
  -H "Authorization: Bearer mcp_localdev0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "default-agent",
    "query": "local storage choice",
    "top_k": 3
  }'
```

### C. Ask Contextual Questions (`POST /answer`)
```bash
curl -X POST http://localhost:8000/answer \
  -H "Authorization: Bearer mcp_localdev0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "default-agent",
    "query": "What local storage database are we using?"
  }'
```

---

## 🐳 4. Production Deployment with Docker

To deploy the system for remote access or servers:

1. Configure `.env` with your active keys.
2. Run:
   ```bash
   docker compose up -d --build
   ```
This exposes the REST endpoints on port `8000` with automated database persistence in volume mounts.

---

## 📅 5. Automated Backups & Cleanups

You can automate daily rollups, database backups, and TTL sweeps using the background job runner. Run these commands using a Cron Scheduler or Windows Task Scheduler:

- **Run safe backup**:
  ```bash
  uv run python run_jobs.py --backup-dir backups
  ```
- **Execute temporal rollups** (compressing raw segment logs into daily context):
  ```bash
  uv run python run_jobs.py --agent-id default-agent --date 2026-06-21
  ```
- **Sweep expired unverified memories**:
  ```bash
  uv run python run_jobs.py --agent-id default-agent --sweep
  ```
