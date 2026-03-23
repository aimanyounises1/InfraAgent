"""FastAPI application -- REST API + WebSocket for InfraAgent.

Run:
    uvicorn api.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.logging_config import setup_logging
from api.middleware.correlation import CorrelationMiddleware
from config import settings

# Initialise structured logging before anything else.
setup_logging(level="INFO")

app = FastAPI(
    title="InfraAgent API",
    description="Agentic AI Platform for Infrastructure Operations",
    version="2.0.0",
)

# --- Middleware (order matters: outermost first) ---
app.add_middleware(CorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# --- Route imports ---
from api.routes import chat, gpu, incidents, k8s, llm  # noqa: F401, E402
from api.websocket import ws_router  # noqa: E402

app.include_router(k8s.router, prefix="/api/k8s", tags=["Kubernetes"])
app.include_router(gpu.router, prefix="/api/gpu", tags=["GPU"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["Incidents"])
app.include_router(llm.router, prefix="/api/llm", tags=["LLM"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(ws_router)


@app.get("/healthz")
async def healthz() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "infra-agent", "version": "2.0.0"}
