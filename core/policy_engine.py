"""
Bank Fraud Policy Engine (Version 1.0)
Implements Bank Policies R1 through R10, approval routing (auto, L1, L2),
exposure calculation, and SAR threshold validation.
"""

from typing import List, Tuple, Optional, Dict, Any
from core.models import PolicyAction, SARReport, EvidenceRequest


class PolicyEngine:
    """
    Evaluates investigation findings against Bank Fraud Policy Rules R1 - R10
    and outputs compliant PolicyAction lists with correct approval routing.
    """

    @staticmethod
    def get_approval_route(action: str, exposure_usd: float = 0.0) -> str:
        """Determines the required approval route (auto, L1, L2)."""
        if action == "BLOCK_ALL_CARDS" or action == "FILE_REPORT":
            return "L2"
        if action == "BLOCK_CARD":
            return "L2" if exposure_usd > 2500.0 else "L1"
        if action == "DECLINE_TRANSACTION":
            return "L1"
        return "auto"

    @classmethod
    def evaluate_initial_actions(
        cls,
        verdict: str,
        fraud_probability: float,
        pattern: str,
        exposure_usd: float,
        trigger_type: str,
        trigger_text: str,
        is_single_signal: bool,
        is_testing_sequence: bool = False,
        testing_large_cleared: bool = False,
        is_shared_device_ring: bool = False,
        is_recurring_dispute: bool = False,
        conflicting_evidence: bool = False,
        connected_cards: List[str] = None
    ) -> List[PolicyAction]:
        """
        Calculates initial next best actions BEFORE any evidence requests are simulated.
        """
        actions: List[PolicyAction] = []
        connected_cards = connected_cards or []

        # R7: Disputed recurring charge
        if is_recurring_dispute:
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="R7: Customer disputed charge matches historical recurring billing pattern; opening case for reconciliation"
            ))
            actions.append(PolicyAction(
                action="VERIFY_WITH_CUSTOMER",
                route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                reason="R7: Verify whether recurring subscription was cancelled with merchant prior to billing"
            ))
            actions.append(PolicyAction(
                action="WARN_CUSTOMER",
                route=cls.get_approval_route("WARN_CUSTOMER"),
                reason="R7: Provide customer with recurring charge management guidelines and merchant contact"
            ))
            return actions

        # R5: Card testing sequence
        if pattern == "card_testing" or is_testing_sequence:
            actions.append(PolicyAction(
                action="DECLINE_TRANSACTION",
                route=cls.get_approval_route("DECLINE_TRANSACTION"),
                reason="R5: Card testing sequence identified; decline pending authorization"
            ))
            if testing_large_cleared or exposure_usd > 100.0:
                actions.append(PolicyAction(
                    action="BLOCK_CARD",
                    route=cls.get_approval_route("BLOCK_CARD", exposure_usd),
                    reason=f"R5: High-value transaction (${exposure_usd:.2f} > $100) cleared following test authorizations; block compromised card"
                ))
            else:
                actions.append(PolicyAction(
                    action="STEP_UP_AUTH",
                    route=cls.get_approval_route("STEP_UP_AUTH"),
                    reason="R5: Rapid test authorizations observed; require step-up authentication before clearing"
                ))
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="R5: Card testing represents automated authorization attack; document case"
            ))
            return actions

        # R6: Shared origin / Fraud Ring
        if is_shared_device_ring or (connected_cards and len(connected_cards) > 0 and pattern in ["card_not_present_new_device", "account_takeover", "undocumented"]):
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="R6: Coordinated fraud ring detected sharing device profile across multiple cardholders"
            ))
            actions.append(PolicyAction(
                action="VERIFY_WITH_CUSTOMER",
                route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                reason="R1: Verify cardholder authorization while identifying compromised ring scope"
            ))
            actions.append(PolicyAction(
                action="MONITOR_CONNECTED_CARDS",
                route=cls.get_approval_route("MONITOR_CONNECTED_CARDS"),
                reason="R6: Elevate monitoring sensitivity on all cards sharing the identified device infrastructure"
            ))
            return actions

        # Customer report trigger: customer already alerted us
        if trigger_type == "customer_report":
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="Policy 3a: Open internal fraud investigation upon customer claim of unauthorized charge"
            ))
            if is_single_signal and fraud_probability < 0.70:
                actions.append(PolicyAction(
                    action="VERIFY_WITH_CUSTOMER",
                    route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                    reason="R1: Single claim with ambiguous indicators; confirm transaction circumstances and card possession"
                ))
            else:
                actions.append(PolicyAction(
                    action="VERIFY_WITH_CUSTOMER",
                    route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                    reason="R1: Gather formal confirmation of card possession and transaction denial before executing block"
                ))
            return actions

        # Risk score triggers / Weak single signal
        if is_single_signal and fraud_probability < 0.70:
            actions.append(PolicyAction(
                action="VERIFY_WITH_CUSTOMER",
                route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                reason=f"R1: Assessed fraud probability {fraud_probability:.2f} < 0.70 rests on single signal; verify before blocking"
            ))
            if fraud_probability >= 0.30:
                actions.append(PolicyAction(
                    action="CREATE_CASE",
                    route=cls.get_approval_route("CREATE_CASE"),
                    reason="Policy 3a: Fraud probability exceeds 0.30 threshold; open case to preserve evidence"
                ))
            return actions

        # High confidence fraud detected initially
        if fraud_probability >= 0.70:
            actions.append(PolicyAction(
                action="DECLINE_TRANSACTION",
                route=cls.get_approval_route("DECLINE_TRANSACTION"),
                reason="R1: Multi-signal fraud pattern identified with probability >= 0.70; decline pending authorization"
            ))
            actions.append(PolicyAction(
                action="VERIFY_WITH_CUSTOMER",
                route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
                reason="R1: Confirm unauthorized status with cardholder before permanent card block"
            ))
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="Policy 3a: Strong fraud indicators observed; create internal investigation case"
            ))
            return actions

        # Legitimate verdict initially
        if fraud_probability <= 0.15:
            actions.append(PolicyAction(
                action="ALLOW_TRANSACTION",
                route=cls.get_approval_route("ALLOW_TRANSACTION"),
                reason="Policy 1: Normal transaction consistent with cardholder behavioral baseline"
            ))
            actions.append(PolicyAction(
                action="CLOSE_NO_FRAUD",
                route=cls.get_approval_route("CLOSE_NO_FRAUD"),
                reason="R3: Activity verified legitimate; close alert without customer friction"
            ))
            return actions

        # Fallback uncertain
        actions.append(PolicyAction(
            action="VERIFY_WITH_CUSTOMER",
            route=cls.get_approval_route("VERIFY_WITH_CUSTOMER"),
            reason="R1: Inconclusive initial signals; prompt cardholder for validation"
        ))
        if exposure_usd > 500.0 or conflicting_evidence:
            actions.append(PolicyAction(
                action="ESCALATE_TO_ANALYST",
                route=cls.get_approval_route("ESCALATE_TO_ANALYST"),
                reason=f"R8: Uncertain verdict with exposure ${exposure_usd:.2f} > $500; escalate for manual review"
            ))
        return actions

    @classmethod
    def evaluate_final_actions(
        cls,
        verdict: str,
        fraud_probability: float,
        pattern: str,
        exposure_usd: float,
        customer_response: Optional[str],
        step_up_response: Optional[str],
        analyst_response: Optional[str],
        is_shared_device_ring: bool = False,
        is_recurring_dispute: bool = False,
        connected_cards: List[str] = None
    ) -> Tuple[List[PolicyAction], bool, str]:
        """
        Calculates final next best actions AFTER evidence response is evaluated.
        Returns: (final_actions, should_file_sar, sar_reason)
        """
        actions: List[PolicyAction] = []
        connected_cards = connected_cards or []
        should_file_sar = False
        sar_reason = ""

        # R7: Disputed recurring charge
        if is_recurring_dispute:
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="R7: Case maintained for documentation of merchant subscription billing dispute"
            ))
            actions.append(PolicyAction(
                action="WARN_CUSTOMER",
                route=cls.get_approval_route("WARN_CUSTOMER"),
                reason="R7: Customer confirmed recurring charge; sent merchant cancellation advice, card remains unblocked"
            ))
            return actions, False, ""

        # Case confirmed legitimate (customer confirmed or travel confirmed)
        if verdict == "legitimate" or (customer_response and "confirmed" in customer_response.lower() and "not" not in customer_response.lower()):
            actions.append(PolicyAction(
                action="ALLOW_TRANSACTION",
                route=cls.get_approval_route("ALLOW_TRANSACTION"),
                reason="Policy 1: Cardholder confirmed authentic transaction"
            ))
            actions.append(PolicyAction(
                action="CLOSE_NO_FRAUD",
                route=cls.get_approval_route("CLOSE_NO_FRAUD"),
                reason="R3: Customer confirmed transaction as legitimate; alert resolved and cleared"
            ))
            return actions, False, ""

        # Fraud Confirmed (customer denied, testing verified, or high probability)
        is_denied = customer_response and any(w in customer_response.lower() for w in ["denied", "not make", "never", "unrecognized", "stolen"])
        
        if verdict == "fraud" or is_denied or fraud_probability >= 0.70:
            actions.append(PolicyAction(
                action="BLOCK_CARD",
                route=cls.get_approval_route("BLOCK_CARD", exposure_usd),
                reason=f"R2: Customer denied transaction / unauthorized activity confirmed. Exposure ${exposure_usd:.2f}"
            ))
            actions.append(PolicyAction(
                action="CREATE_CASE",
                route=cls.get_approval_route("CREATE_CASE"),
                reason="R2: Formally open internal fraud case and record investigation graph vertex"
            ))

            # SAR Filing Criteria (Policy 3a & R2/R6/R9)
            # 1. Exposure > $1,000
            # 2. Shared device profile / connected cards fraud ring
            # 3. Coordinated / undocumented pattern (R9)
            has_shared_ring = is_shared_device_ring or len(connected_cards) > 0
            is_undocumented = (pattern == "undocumented")

            if exposure_usd > 1000.0 or has_shared_ring or is_undocumented:
                should_file_sar = True
                reasons = []
                if exposure_usd > 1000.0:
                    reasons.append(f"exposure of ${exposure_usd:.2f} exceeds regulatory filing threshold ($1,000)")
                if has_shared_ring:
                    reasons.append(f"activity links to shared device/ring infrastructure across {len(connected_cards)} connected card(s)")
                if is_undocumented:
                    reasons.append("pattern represents coordinated undocumented syndicate activity (R9)")
                sar_reason = "R2/Policy 3a: " + "; ".join(reasons)

                actions.append(PolicyAction(
                    action="FILE_REPORT",
                    route=cls.get_approval_route("FILE_REPORT"),
                    reason=sar_reason
                ))

            if has_shared_ring:
                actions.append(PolicyAction(
                    action="MONITOR_CONNECTED_CARDS",
                    route=cls.get_approval_route("MONITOR_CONNECTED_CARDS"),
                    reason=f"R6: Place connected card(s) {', '.join(connected_cards[:3])} under heightened 72h monitoring"
                ))

            return actions, should_file_sar, sar_reason

        # Uncertain Verdict
        actions.append(PolicyAction(
            action="MONITOR_CARD",
            route=cls.get_approval_route("MONITOR_CARD"),
            reason="R4/R8: Retain card under elevated 72h monitoring pending definitive resolution"
        ))
        if exposure_usd > 500.0:
            actions.append(PolicyAction(
                action="ESCALATE_TO_ANALYST",
                route=cls.get_approval_route("ESCALATE_TO_ANALYST"),
                reason=f"R8: Inconclusive findings with exposure ${exposure_usd:.2f} > $500; escalate to fraud analyst"
            ))
        return actions, False, ""
