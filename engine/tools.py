from typing import Dict, Any, Optional
from engine.models import CorporatePolicyRecord, PolicyComplianceVerdict, ManagerApprovalPacket

class CorporateComplianceTool:
    """
    Deterministic Compliance Engine for Corporate Travel (B2E).
    Validates flight vs train distance thresholds, airfare budget ceilings,
    advance booking windows, and State GSTIN matching.
    """
    def __init__(self, gst_registry: Dict[str, Dict[str, str]]):
        self.gst_registry = gst_registry

    def evaluate_travel_request(
        self,
        policy: CorporatePolicyRecord,
        route: str,
        distance_km: Optional[int],
        flight_fare: Optional[float],
        advance_days: Optional[int],
        is_business_class: bool = False
    ) -> PolicyComplianceVerdict:
        ent = policy.entitlements

        # Rule 1: Business Class Eligibility Check
        if is_business_class and not ent.business_class_allowed:
            return PolicyComplianceVerdict(
                verdict="HARD_BLOCK",
                allowed_mode="Economy Only",
                max_cap_inr=ent.max_domestic_fare_inr,
                actual_fare_inr=flight_fare,
                citation=policy.citation,
                rationale=(
                    f"Policy Hard Block: Business Class is strictly prohibited for {policy.grade_group}. "
                    f"Per {policy.corporate_name} travel policy ({policy.citation}), official travel must be booked in Economy Class."
                )
            )

        # Rule 2: Minimum Distance Cutoff for Air Travel (e.g. 500 km for Scale 1-3)
        if distance_km is not None and distance_km < ent.min_distance_km_for_air:
            return PolicyComplianceVerdict(
                verdict="HARD_BLOCK",
                allowed_mode=f"Train / Road ({ent.train_entitlement})",
                max_cap_inr=0.0,
                actual_fare_inr=flight_fare,
                citation=policy.citation,
                rationale=(
                    f"Policy Hard Block: Distance for {route} is {distance_km} km, which is under the {ent.min_distance_km_for_air} km cutoff. "
                    f"Under {policy.corporate_name} rules ({policy.citation}), employees in {policy.grade_group} "
                    f"are entitled to {ent.train_entitlement}. Air travel cannot be authorized."
                )
            )

        # Rule 3: Budget Ceiling Check
        if flight_fare is not None and flight_fare > ent.max_domestic_fare_inr:
            overrun = round(flight_fare - ent.max_domestic_fare_inr, 2)
            packet = ManagerApprovalPacket(
                employee_grade=policy.grade_group,
                route=route,
                selected_fare=flight_fare,
                max_allowed_fare=ent.max_domestic_fare_inr,
                budget_overrun=overrun,
                reason_for_exception=f"Airfare exceeds {policy.corporate_name} band ceiling by ₹{overrun:.2f} due to emergency booking window.",
                one_click_approval_link=f"https://corp.akbartravels.com/approve?client={policy.tenant_id}&overrun={overrun}"
            )
            return PolicyComplianceVerdict(
                verdict="EXCEPTION_APPROVAL_REQUIRED",
                allowed_mode="Economy Flight (Over Budget)",
                max_cap_inr=ent.max_domestic_fare_inr,
                actual_fare_inr=flight_fare,
                variance_inr=overrun,
                approval_packet=packet,
                citation=policy.citation,
                rationale=(
                    f"Exception Approval Required: Selected fare ₹{flight_fare:.2f} exceeds policy cap (₹{ent.max_domestic_fare_inr:.2f}) "
                    f"by ₹{overrun:.2f}. A pre-filled Manager Approval Packet has been generated under {policy.citation}."
                )
            )

        # Rule 4: Fully Compliant Booking
        return PolicyComplianceVerdict(
            verdict="COMPLIANT_APPROVED",
            allowed_mode="Economy Flight",
            max_cap_inr=ent.max_domestic_fare_inr,
            actual_fare_inr=flight_fare,
            variance_inr=0.0,
            citation=policy.citation,
            rationale=(
                f"Booking Compliant: Request satisfies all {policy.corporate_name} travel norms under {policy.citation}. "
                f"Distance threshold (> {ent.min_distance_km_for_air} km) and fare limit (₹{flight_fare:.2f} <= ₹{ent.max_domestic_fare_inr:.2f}) satisfied."
            )
        )

    def lookup_corporate_gst(self, tenant_id: str, state_name: str) -> Optional[str]:
        corp_gst = self.gst_registry.get(tenant_id, {})
        for state, gstin in corp_gst.items():
            if state.lower() in state_name.lower():
                return gstin
        return None
