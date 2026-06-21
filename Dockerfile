FROM ghcr.io/astral-sh/uv:python3.11-alpine

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files first for caching layers
COPY pyproject.toml /app/

# Install the project's dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source code
COPY . /app

# Initialize application and pre-download Hugging Face models during image build
# This avoids cold-start latency when real users hit retrieval queries
RUN uv run python -c "from retrieval import get_embedder, get_reranker; get_embedder(); get_reranker()"

# Expose FastAPI REST port
EXPOSE 8000

# Command to run uvicorn in production
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
