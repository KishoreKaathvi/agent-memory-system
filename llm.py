import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

# Setup provider logging
provider_logger = logging.getLogger("memory.llm_provider")
if not provider_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    provider_logger.addHandler(handler)
    provider_logger.setLevel(logging.INFO)

# Config keys and settings
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# Define fallback chain (model name, provider/base_url, API key)
FALLBACK_CHAIN = [
    # Primary: Llama 3.3 70B free model
    (DEFAULT_MODEL, "https://openrouter.ai/api/v1", OPENROUTER_API_KEY),
    # Secondary: Gemini 2.5 Flash free model on OpenRouter
    ("google/gemini-2.5-flash", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY),
    # Tertiary: Llama 3 8B free model on OpenRouter
    ("meta-llama/llama-3-8b-instruct:free", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY),
]

if NVIDIA_API_KEY:
    # If NVIDIA NIM key is supplied, insert it as another fallback options
    FALLBACK_CHAIN.append(
        ("nvidia/llama-3.1-nemotron-70b-instruct", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY)
    )

class AllProvidersExhaustedError(Exception):
    """Exception raised when all configured LLM models fail or are rate-limited."""
    pass

async def generate_answer(query: str, context_str: str = "", system_prompt: str = "") -> str:
    """
    Call the LLM fallback chain to generate an answer for the given prompt.
    Tries each configured model in sequence.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
        
    user_content = ""
    if context_str:
        user_content += f"Context:\n{context_str}\n\n"
    user_content += f"Query: {query}"
    
    messages.append({"role": "user", "content": user_content})
    
    # Run through fallback chain
    for model, base_url, api_key in FALLBACK_CHAIN:
        if not api_key:
            provider_logger.warning(f"Skipping model {model} due to missing API key.")
            continue
            
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Include site details for OpenRouter if available
        if "openrouter" in base_url:
            headers["HTTP-Referer"] = "https://github.com/google-deepmind/antigravity"
            headers["X-Title"] = "Antigravity Memory Layer"
            
        data = {
            "model": model,
            "messages": messages,
            "temperature": 0.1 # Low temperature for factual rollup/evaluation stability
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=data)
                
                if response.status_code == 429:
                    provider_logger.warning(f"Rate limited by {model} (429 status code). Falling back...")
                    continue
                    
                response.raise_for_status()
                res_data = response.json()
                answer = res_data["choices"][0]["message"]["content"]
                
                provider_logger.info(f"Success calling LLM provider: model={model}")
                return answer.strip()
                
        except httpx.HTTPStatusError as e:
            provider_logger.warning(f"HTTP error calling {model}: {e.response.status_code} - {e.response.text}. Falling back...")
            continue
        except Exception as e:
            provider_logger.warning(f"Error calling {model}: {str(e)}. Falling back...")
            continue
            
    # If we get here, all providers were exhausted
    provider_logger.error("All LLM providers in fallback chain exhausted.")
    raise AllProvidersExhaustedError("All free-tier LLM providers exhausted. Please check keys or rate limits.")

VALID_DECISIONS = {"supersede", "retain", "annotate"}

def parse_conflict_decision(raw_output: str) -> str:
    """
    Defensively parse the conflict checking output from LLM.
    Ensures that it maps exactly to one of ('supersede', 'retain', 'annotate').
    """
    cleaned = raw_output.strip().lower()
    for decision in VALID_DECISIONS:
        if decision in cleaned:
            return decision
    # Safe default: annotate and flag for human review
    return "annotate"
