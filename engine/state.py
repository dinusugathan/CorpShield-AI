from typing import TypedDict, List, Dict, Any, Optional

class CorpAgentState(TypedDict):
    """
    LangGraph State Schema for CorpShield AI (B2E Corporate Travel Compliance).
    """
    query: str
    tenant_id: str                      # "SBI", "TCS"
    grade: str                          # "Scale 1-3", "Scale 4-5", "Scale 6-7", "Band C4"
    route: str                          # e.g. "Delhi to Mumbai"
    distance_km: Optional[int]
    flight_fare: Optional[float]
    advance_days: int
    is_business: bool
    is_gst_query: bool
    state_query: Optional[str]
    policy_record: Optional[Dict[str, Any]]
    verdict: Optional[Dict[str, Any]]
    status: str                         # "PENDING_APPROVAL", "APPROVED", "HARD_BLOCKED", "GST_VERIFIED", "APPROVED_BY_MANAGER"
    approval_packet: Optional[Dict[str, Any]]
    manager_decision: Optional[str]     # "APPROVED", "REJECTED", None
    answer: str
    policy_citations: List[str]
    trace_steps: List[Dict[str, Any]]
