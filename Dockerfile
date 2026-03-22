# InfraAgent -- Python backend
FROM python:3.11-slim AS base

WORKDIR /app

# Install system deps (build-essential for compiled Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first for better layer caching
COPY pyproject.toml .

# Install runtime dependencies plus Ollama provider (default LLM)
# We use a two-step approach: install deps, then copy source and install in
# editable mode so PYTHONPATH resolves all packages correctly.
RUN pip install --no-cache-dir ".[ollama]"

# Copy full source tree
COPY . .

# Re-install in editable mode so setuptools discovers the packages
RUN pip install --no-cache-dir -e ".[ollama]"

# Ensure `from config import settings` resolves from /app
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
