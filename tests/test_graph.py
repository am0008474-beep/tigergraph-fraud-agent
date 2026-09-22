"""
Unit tests for TigerGraphEngine and TigerGraphMCPServer traversals.
"""

import pytest
from graph.engine import TigerGraphEngine
from mcp.server import TigerGraphMCPServer


@pytest.fixture(scope="module")
def engine():
    return TigerGraphEngine()


@pytest.fixture(scope="module")
def mcp():
    return TigerGraphMCPServer()


def test_transaction_fetch(engine):
    txn = engine.get_transaction("3514030")
    assert txn is not None
    assert txn["TransactionID"] == "3514030"
    assert txn["channel"] == "in_person"
    assert txn["customer_id"] == "C12382"


def test_card_window_query(engine):
    txns = engine.get_card_window("C12382-K1", "2016-12-04 19:55:28", hours_before=24, hours_after=24)
    assert len(txns) > 0
    # verify sorted by ts
    for i in range(len(txns) - 1):
        assert txns[i]["ts"] <= txns[i+1]["ts"]


def test_device_neighbors_traversal(engine):
    # Device from HHG-014 (syndicate ring)
    dev_prof = "SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080"
    res = engine.get_device_neighbors(dev_prof)
    assert len(res["connected_cards"]) > 1, "Must detect multi-card device linkage"


def test_mcp_server_tool_listing(mcp):
    tools = mcp.list_tools()
    tool_names = [t["name"] for t in tools]
    assert "tg_card_window" in tool_names
    assert "tg_device_neighbors" in tool_names
    assert "tg_customer_network" in tool_names
    assert "tg_detect_card_testing" in tool_names
    assert "tg_search_closed_cases" in tool_names
    assert "tg_write_case_vertex" in tool_names


def test_case_memory_write_and_retrieve(engine):
    test_case_data = {
        "case": {
            "status": "closed_fraud",
            "verdict": "fraud",
            "fraud_probability": 0.95,
            "pattern": "card_not_present_fraud",
            "exposure_usd": 250.0,
            "affected_txn_ids": ["9999991"],
            "connected_card_ids": ["C99999-K1"],
            "connected_device_profiles": [],
            "summary": "Automated test fraud case for graph memory verification."
        },
        "card_id": "C99999-K1",
        "stop_reason": "Test stopping reason"
    }
    graph_id = engine.write_case_to_graph("TEST-001", test_case_data)
    assert graph_id.startswith("CASE-")
