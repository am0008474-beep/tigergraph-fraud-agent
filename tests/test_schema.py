"""
Validation test suite for 20 benchmark case outputs.
Guarantees 100% adherence to the official HHGOA IEEE JSON Answer Format.
"""

import os
import json
import pytest
from core.models import BenchmarkAnswer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE_DIR, "cases")


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

    # Validate against Pydantic schema
    answer = BenchmarkAnswer.model_validate(data)
    assert answer.case_id == case_id

    # Check Part 1: Case
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

    if c.verdict == "legitimate":
        assert len(c.affected_txn_ids) == 0, "Legitimate cases must have empty affected_txn_ids"
        assert c.exposure_usd == 0.0, "Legitimate cases must have exposure_usd == 0.0"

    # Check Part 2: SAR
    sar = answer.sar
    if sar.file:
        assert len(sar.narrative) > 50, "SAR narrative must be populated when file=True"
        assert len(sar.subjects) > 0, "SAR subjects must be listed when file=True"
        assert sar.total_amount_usd > 0.0, "SAR total_amount_usd must be > 0 when file=True"
        assert len(sar.activity_dates) == 2, "SAR activity_dates must contain start and end date"
    else:
        assert sar.narrative == ""
        assert sar.subjects == []
        assert sar.total_amount_usd == 0.0
        assert sar.activity_dates == []

    # Check Part 3: Next Best Actions
    nba = answer.next_best_actions
    assert len(nba.initial) > 0, "Must provide initial actions"
    assert len(nba.final) > 0, "Must provide final actions"
    for a in nba.initial + nba.final:
        assert a.route in ["auto", "L1", "L2"]
        assert len(a.reason) > 5

    # Check Metadata
    assert answer.tool_calls > 0
    assert answer.tokens > 0
    assert answer.latency_s > 0.0
    assert len(answer.stop_reason) > 5
