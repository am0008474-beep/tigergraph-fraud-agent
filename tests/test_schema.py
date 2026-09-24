"""
Validation test suite for 20 benchmark case outputs.
Guarantees 100% adherence to the official HHGOA IEEE JSON Answer Format,
FinCEN SAR 6-12 sentence requirements, and database entity integrity.
"""

import os
import json
import re
import sqlite3
import pytest
from core.models import BenchmarkAnswer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE_DIR, "cases")
DB_PATH = os.path.join(BASE_DIR, "fraud_graph.db")


def test_all_20_case_files_exist():
    assert os.path.exists(CASES_DIR), "Cases directory must exist"
    case_files = [f"HHG-{i:03d}.json" for i in range(1, 21)]
    for cf in case_files:
        fpath = os.path.join(CASES_DIR, cf)
        assert os.path.exists(fpath), f"Answer file {cf} missing from cases directory!"


@pytest.mark.parametrize("case_num", range(1, 21))
def test_case_json_schema_conformance(case_num):
    case_id = f"HHG-{case_num:03d}"
    fpath = os.path.join(CASES_DIR, f"{case_id}.json")
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Pydantic validation
    answer = BenchmarkAnswer.model_validate(data)
    assert answer.case_id == case_id

    # 2. Check Part 1: Case Details
    c = answer.case
    assert c.status in ["open", "closed_fraud", "closed_legitimate", "escalated"]
    assert c.verdict in ["fraud", "legitimate", "uncertain"]
    assert 0.0 <= c.fraud_probability <= 1.0
    assert c.pattern in [
        "card_testing", "card_not_present_fraud", "card_not_present_new_device",
        "out_of_region_use", "account_takeover", "undocumented", "none"
    ]
    assert c.written_to_graph is True
    assert len(c.summary) > 10

    # Pattern description rules
    if c.pattern == "undocumented":
        assert len(c.pattern_description) > 20, "Undocumented pattern must have a descriptive explanation"
    else:
        assert c.pattern_description == "", "Standard patterns must have empty pattern_description"

    # Legitimate verdict rules
    if c.verdict == "legitimate":
        assert len(c.affected_txn_ids) == 0, "Legitimate cases must have empty affected_txn_ids"
        assert c.exposure_usd == 0.0, "Legitimate cases must have exposure_usd == 0.0"

    # Fraud verdict rules
    if c.verdict == "fraud":
        assert len(c.affected_txn_ids) > 0, "Fraud cases must specify affected transactions"
        assert c.exposure_usd > 0.0, "Fraud cases must identify financial exposure"
        assert c.first_suspicious_txn_id != "", "Fraud cases must designate first_suspicious_txn_id"

    # 3. Check Part 2: SAR Requirements
    sar = answer.sar
    final_actions = [a.action for a in answer.next_best_actions.final]
    has_file_report = "FILE_REPORT" in final_actions
    assert sar.file == has_file_report, "sar.file must strictly agree with presence of FILE_REPORT in final actions"

    if sar.file:
        assert len(sar.narrative) > 50, "SAR narrative must be populated when file=True"
        assert len(sar.subjects) > 0, "SAR subjects must be listed when file=True"
        assert sar.total_amount_usd == c.exposure_usd, "SAR total_amount_usd must equal case exposure_usd"
        assert len(sar.activity_dates) == 2, "SAR activity_dates must contain [start_date, end_date]"
        assert sar.activity_dates[0] <= sar.activity_dates[1], "Activity start date must precede or equal end date"
        
        # FinCEN 6-12 sentence compliance check
        sentences = [s.strip() for s in re.split(r'(?<=\.)\s+(?=[A-Z])', sar.narrative) if s.strip()]
        assert 6 <= len(sentences) <= 12, f"SAR narrative must be 6-12 sentences (found {len(sentences)})"
    else:
        assert sar.narrative == ""
        assert sar.subjects == []
        assert sar.total_amount_usd == 0.0
        assert sar.activity_dates == []

    # 4. Check Part 3: Next Best Actions & Routing
    nba = answer.next_best_actions
    assert len(nba.initial) > 0, "Must provide initial actions"
    assert len(nba.final) > 0, "Must provide final actions"
    assert len(nba.what_changed) > 0, "Must explain what changed"

    valid_actions = {
        "ALLOW_TRANSACTION", "DECLINE_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS",
        "WARN_CUSTOMER", "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH", "BLOCK_CARD", "BLOCK_ALL_CARDS",
        "GENERATE_REPORT", "CREATE_CASE", "FILE_REPORT", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD"
    }

    for a in nba.initial + nba.final:
        assert a.action in valid_actions, f"Unknown action: {a.action}"
        assert a.route in ["auto", "L1", "L2"]
        assert len(a.reason) > 5

        # Strict Approval Routing verification
        if a.action in {"ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", "WARN_CUSTOMER",
                        "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH", "GENERATE_REPORT", "CREATE_CASE",
                        "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD"}:
            assert a.route == "auto", f"Action {a.action} must have route auto"
        elif a.action == "DECLINE_TRANSACTION":
            assert a.route == "L1", "DECLINE_TRANSACTION must have route L1"
        elif a.action == "BLOCK_CARD":
            expected_route = "L2" if c.exposure_usd > 2500.0 else "L1"
            assert a.route == expected_route, f"BLOCK_CARD exposure ${c.exposure_usd} requires route {expected_route}"
        elif a.action in {"BLOCK_ALL_CARDS", "FILE_REPORT"}:
            assert a.route == "L2", f"Action {a.action} must have route L2"

    # 5. Metadata verification
    assert answer.tool_calls > 0
    assert answer.tokens > 0
    assert answer.latency_s > 0.0
    assert len(answer.stop_reason) > 5


def test_entity_ids_in_database():
    """Validates that all referenced IDs in the answer files exist in the actual dataset."""
    if not os.path.exists(DB_PATH):
        pytest.skip("fraud_graph.db not present locally; skipping dataset entity check")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    case_files = [f"HHG-{i:03d}.json" for i in range(1, 21)]
    for cf in case_files:
        fpath = os.path.join(CASES_DIR, cf)
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        c = data.get("case", {})

        # Verify affected transactions
        for tid in c.get("affected_txn_ids", []):
            cur.execute("SELECT 1 FROM transactions WHERE TransactionID = ?", (tid,))
            assert cur.fetchone() is not None, f"Transaction {tid} in {cf} does not exist in dataset!"

        # Verify connected cards
        for card_id in c.get("connected_card_ids", []):
            cur.execute("SELECT 1 FROM transactions WHERE card_id = ? LIMIT 1", (card_id,))
            assert cur.fetchone() is not None, f"Connected card {card_id} in {cf} does not exist in dataset!"

        # Verify prior closed cases
        for sc in c.get("similar_prior_cases", []):
            cur.execute("SELECT 1 FROM closed_cases WHERE case_id = ?", (sc,))
            assert cur.fetchone() is not None, f"Closed case reference {sc} in {cf} does not exist in dataset!"

    conn.close()


def test_autonomous_monitoring_schema_conformance():
    """Validates schema conformance for any autonomous monitoring cases generated beyond the 20 benchmark cases."""
    auto_dir = os.path.join(BASE_DIR, "autonomous_monitoring")
    if not os.path.exists(auto_dir):
        pytest.skip("autonomous_monitoring/ not present; skipping check")

    auto_files = [f for f in os.listdir(auto_dir) if f.endswith(".json")]
    for af in auto_files:
        fpath = os.path.join(auto_dir, af)
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        answer = BenchmarkAnswer.model_validate(data)
        assert answer.case_id.startswith("AUTO-")
        assert answer.case.verdict in ["fraud", "legitimate", "uncertain"]
        assert len(answer.next_best_actions.final) > 0

