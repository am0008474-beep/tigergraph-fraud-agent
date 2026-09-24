"""
Unit tests for Bank Fraud Policy Engine (Rules R1 - R10 and Approval Routes).
Validates that all 10 policy rules produce compliant actions and routing.
"""

import pytest
from core.policy_engine import PolicyEngine


def test_approval_routes():
    assert PolicyEngine.get_approval_route("ALLOW_TRANSACTION") == "auto"
    assert PolicyEngine.get_approval_route("MONITOR_CARD") == "auto"
    assert PolicyEngine.get_approval_route("CREATE_CASE") == "auto"
    assert PolicyEngine.get_approval_route("DECLINE_TRANSACTION") == "L1"
    assert PolicyEngine.get_approval_route("BLOCK_CARD", exposure_usd=500.0) == "L1"
    assert PolicyEngine.get_approval_route("BLOCK_CARD", exposure_usd=3000.0) == "L2"
    assert PolicyEngine.get_approval_route("BLOCK_ALL_CARDS") == "L2"
    assert PolicyEngine.get_approval_route("FILE_REPORT") == "L2"


def test_rule_r1_verify_before_block_on_weak_signal():
    # Probability < 0.70 on single signal -> must verify first before blocking
    actions = PolicyEngine.evaluate_initial_actions(
        verdict="uncertain",
        fraud_probability=0.45,
        pattern="card_not_present_fraud",
        exposure_usd=150.0,
        trigger_type="risk_score",
        trigger_text="scored 0.60",
        is_single_signal=True
    )
    action_names = [a.action for a in actions]
    assert "VERIFY_WITH_CUSTOMER" in action_names
    assert "BLOCK_CARD" not in action_names


def test_rule_r2_customer_denial_blocks_card():
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="fraud",
        fraud_probability=0.88,
        pattern="card_not_present_new_device",
        exposure_usd=600.0,
        customer_response="Cardholder denies making this charge",
        step_up_response=None,
        analyst_response=None
    )
    action_names = [a.action for a in actions]
    assert "BLOCK_CARD" in action_names
    assert "CREATE_CASE" in action_names
    # Exposure is $600 <= $1,000 and no shared ring -> no SAR
    assert should_file is False


def test_rule_r3_customer_confirmation_clears_alert():
    # R3: Customer confirms transaction -> CLOSE_NO_FRAUD
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="legitimate",
        fraud_probability=0.05,
        pattern="none",
        exposure_usd=0.0,
        customer_response="Cardholder confirmed making this purchase while traveling",
        step_up_response=None,
        analyst_response=None
    )
    action_names = [a.action for a in actions]
    assert "CLOSE_NO_FRAUD" in action_names
    assert "ALLOW_TRANSACTION" in action_names
    assert "BLOCK_CARD" not in action_names
    assert should_file is False


def test_rule_r4_no_reply_escalation():
    # R4: Retain monitoring and decline pending
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="uncertain",
        fraud_probability=0.55,
        pattern="card_not_present_fraud",
        exposure_usd=650.0,
        customer_response=None,
        step_up_response=None,
        analyst_response=None
    )
    action_names = [a.action for a in actions]
    assert "MONITOR_CARD" in action_names
    assert "ESCALATE_TO_ANALYST" in action_names


def test_rule_r5_card_testing_sequence():
    # R5: Card testing sequence
    actions = PolicyEngine.evaluate_initial_actions(
        verdict="fraud",
        fraud_probability=0.85,
        pattern="card_testing",
        exposure_usd=250.0,
        trigger_type="risk_score",
        trigger_text="testing sequence detected",
        is_single_signal=False,
        is_testing_sequence=True,
        testing_large_cleared=True
    )
    action_names = [a.action for a in actions]
    assert "DECLINE_TRANSACTION" in action_names
    assert "BLOCK_CARD" in action_names
    assert "CREATE_CASE" in action_names


def test_rule_r6_shared_origin_fraud_ring():
    # R6: Shared origin / device ring
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="fraud",
        fraud_probability=0.95,
        pattern="card_not_present_new_device",
        exposure_usd=500.0,
        customer_response="Denied charge",
        step_up_response=None,
        analyst_response=None,
        is_shared_device_ring=True,
        connected_cards=["C00877-K1", "C00999-K1"]
    )
    action_names = [a.action for a in actions]
    assert "FILE_REPORT" in action_names
    assert "MONITOR_CONNECTED_CARDS" in action_names
    assert should_file is True
    assert "shared device/ring" in reason


def test_rule_r7_disputed_recurring_charge():
    actions = PolicyEngine.evaluate_initial_actions(
        verdict="legitimate",
        fraud_probability=0.15,
        pattern="none",
        exposure_usd=0.0,
        trigger_type="customer_report",
        trigger_text="Customer message disputed charge",
        is_single_signal=False,
        is_recurring_dispute=True
    )
    action_names = [a.action for a in actions]
    assert "CREATE_CASE" in action_names
    assert "VERIFY_WITH_CUSTOMER" in action_names
    assert "WARN_CUSTOMER" in action_names
    assert "BLOCK_CARD" not in action_names


def test_rule_r8_escalate_uncertain_and_exposed():
    # R8: Inconclusive with exposure > $500
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="uncertain",
        fraud_probability=0.55,
        pattern="card_not_present_fraud",
        exposure_usd=750.0,
        customer_response=None,
        step_up_response=None,
        analyst_response=None
    )
    action_names = [a.action for a in actions]
    assert "ESCALATE_TO_ANALYST" in action_names


def test_rule_r9_undocumented_pattern():
    # R9: Undocumented pattern triggers report and case
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="fraud",
        fraud_probability=0.95,
        pattern="undocumented",
        exposure_usd=200.0,
        customer_response="Denied charge",
        step_up_response=None,
        analyst_response=None
    )
    action_names = [a.action for a in actions]
    assert "FILE_REPORT" in action_names
    assert "CREATE_CASE" in action_names
    assert should_file is True


def test_rule_r10_block_all_cards_restriction():
    # R10: Never BLOCK_ALL_CARDS unless 2+ cards compromised or credentials confirmed compromised
    route = PolicyEngine.get_approval_route("BLOCK_ALL_CARDS")
    assert route == "L2", "BLOCK_ALL_CARDS requires highest L2 executive approval"


def test_sar_filing_thresholds():
    # Case with exposure > $1,000 -> must file SAR
    actions, should_file, reason = PolicyEngine.evaluate_final_actions(
        verdict="fraud",
        fraud_probability=0.92,
        pattern="card_not_present_new_device",
        exposure_usd=1500.0,
        customer_response="Cardholder denies purchase",
        step_up_response=None,
        analyst_response=None
    )
    assert should_file is True
    assert any(a.action == "FILE_REPORT" and a.route == "L2" for a in actions)
