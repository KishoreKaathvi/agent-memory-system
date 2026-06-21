# Pending Roadmap & Enhancements

This document tracks planned enhancements, improvements, and features currently deferred for the Agent Memory System.

---

## 🔗 1. Graph-augmented Retrieval (Entity Relations)
- **Status**: Deferred.
- **Details**: Implement a lightweight entity-relationship parser to map facts together. Although the Memanto paper noted minor accuracy gains from graph-only setups, a hybrid Vector + BM25 + Graph pipeline remains a future optimization target when query logs justify it.

---

## 💾 2. Continuous S3 Database Replication (Litestream)
- **Status**: Pending.
- **Details**: Integrate Litestream to stream SQLite WAL transactions continuously to S3-compatible cloud storage. Provides near-zero Recovery Point Objective (RPO) backups for critical production instances.

---

## 🔑 3. Full OAuth 2.1 PKCE Flow for Browser Clients
- **Status**: Pending.
- **Details**: Build authorization endpoints to support OAuth 2.1 with PKCE for direct browser extensions and third-party dashboard setups.

---

## 📈 4. Multi-Server Horizontal Scaling (PostgreSQL Migration)
- **Status**: Deferred.
- **Details**: If client volumes grow beyond single-server write concurrency limits, execute the migration to PostgreSQL using pgloader to support row-level locks and cluster architectures.

---

## 🤖 5. Additional Free LLM Providers Integration (Groq, Cerebras, SiliconFlow)
- **Status**: Pending.
- **Details**: Integrate additional high-speed, free-tier OpenAI-compatible LLM providers (specifically Groq for high-speed Llama-3.3, Cerebras for Cerebras-WSE accelerated Qwen models, and SiliconFlow for DeepSeek reasoning models) into the backend fallback client (`llm.py`) and visual selection lock drop-down (`index.html`) to increase failover coverage. These will be sourced from the **[freeLLM.net](https://freellm.net/)** directory, which is the best single-point index for finding all free LLMs, rate limits, configurations, and API keys.
