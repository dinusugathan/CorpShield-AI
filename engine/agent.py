import json
import time
import uuid
from typing import List, Dict, Any, Optional

from engine.models import (
    CorporatePolicyRecord, PolicyComplianceVerdict, CorporateAgentResponse, ManagerApprovalPacket
)
from engine.tools import CorporateComplianceTool
from engine.graph import create_corp_graph

class CorpShieldAgent:
    """
    CorpShield AI — Enterprise Corporate Travel Policy & Approval Agent.
    Orchestrated via LangGraph State Machine with Human-in-the-Loop (HITL) Checkpointing.
    """
    def __init__(self, policies_path: str, gst_registry_path: str):
        self.policies: Dict[str, List[CorporatePolicyRecord]] = {}
        self.gst_registry: Dict[str, Dict[str, str]] = {}
        self._load_data(policies_path, gst_registry_path)
        
        self.compliance_tool = CorporateComplianceTool(self.gst_registry)
        # Compile LangGraph workflow with MemorySaver checkpointer
        self.graph = create_corp_graph(self.policies, self.gst_registry)

    def _load_data(self, pol_path: str, gst_path: str):
        with open(pol_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for item in raw:
                rec = CorporatePolicyRecord(**item)
                if rec.tenant_id not in self.policies:
                    self.policies[rec.tenant_id] = []
                self.policies[rec.tenant_id].append(rec)

        with open(gst_path, "r", encoding="utf-8") as f:
            self.gst_registry = json.load(f)

    def process_query(self, query: str, thread_id: Optional[str] = None) -> CorporateAgentResponse:
        """
        Executes query through the LangGraph State Machine.
        """
        start_time = time.time()
        active_thread = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": active_thread}}

        initial_state = {
            "query": query,
            "tenant_id": "SBI",
            "grade": "Scale 1-3",
            "route": "Domestic Sector",
            "distance_km": None,
            "flight_fare": None,
            "advance_days": 5,
            "is_business": False,
            "is_gst_query": False,
            "state_query": None,
            "policy_record": None,
            "verdict": None,
            "status": "APPROVED",
            "approval_packet": None,
            "manager_decision": None,
            "answer": "",
            "policy_citations": [],
            "trace_steps": []
        }

        # Invoke the LangGraph workflow
        final_state = self.graph.invoke(initial_state, config=config)

        # Reconstruct typed verdict if present
        verdict_obj: Optional[PolicyComplianceVerdict] = None
        v_dict = final_state.get("verdict")
        if v_dict:
            pkt_dict = final_state.get("approval_packet")
            pkt_obj = ManagerApprovalPacket(**pkt_dict) if pkt_dict else None
            verdict_obj = PolicyComplianceVerdict(
                verdict=v_dict.get("verdict", "COMPLIANT_APPROVED"),
                allowed_mode=v_dict.get("allowed_mode", "Economy"),
                max_cap_inr=v_dict.get("max_cap_inr"),
                actual_fare_inr=v_dict.get("actual_fare_inr"),
                variance_inr=v_dict.get("variance_inr"),
                approval_packet=pkt_obj,
                citation=v_dict.get("citation", "CORP-TRAVEL-POLICY-2025"),
                rationale=v_dict.get("rationale", "")
            )

        latency = round((time.time() - start_time) * 1000, 2)

        return CorporateAgentResponse(
            query=query,
            tenant_id=final_state.get("tenant_id", "SBI"),
            verdict=verdict_obj,
            answer=final_state.get("answer", ""),
            policy_citations=final_state.get("policy_citations", []),
            thread_id=active_thread,
            trace_steps=final_state.get("trace_steps", []),
            latency_ms=latency
        )

    def approve_manager_exception(self, thread_id: str) -> CorporateAgentResponse:
        """
        Human-in-the-Loop Resumption: Resumes graph with approved manager decision.
        """
        start_time = time.time()
        config = {"configurable": {"thread_id": thread_id}}

        # Update state with manager authorization and resume
        resume_state = {
            "manager_decision": "APPROVED",
            "status": "APPROVED_BY_MANAGER"
        }
        
        final_state = self.graph.invoke(resume_state, config=config)
        latency = round((time.time() - start_time) * 1000, 2)

        return CorporateAgentResponse(
            query="[HITL Manager Approval Action]",
            tenant_id=final_state.get("tenant_id", "SBI"),
            verdict=None,
            answer=final_state.get("answer", ""),
            policy_citations=final_state.get("policy_citations", []),
            thread_id=thread_id,
            trace_steps=final_state.get("trace_steps", []),
            latency_ms=latency
        )
