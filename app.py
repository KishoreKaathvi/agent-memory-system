import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, Depends, Security
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from database import get_db, initialize_db, register_agent_namespace, verify_namespace_access
from retrieval import hybrid_recall_with_rerank, compute_confidence
from conflict import remember_with_conflict_check
from security import build_answer_prompt, validate_external_input
from llm import generate_answer


load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("memory.app")

# Environment key setup
MEMORY_SYSTEM_API_KEY = os.getenv(
    "MEMORY_SYSTEM_API_KEY", 
    "mcp_localdev0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
)

# Startup Lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and index schema on startup
    logger.info("Initializing database...")
    conn = get_db()
    try:
        initialize_db(conn)
        
        # Register a default workspace for local out-of-the-box usage
        logger.info("Registering default agent namespace...")
        register_agent_namespace(
            conn=conn,
            agent_id="default-agent",
            owner_id="default-owner",
            api_key=MEMORY_SYSTEM_API_KEY
        )
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
    finally:
        conn.close()
    yield

app = FastAPI(
    title="Agent Memory System REST API",
    version="2.0.0",
    description="Production-grade, self-hosted memory layer for AI agents",
    lifespan=lifespan
)

# Security authentication schema
security_scheme = HTTPBearer()

def authenticate_agent_id(agent_id: str, credentials: HTTPAuthorizationCredentials = Depends(security_scheme)):
    """FastAPI dependency to verify that the request's Bearer token owns the agent namespace."""
    api_key = credentials.credentials
    conn = get_db()
    try:
        if not verify_namespace_access(conn, agent_id, api_key):
            logger.warning(f"Unauthorized access attempt to namespace '{agent_id}'")
            raise HTTPException(status_code=401, detail=f"Permission denied: Invalid API Key for agent '{agent_id}'.")
    finally:
        conn.close()

# Request and Response schemas
class RememberRequest(BaseModel):
    agent_id: str = Field(..., description="The namespace identifier")
    memory_class: str = Field(..., description="Must be 'episodic' or 'library'")
    memory_type: str = Field(..., description="Type of memory (e.g. 'fact', 'decision')")
    content: str = Field(..., description="Content to remember")
    source: str = Field("rest_api", description="Where the memory originated")
    llm_provider: str | None = Field(None, description="Optional target LLM provider")
    llm_model: str | None = Field(None, description="Optional target LLM model")

class RecallRequest(BaseModel):
    agent_id: str = Field(..., description="The namespace identifier")
    query: str = Field(..., description="The query to search memories for")
    top_k: int = Field(8, description="Number of results to retrieve")

class AnswerRequest(BaseModel):
    agent_id: str = Field(..., description="The namespace identifier")
    query: str = Field(..., description="User query to synthesize answer for")
    llm_provider: str | None = Field(None, description="Optional target LLM provider")
    llm_model: str | None = Field(None, description="Optional target LLM model")

# Endpoints
@app.post("/remember")
async def api_remember(request: RememberRequest, auth=Depends(security_scheme)):
    # 1. Enforce Authentication
    authenticate_agent_id(request.agent_id, auth)
    
    # 2. Check memory class limits
    if request.memory_class not in ("episodic", "library"):
        raise HTTPException(status_code=400, detail="memory_class must be 'episodic' or 'library'")
        
    # 3. Check for external document injections
    if not validate_external_input(request.content, request.source):
        raise HTTPException(status_code=400, detail="Write rejected due to potential instruction injection in content.")
        
    conn = get_db()
    try:
        new_id = await remember_with_conflict_check(
            conn=conn,
            agent_id=request.agent_id,
            memory_class=request.memory_class,
            memory_type=request.memory_type,
            content=request.content,
            source=request.source,
            explicit=True,
            llm_provider=request.llm_provider,
            llm_model=request.llm_model
        )
        return {"status": "success", "memory_id": new_id}
    except Exception as e:
        logger.error(f"Error in /remember endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/recall")
async def api_recall(request: RecallRequest, auth=Depends(security_scheme)):
    # 1. Enforce Authentication
    authenticate_agent_id(request.agent_id, auth)
    
    try:
        results = await hybrid_recall_with_rerank(
            query=request.query,
            agent_id=request.agent_id,
            final_k=request.top_k
        )
        # Strip internal search fields from api response for cleanliness
        cleaned_results = []
        for r in results:
            cleaned_results.append({
                "id": r["id"],
                "memory_class": r["memory_class"],
                "memory_type": r["memory_type"],
                "content": r["content"],
                "source": r["source"],
                "confidence": r["confidence"],
                "created_at": r["created_at"]
            })
        return {"status": "success", "results": cleaned_results}
    except Exception as e:
        logger.error(f"Error in /recall endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/answer")
async def api_answer(request: AnswerRequest, auth=Depends(security_scheme)):
    # 1. Enforce Authentication
    authenticate_agent_id(request.agent_id, auth)
    
    try:
        # Step A: Hybrid Recall relevant memories
        results = await hybrid_recall_with_rerank(
            query=request.query,
            agent_id=request.agent_id,
            final_k=8
        )
        
        # Step B: Wrap memories in injection protection delimiters
        prompt = build_answer_prompt(request.query, results)
        
        # Step C: Synthesize answer via fallback LLM client
        answer = await generate_answer(
            query=prompt,
            provider=request.llm_provider,
            model=request.llm_model
        )
        
        cleaned_sources = [
            {
                "id": r["id"],
                "memory_type": r["memory_type"],
                "content": r["content"],
                "confidence": r["confidence"]
            }
            for r in results
        ]
        
        return {
            "status": "success",
            "answer": answer,
            "sources": cleaned_sources
        }
    except Exception as e:
        logger.error(f"Error in /answer endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def api_health():
    conn = get_db()
    try:
        # Check SQLite connectivity
        conn.execute("SELECT 1").fetchone()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    finally:
        conn.close()
        
    return {
        "status": "healthy",
        "database": db_status
    }

@app.get("/")
def api_dashboard():
    return FileResponse("index.html")

