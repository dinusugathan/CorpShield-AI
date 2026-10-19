from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class CorporateEntitlement(BaseModel):
    air_travel_eligibility: str
    min_distance_km_for_air: int
    cabin_class: str
    business_class_allowed: bool
    max_domestic_fare_inr: float
    min_advance_booking_days: int
    train_entitlement: str
    daily_hotel_allowance_tier1: float
    daily_hotel_allowance_other: float

class CorporatePolicyRecord(BaseModel):
    tenant_id: str
    corporate_name: str
    grade_group: str
    entitlements: CorporateEntitlement
    gst_mandate: str
    citation: str

class ManagerApprovalPacket(BaseModel):
    employee_grade: str
    route: str
    selected_fare: float
    max_allowed_fare: float
    budget_overrun: float
    reason_for_exception: str
    one_click_approval_link: str

class PolicyComplianceVerdict(BaseModel):
    verdict: str                        # COMPLIANT_APPROVED, HARD_BLOCK, EXCEPTION_APPROVAL_REQUIRED, GST_VERIFIED
    allowed_mode: str
    max_cap_inr: Optional[float] = None
    actual_fare_inr: Optional[float] = None
    variance_inr: Optional[float] = None
    approval_packet: Optional[ManagerApprovalPacket] = None
    citation: str
    rationale: str

class CorporateAgentResponse(BaseModel):
    query: str
    tenant_id: str
    verdict: Optional[PolicyComplianceVerdict] = None
    answer: str
    policy_citations: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0

class CorpEvalCaseResult(BaseModel):
    test_id: str
    passed: bool
    verdict_matched: bool
    citation_matched: bool
    latency_ms: float
    details: str
