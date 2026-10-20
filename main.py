import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel

from engine.agent import CorpShieldAgent
from engine.models import CorporateAgentResponse
from evals.run_evals import run_corporate_benchmark

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POL_PATH = os.path.join(BASE_DIR, "data", "corporate_policies.json")
GST_PATH = os.path.join(BASE_DIR, "data", "corporate_gst_registry.json")
EVAL_PATH = os.path.join(BASE_DIR, "evals", "benchmark_report.json")
STATIC_DIR = os.path.join(BASE_DIR, "web")

app = FastAPI(
    title="CorpShield AI — Enterprise Corporate Travel Policy & Approval RAG Agent",
    version="1.0.0",
    description="Akbar Travels B2E corporate travel policy engine for State Bank of India (SBI) and corporate accounts."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Agent
agent = CorpShieldAgent(POL_PATH, GST_PATH)

class CorporateQueryRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None

class ManagerApprovalRequest(BaseModel):
    thread_id: str

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "CorpShield AI (LangGraph HITL State Machine)",
        "clients": list(agent.policies.keys()),
        "total_policies": sum(len(v) for v in agent.policies.values())
    }

@app.post("/api/chat", response_model=CorporateAgentResponse)
def handle_corporate_query(payload: CorporateQueryRequest):
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    return agent.process_query(payload.query.strip(), thread_id=payload.thread_id)

@app.post("/api/approval/approve", response_model=CorporateAgentResponse)
def handle_manager_approval(payload: ManagerApprovalRequest):
    if not payload.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required to resume HITL state.")
    return agent.approve_manager_exception(payload.thread_id)

@app.get("/api/policies")
def get_policies():
    with open(POL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/gst-registry")
def get_gst_registry():
    with open(GST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/evals")
def get_evals():
    if not os.path.exists(EVAL_PATH):
        return run_corporate_benchmark(POL_PATH, GST_PATH, output_report_path=EVAL_PATH)
    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/evals/run")
def trigger_evals():
    return run_corporate_benchmark(POL_PATH, GST_PATH, output_report_path=EVAL_PATH)

# Serve Web Frontend
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Project 4 runs on port 8003
    uvicorn.run("main:app", host="127.0.0.1", port=8003, reload=True)
