import re
import time
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from engine.state import CorpAgentState
from engine.models import (
    CorporatePolicyRecord, PolicyComplianceVerdict, ManagerApprovalPacket
)
from engine.tools import CorporateComplianceTool

def create_corp_graph(
    policies: Dict[str, List[CorporatePolicyRecord]], 
    gst_registry: Dict[str, Dict[str, str]]
):
    compliance_tool = CorporateComplianceTool(gst_registry)

    # -------------------------------------------------------------
    # Node 1: Tenant Router & Parameter Extraction Node
    # -------------------------------------------------------------
    def tenant_router_node(state: CorpAgentState) -> Dict[str, Any]:
        start = time.time()
        query = state["query"]
        q_low = query.lower()

        # 1. Tenant Isolation
        tenant_id = "TCS" if "tcs" in q_low else "SBI"

        # 2. Grade Group
        if any(w in q_low for w in ["scale 5", "scale 4", "agm", "chief manager"]):
            grade = "Scale 4-5"
        elif any(w in q_low for w in ["scale 6", "scale 7", "dgm", "general manager", "cgm"]):
            grade = "Scale 6-7"
        elif "band c4" in q_low:
            grade = "Band C4"
        else:
            grade = "Scale 1-3"

        # 3. Route Extraction
        route = "Domestic Sector"
        route_match = re.search(r"(?:from\s+)?([a-zA-Z\s]+)\s+(?:to|-)\s+([a-zA-Z\s]+)", query, re.IGNORECASE)
        if route_match:
            origin = route_match.group(1).strip().title()
            dest = route_match.group(2).strip().split()[0].title()
            route = f"{origin} to {dest}"

        # 4. Distance Extraction
        distance_km = None
        dist_match = re.search(r"(\d{3,4})\s*(?:km|kms|kilometers)\b", q_low)
        if dist_match:
            distance_km = int(dist_match.group(1))
        elif "mumbai" in q_low and "delhi" in q_low:
            distance_km = 1150
        elif "mumbai" in q_low and "pune" in q_low:
            distance_km = 150
        elif "bangalore" in q_low and "chennai" in q_low:
            distance_km = 350

        # 5. Fare Extraction (Do not match distance km as fare)
        flight_fare = None
        fare_match = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", query, re.IGNORECASE)
        if not fare_match:
            fare_match = re.search(r"(?:fare|ticket|price|is|at|for)\s+(?:is\s+)?(?:₹|rs\.?|inr)?\s*([\d,]+)(?!\s*(?:km|kms|kilometers|days|hours))", query, re.IGNORECASE)
        if fare_match:
            raw_num = fare_match.group(1).replace(",", "")
            flight_fare = float(raw_num)

        # 6. Business Class & GST Flags
        is_business = any(w in q_low for w in ["business class", "j class", "club"])
        is_gst_query = any(w in q_low for w in ["gst", "gstin", "tax credit", "itc"])

        state_query = None
        for state_name in ["Maharashtra", "Karnataka", "Delhi", "Tamil Nadu", "Gujarat", "West Bengal", "Telangana", "Kerala", "Kochi"]:
            if state_name.lower() in q_low:
                state_query = "Kerala" if state_name.lower() in ["kerala", "kochi"] else state_name
                break

        # Tenant-isolated policy lookup
        tenant_policies = policies.get(tenant_id, [])
        policy_rec = None
        for p in tenant_policies:
            if grade.lower() in p.grade_group.lower():
                policy_rec = p
                break
        if not policy_rec and tenant_policies:
            policy_rec = tenant_policies[0]

        trace = {
            "node": "tenant_router_node",
            "summary": f"Tenant: {tenant_id} | Grade: {grade} | Route: {route} | Dist: {distance_km}km | Fare: {flight_fare}",
            "duration_ms": round((time.time() - start) * 1000, 2)
        }

        return {
            "tenant_id": tenant_id,
            "grade": grade,
            "route": route,
            "distance_km": distance_km,
            "flight_fare": flight_fare,
            "is_business": is_business,
            "is_gst_query": is_gst_query,
            "state_query": state_query,
            "policy_record": policy_rec.model_dump() if policy_rec else None,
            "trace_steps": state.get("trace_steps", []) + [trace]
        }

    # -------------------------------------------------------------
    # Node 2: Compliance Evaluator Node
    # -------------------------------------------------------------
    def compliance_evaluator_node(state: CorpAgentState) -> Dict[str, Any]:
        start = time.time()
        pol_dict = state.get("policy_record")
        if not pol_dict:
            return {"status": "HARD_BLOCKED", "trace_steps": state.get("trace_steps", [])}

        policy = CorporatePolicyRecord(**pol_dict)
        verdict = compliance_tool.evaluate_travel_request(
            policy=policy,
            route=state["route"],
            distance_km=state["distance_km"],
            flight_fare=state["flight_fare"],
            advance_days=state.get("advance_days", 5),
            is_business_class=state.get("is_business", False)
        )

        status_map = {
            "COMPLIANT_APPROVED": "APPROVED",
            "HARD_BLOCK": "HARD_BLOCKED",
            "EXCEPTION_APPROVAL_REQUIRED": "PENDING_APPROVAL"
        }

        trace = {
            "node": "compliance_evaluator_node",
            "summary": f"Verdict: {verdict.verdict} | Allowed: {verdict.allowed_mode} | Citation: {verdict.citation}",
            "duration_ms": round((time.time() - start) * 1000, 2)
        }

        return {
            "verdict": verdict.model_dump(),
            "status": status_map.get(verdict.verdict, "PENDING_APPROVAL"),
            "approval_packet": verdict.approval_packet.model_dump() if verdict.approval_packet else None,
            "policy_citations": [verdict.citation],
            "trace_steps": state.get("trace_steps", []) + [trace]
        }

    # -------------------------------------------------------------
    # Node 3: Manager Approval Node (Human-in-the-Loop State)
    # -------------------------------------------------------------
    def manager_approval_node(state: CorpAgentState) -> Dict[str, Any]:
        start = time.time()
        packet = state.get("approval_packet") or {}
        decision = state.get("manager_decision")

        if decision == "APPROVED":
            status = "APPROVED_BY_MANAGER"
            summary = f"Human-in-the-Loop: Manager approved budget overrun of ₹{packet.get('budget_overrun', 0):,}"
        elif decision == "REJECTED":
            status = "HARD_BLOCKED"
            summary = "Human-in-the-Loop: Manager rejected exception request"
        else:
            status = "PENDING_APPROVAL"
            summary = f"HITL Intercept: Approval Packet generated for {packet.get('employee_grade')} (Overrun: ₹{packet.get('budget_overrun', 0):,})"

        trace = {
            "node": "manager_approval_node",
            "summary": summary,
            "duration_ms": round((time.time() - start) * 1000, 2)
        }

        return {
            "status": status,
            "trace_steps": state.get("trace_steps", []) + [trace]
        }

    # -------------------------------------------------------------
    # Node 4: GST Verification Node
    # -------------------------------------------------------------
    def gst_verification_node(state: CorpAgentState) -> Dict[str, Any]:
        start = time.time()
        state_name = state.get("state_query") or "Maharashtra"
        tenant_id = state.get("tenant_id", "SBI")
        gst_result = compliance_tool.verify_state_gstin(tenant_id=tenant_id, state_name=state_name)

        trace = {
            "node": "gst_verification_node",
            "summary": f"GST Verified for {tenant_id} {state_name}: {gst_result.get('gstin')}",
            "duration_ms": round((time.time() - start) * 1000, 2)
        }

        return {
            "status": "GST_VERIFIED",
            "verdict": {
                "verdict": "GST_VERIFIED",
                "allowed_mode": "GST_AUDIT_PASSED",
                "citation": gst_result.get("citation", "GSTIN-MATCH-RULE"),
                "rationale": f"Verified valid GSTIN: {gst_result.get('gstin')} for {gst_result.get('state')}"
            },
            "policy_citations": [gst_result.get("citation", "GSTIN-MATCH-RULE")],
            "trace_steps": state.get("trace_steps", []) + [trace]
        }

    # -------------------------------------------------------------
    # Node 5: Structured Synthesis Node
    # -------------------------------------------------------------
    def synthesis_node(state: CorpAgentState) -> Dict[str, Any]:
        start = time.time()
        status = state.get("status", "APPROVED")
        verdict = state.get("verdict") or {}
        pol_dict = state.get("policy_record") or {}
        pol_citation = pol_dict.get("citation", "CORP-TRAVEL-POLICY-2025")

        if status == "GST_VERIFIED":
            tenant_id = state.get("tenant_id", "SBI")
            state_name = state.get("state_query") or "Maharashtra"
            gst_res = compliance_tool.verify_state_gstin(tenant_id=tenant_id, state_name=state_name)
            answer = (
                f"🧾 **Akbar Travels B2E GST Audit Verification ({gst_res.get('citation')})**:\n"
                f"• Client: **{gst_res.get('entity_name')}** ({tenant_id})\n"
                f"• Booking State Jurisdiction: **{gst_res.get('state')}**\n"
                f"• Registered Entity GSTIN: `{gst_res.get('gstin')}`\n"
                f"• Input Tax Credit (ITC) Status: **VERIFIED FOR 100% INPUT TAX CREDIT RECOVERY**\n\n"
                f"*Mandatory Compliance*: All airline GDS PNRs issued under this B2E account must have `{gst_res.get('gstin')}` appended to SSR GST tags."
            )
        elif status == "HARD_BLOCKED":
            answer = (
                f"🚫 **Booking Authorization Blocked: Policy Violation**\n\n"
                f"**Verdict**: `HARD_BLOCK`\n"
                f"**Mandated Travel Mode**: {verdict.get('allowed_mode', 'Train / Road')}\n"
                f"**Reason**: {verdict.get('rationale', 'Request violates corporate travel guidelines.')}\n\n"
                f"• **Governing Circular**: `[{verdict.get('citation', pol_citation)}]`\n"
                f"• *Remediation*: Please rebook using designated travel mode or request official grade re-classification."
            )
        elif status == "APPROVED_BY_MANAGER":
            packet = state.get("approval_packet") or {}
            answer = (
                f"✅ **Booking Authorized via Manager Exception Approval**\n\n"
                f"**Employee Grade**: `{state.get('grade')}` | **Route**: `{state.get('route')}`\n"
                f"**Approved Airfare**: ₹{packet.get('selected_fare', 0):,} (Overrun: ₹{packet.get('budget_overrun', 0):,})\n"
                f"**Authorization Status**: `APPROVED_BY_MANAGER`\n"
                f"**Audit Trail Reference**: `[{verdict.get('citation', pol_citation)}]`\n\n"
                f"The booking order has been unlocked for GDS ticketing."
            )
        elif status == "PENDING_APPROVAL":
            packet = state.get("approval_packet") or {}
            answer = (
                f"⚠️ **Exception Approval Required (Budget Overrun)**\n\n"
                f"**Status**: `EXCEPTION_APPROVAL_REQUIRED` (Pending Human-in-the-Loop Review)\n"
                f"• Selected Fare: **₹{packet.get('selected_fare', 0):,}**\n"
                f"• Maximum Allowed Fare Cap: **₹{packet.get('max_allowed_fare', 0):,}**\n"
                f"• Budget Variance / Overrun: **+₹{packet.get('budget_overrun', 0):,}**\n\n"
                f"**Manager Approval Packet:**\n"
                f"• Reason: {packet.get('reason_for_exception')}\n"
                f"• One-Click Manager Approval Link: `{packet.get('one_click_approval_link')}`\n\n"
                f"• **Policy Citation**: `[{verdict.get('citation', pol_citation)}]`"
            )
        else: # APPROVED
            answer = (
                f"✅ **Booking Pre-Approved: Fully Policy Compliant**\n\n"
                f"**Verdict**: `COMPLIANT_APPROVED`\n"
                f"• Employee Grade: `{state.get('grade')}`\n"
                f"• Authorized Cabin: `{verdict.get('allowed_mode', 'Economy Class')}`\n"
                f"• Selected Fare: ₹{state.get('flight_fare', 0):,} (Policy Cap: ₹{verdict.get('max_cap_inr', 0):,})\n\n"
                f"• **Governing Authority**: `[{verdict.get('citation', pol_citation)}]`"
            )

        trace = {
            "node": "synthesis_node",
            "summary": f"Final Status: {status} | Citations: {state.get('policy_citations', [])}",
            "duration_ms": round((time.time() - start) * 1000, 2)
        }

        return {
            "answer": answer,
            "trace_steps": state.get("trace_steps", []) + [trace]
        }

    # -------------------------------------------------------------
    # Build Graph & Routing Logic
    # -------------------------------------------------------------
    workflow = StateGraph(CorpAgentState)

    workflow.add_node("tenant_router_node", tenant_router_node)
    workflow.add_node("compliance_evaluator_node", compliance_evaluator_node)
    workflow.add_node("manager_approval_node", manager_approval_node)
    workflow.add_node("gst_verification_node", gst_verification_node)
    workflow.add_node("synthesis_node", synthesis_node)

    # Routing condition from Router
    def route_after_router(state: CorpAgentState) -> str:
        if state.get("is_gst_query"):
            return "gst_verification_node"
        return "compliance_evaluator_node"

    # Routing condition after Compliance Evaluator
    def route_after_evaluator(state: CorpAgentState) -> str:
        status = state.get("status")
        if status == "PENDING_APPROVAL":
            return "manager_approval_node"
        return "synthesis_node"

    workflow.add_edge(START, "tenant_router_node")
    workflow.add_conditional_edges("tenant_router_node", route_after_router)
    workflow.add_conditional_edges("compliance_evaluator_node", route_after_evaluator)
    workflow.add_edge("manager_approval_node", "synthesis_node")
    workflow.add_edge("gst_verification_node", "synthesis_node")
    workflow.add_edge("synthesis_node", END)

    # Use checkpointer for session persistence
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
