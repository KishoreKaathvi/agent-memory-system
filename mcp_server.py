import os
import sys
import logging
from mcp.server.fastmcp import FastMCP
from database import get_db
from conflict import remember_with_conflict_check
from retrieval import hybrid_recall_with_rerank
from security import verify_agent_access, validate_external_input

# Configure basic logging to stderr so it does not interfere with MCP stdout transport
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("memory.mcp_server")

# Initialize FastMCP Server
mcp = FastMCP("agent-memory")

@mcp.tool()
async def remember(agent_id: str, memory_class: str, memory_type: str, content: str, api_key: str, source: str = "mcp_client") -> str:
    """
    Store a new episodic or library memory event. Runs semantic conflict detection
    and tenant namespace verification.
    
    Parameters:
    - agent_id: Identifier of the target agent/namespace.
    - memory_class: Either 'episodic' (for interactions, decisions, observations) or 'library' (documents, static context).
    - memory_type: Subtype of memory (e.g. 'decision', 'preference', 'fact', 'event', 'commitment').
    - content: The actual fact, decision or description text to remember.
    - api_key: Authorization token for the agent's namespace.
    - source: Provenance source (default: 'mcp_client').
    """
    if memory_class not in ("episodic", "library"):
        return f"Error: memory_class must be either 'episodic' or 'library'. Received: '{memory_class}'"

    # Scan for potential prompt injection attempts in incoming content
    if not validate_external_input(content, source):
        return "Error: Memory write rejected due to potential instruction injection pattern."

    conn = get_db()
    try:
        # Enforce multi-tenant namespace isolation
        try:
            verify_agent_access(conn, agent_id, api_key)
        except PermissionError as pe:
            return f"Error: Permission denied. {str(pe)}"

        # Perform insertion with contradiction check
        new_id = await remember_with_conflict_check(
            conn=conn,
            agent_id=agent_id,
            memory_class=memory_class,
            memory_type=memory_type,
            content=content,
            source=source,
            explicit=True
        )
        
        return f"Success: Memory recorded with ID {new_id} in agent '{agent_id}' namespace."
    except Exception as e:
        logger.error(f"Error executing remember tool: {str(e)}", exc_info=True)
        return f"Error: Failed to record memory. details: {str(e)}"
    finally:
        conn.close()

@mcp.tool()
async def recall(agent_id: str, query: str, api_key: str, top_k: int = 8) -> str:
    """
    Retrieve relevant historical context using Vector + BM25 hybrid search and CrossEncoder reranking.
    
    Parameters:
    - agent_id: Identifier of the target agent/namespace.
    - query: Natural language search term.
    - api_key: Authorization token for the agent's namespace.
    - top_k: Number of ranked context items to return (default: 8).
    """
    conn = get_db()
    try:
        # Enforce multi-tenant namespace isolation
        try:
            verify_agent_access(conn, agent_id, api_key)
        except PermissionError as pe:
            return f"Error: Permission denied. {str(pe)}"

        # Run hybrid retrieval + reranking
        results = await hybrid_recall_with_rerank(
            query=query,
            agent_id=agent_id,
            final_k=top_k
        )
        
        if not results:
            return f"No relevant memories found for query '{query}' in namespace '{agent_id}'."
            
        # Format response
        formatted_memories = []
        for idx, m in enumerate(results):
            formatted_memories.append(
                f"[{idx + 1}] (Confidence: {m['confidence']:.2f}, Type: {m['memory_type']}, Created: {m['created_at']})\n"
                f"Content: {m['content']}"
            )
            
        return "\n\n".join(formatted_memories)
    except Exception as e:
        logger.error(f"Error executing recall tool: {str(e)}", exc_info=True)
        return f"Error: Failed to recall context. details: {str(e)}"
    finally:
        conn.close()

if __name__ == "__main__":
    # Start the stdin/stdout MCP server loop
    mcp.run()
