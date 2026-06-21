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

## ⚙️ 2. Provider, Model, and API Key Configuration

> [!NOTE]
> For the easiest setup, use **[freeLLM.net](https://freellm.net/)**—the best single-point index for finding all free LLM models, getting free API keys, looking up OpenAI-compatible configuration settings, and comparing daily rate limits.

The Agent Memory System uses local CPU-based models for hybrid search/reranking and external LLM APIs (OpenRouter, NVIDIA NIM) for contradiction checks, temporal summaries, and answer generation.

### A. Backend LLM Providers & Model Selection
All external LLM configurations are managed server-side via the `.env` file in the project root:
- **OpenRouter (Default)**: Set key in `OPENROUTER_API_KEY` and specify model in `OPENROUTER_MODEL` (e.g., `meta-llama/llama-3.3-70b-instruct:free`).
- **NVIDIA NIM (Fallback)**: Set key in `NVIDIA_API_KEY`. Supports frontier models like `deepseek-ai/deepseek-v4-flash`, `qwen/qwen3.5-397b-a17b`, `moonshotai/kimi-k2.6`, `z-ai/glm-5.1`, `minimaxai/minimax-m3`.
- **Google Gemini (AI Studio)**: Set key in `GEMINI_API_KEY`. Supports `gemini-2.5-flash`, `gemini-2.5-pro`.
- **GitHub Models**: Set token in `GITHUB_TOKEN`. Supports `gpt-4o-mini`, `gpt-4o`, `meta-llama-3.1-405b-instruct`.
- **Mistral AI**: Set key in `MISTRAL_API_KEY`. Supports `mistral-small-latest`, `mistral-large-latest`, `codestral-latest`.
- **Cohere**: Set key in `COHERE_API_KEY`. Supports `command-r`, `command-r-plus`.
- **Together AI**: Set key in `TOGETHER_API_KEY`. Supports Qwen and Llama Turbo models.
- **SambaNova**: Set key in `SAMBANOVA_API_KEY`. Supports Llama 3.1 405B and 70B models.
- **Custom Fallback Chain**: If you want to modify fallback priorities, edit the `FALLBACK_CHAIN` array inside [llm.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/llm.py).

*Note: For security and stability, these keys cannot be uploaded via the dashboard UI. They must be set in the `.env` file or passed as environment variables in Docker.*

### B. Client Access & API Authorization Key
To authenticate agents, tools, or users communicating with the memory backend:
1. Set the access key on the server in `.env` under `MEMORY_SYSTEM_API_KEY`.
2. **Dashboard access**: Paste the token into the **🛡️ Authentication** card in the dashboard's left sidebar under **API Authorization Token**.
3. **REST API access**: Pass the key in the request header: `Authorization: Bearer <key>`.
4. **MCP Tool access**: Pass the key as the `api_key` argument in `remember` or `recall` tool calls.

---

## 🖥️ 3. Using the Dashboard Interface

Open `http://localhost:8000` in your browser. The dashboard gives you a visual way to manage memories:

- **📥 Store Tab**: Choose a memory class (`episodic` for decisions, `library` for documentation/notes) and write the content. Click **Record Memory** to save.
- **🔍 Search Tab**: Type a keyword (e.g. `database` or `frontend`) and click **Perform Hybrid Rerank Recall** to view matching memories.
- **🤖 Ask AI Tab**: Ask open-ended questions like *"Which database did we decide to use?"*. The system will fetch relevant memories and synthesize a structured response.
- **⚙️ Operations Card (Sidebar)**: Click **Safe Backup DB** to backup your database safely, or click **Sweep Expired TTL** to clear out unverified logs.

---

## 📡 4. REST API Integrations (curl examples)

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

## 🐳 5. Production Deployment with Docker

To deploy the system for remote access or servers:

1. Configure `.env` with your active keys.
2. Run:
   ```bash
   docker compose up -d --build
   ```
This exposes the REST endpoints on port `8000` with automated database persistence in volume mounts.

---

## 📅 6. Automated Backups & Cleanups

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
