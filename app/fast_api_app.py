"""FastAPI production server with ADK runtime, A2A routes, HITL gate endpoints, and health check."""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from pydantic import BaseModel

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.guardrails.hitl import approval_gate
from app.memory.session_store import session_store
from app.memory.vector_store import vector_store
from app.observability.logging import app_logger

load_dotenv()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)
otel_to_cloud = os.getenv("OTEL_TO_CLOUD", "true").lower() == "true"

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        plugins=adk_app.plugins,
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    app_logger.info("FastAPI server started with ADK runner and A2A routes", agent_name=root_agent.name)
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=otel_to_cloud,
    lifespan=lifespan,
)
app.title = "video-editor-assistant"
app.description = "Production AI Video Editing Assistant API with ADK, VFX Compositing, and HITL Governance"


# -----------------------------------------------------------------------------
# HITL & Memory API Endpoints
# -----------------------------------------------------------------------------

class HITLDecisionRequest(BaseModel):
    approval_token: str


@app.post("/api/hitl/approve")
async def approve_hitl_action(req: HITLDecisionRequest):
    """Approves a high-stakes action awaiting Human-in-the-Loop confirmation."""
    success = approval_gate.approve(req.approval_token)
    if not success:
        raise HTTPException(status_code=404, detail="Approval token not found or already processed.")
    return {"status": "approved", "approval_token": req.approval_token}


@app.post("/api/hitl/reject")
async def reject_hitl_action(req: HITLDecisionRequest):
    """Rejects a high-stakes action awaiting Human-in-the-Loop confirmation."""
    success = approval_gate.reject(req.approval_token)
    if not success:
        raise HTTPException(status_code=404, detail="Approval token not found or already processed.")
    return {"status": "rejected", "approval_token": req.approval_token}


@app.get("/api/memory/session/{session_id}")
async def get_session_timeline_memory(session_id: str):
    """Retrieves the latest persisted timeline snapshot from SQLite."""
    state = session_store.load_latest_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No snapshot found for session '{session_id}'.")
    return {"session_id": session_id, "snapshot": state}


@app.get("/api/memory/search")
async def search_vfx_knowledge(query: str):
    """Searches vector store for VFX presets and composition guidelines."""
    results = vector_store.search(query, top_k=3)
    return {"query": query, "results": results}


@app.get("/healthz")
async def health_check():
    """Kubernetes / Cloud Run liveness probe."""
    return {"status": "healthy", "service": "video-editor-assistant", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
