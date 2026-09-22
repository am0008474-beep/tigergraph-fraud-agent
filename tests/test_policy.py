"""
Unit tests for Bank Fraud Policy Engine (Rules R1 - R10 and Approval Routes).
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
    # Probability < 0.70 on single signal -> must verify first
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
