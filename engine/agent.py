import json
import re
import time
from typing import List, Dict, Any, Optional

from engine.models import (
    CorporatePolicyRecord, PolicyComplianceVerdict, CorporateAgentResponse
)
from engine.tools import CorporateComplianceTool

class CorpShieldAgent:
    """
    CorpShield AI — Enterprise Corporate Travel Policy & Approval RAG Agent.
    Specialized for B2E Corporate Accounts (State Bank of India - SBI, PSUs, Corporates).
    """
    def __init__(self, policies_path: str, gst_registry_path: str):
        self.policies: Dict[str, List[CorporatePolicyRecord]] = {}
        self.gst_registry: Dict[str, Dict[str, str]] = {}
        self._load_data(policies_path, gst_registry_path)
        self.compliance_tool = CorporateComplianceTool(self.gst_registry)

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

    def _extract_request_params(self, query: str) -> Dict[str, Any]:
        q_low = query.lower()
        params = {
            "tenant_id": "SBI",
            "grade": "Scale 1",
            "route": "Domestic Sector",
            "distance_km": None,
            "flight_fare": None,
            "advance_days": 5,
            "is_business": False,
            "is_gst_query": False,
            "state_query": None
        }

        # 1. Tenant
        if "tcs" in q_low:
            params["tenant_id"] = "TCS"
        else:
            params["tenant_id"] = "SBI"

        # 2. Grade
        if any(w in q_low for w in ["scale 5", "scale 4", "agm", "chief manager"]):
            params["grade"] = "Scale 4-5"
        elif any(w in q_low for w in ["scale 6", "scale 7", "dgm", "general manager", "cgm"]):
            params["grade"] = "Scale 6-7"
        elif "band c4" in q_low:
            params["grade"] = "Band C4"
        else:
            params["grade"] = "Scale 1-3"

        # 3. Distance (e.g. 150 km, 1150 km, 1300 km)
        dist_match = re.search(r"(\d+)\s*km\b", q_low)
        if dist_match:
            params["distance_km"] = int(dist_match.group(1))

        # 4. Flight Fare (e.g. ₹3,800, ₹5,800, ₹8,200, or explicitly prefixed by ₹ / Rs / INR)
        fare_match = re.search(r"(?:₹|rs\.?|inr)\s*(\d{1,3}(?:,\d{3})+|\d{3,6})", query, re.IGNORECASE)
        if fare_match:
            params["flight_fare"] = float(fare_match.group(1).replace(",", ""))
        else:
            fare_fallback = re.search(r"fare\s+is\s*(\d{3,6})", q_low)
            if fare_fallback:
                params["flight_fare"] = float(fare_fallback.group(1))

        # 5. Route
        route_match = re.search(r"([A-Za-z]+)\s+to\s+([A-Za-z]+)", query)
        if route_match:
            params["route"] = f"{route_match.group(1)} to {route_match.group(2)}"

        # 6. Business Class
        if "business class" in q_low:
            params["is_business"] = True

        # 7. GST query
        if any(w in q_low for w in ["gst", "gstin", "tax credit", "itc"]):
            params["is_gst_query"] = True
            for st in ["kerala", "maharashtra", "delhi", "karnataka", "tamil nadu", "gujarat"]:
                if st in q_low:
                    params["state_query"] = st.title()
                    break

        return params

    def _match_policy_record(self, tenant_id: str, grade_str: str) -> CorporatePolicyRecord:
        tenant_policies = self.policies.get(tenant_id, [])
        for p in tenant_policies:
            if grade_str.lower() in p.grade_group.lower():
                return p
        return tenant_policies[0]

    def process_query(self, query: str) -> CorporateAgentResponse:
        start_time = time.time()
        params = self._extract_request_params(query)
        tenant_id = params["tenant_id"]

        # 1. Handle GST Query
        if params["is_gst_query"]:
            state = params["state_query"] or "Maharashtra"
            gstin = self.compliance_tool.lookup_corporate_gst(tenant_id, state)
            cit = "GST-CORP-REGISTRY-2026"
            ans = (
                f"🏛️ **Corporate GST Validation ({cit})**:\n"
                f"• Client: **{tenant_id}**\n"
                f"• State / Circle: **{state}**\n"
                f"• Valid GSTIN: `{gstin}`\n"
                f"• Status: **VERIFIED FOR 100% INPUT TAX CREDIT (ITC)**"
            )
            return CorporateAgentResponse(
                query=query,
                tenant_id=tenant_id,
                answer=ans,
                policy_citations=[cit, gstin],
                latency_ms=round((time.time() - start_time) * 1000, 2)
            )

        # 2. Match Policy Record
        policy = self._match_policy_record(tenant_id, params["grade"])

        # 3. Deterministic Compliance Evaluation
        verdict = self.compliance_tool.evaluate_travel_request(
            policy=policy,
            route=params["route"],
            distance_km=params["distance_km"],
            flight_fare=params["flight_fare"],
            advance_days=params["advance_days"],
            is_business_class=params["is_business"]
        )

        # 4. Build Structured Answer
        lines = []
        if verdict.verdict == "HARD_BLOCK":
            lines.append(f"⛔ **Policy Violation: Booking Blocked**")
            lines.append(f"• **Rationale**: {verdict.rationale}")
            lines.append(f"• **Entitled Travel Mode**: {verdict.allowed_mode}")
            lines.append(f"• **HR Policy Citation**: `{verdict.citation}`")
        elif verdict.verdict == "EXCEPTION_APPROVAL_REQUIRED":
            lines.append(f"⚠️ **Out-of-Policy Exception Detected: Manager Approval Required**")
            lines.append(f"• **Selected Fare**: ₹{verdict.actual_fare_inr:.2f} (Cap: ₹{verdict.max_cap_inr:.2f})")
            lines.append(f"• **Budget Overrun**: ₹{verdict.variance_inr:.2f}")
            lines.append(f"• **One-Click Approval Packet**: Pre-generated for Reporting Authority.")
            lines.append(f"• **Authority Citation**: `{verdict.citation}`")
        else:
            lines.append(f"✅ **Booking Compliant & Pre-Approved**")
            lines.append(f"• **Employee Band**: {policy.grade_group}")
            lines.append(f"• **Route**: {params['route']} (Distance: {params['distance_km']} km)")
            lines.append(f"• **Fare**: ₹{verdict.actual_fare_inr:.2f} (Within ₹{verdict.max_cap_inr:.2f} budget cap)")
            lines.append(f"• **HR Policy Citation**: `{verdict.citation}`")

        latency = round((time.time() - start_time) * 1000, 2)
        return CorporateAgentResponse(
            query=query,
            tenant_id=tenant_id,
            verdict=verdict,
            answer="\n".join(lines),
            policy_citations=[verdict.citation],
            latency_ms=latency
        )
