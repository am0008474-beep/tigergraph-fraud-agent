"""
TigerGraph Live Connector & Dual-Mode Bridge.
Connects to TigerGraph Savanna Cloud or Community Edition via REST++ / pyTigerGraph,
with seamless fallback to the embedded high-performance TigerGraphEngine.
"""

import os
from typing import Dict, Any, List, Optional
from graph.engine import TigerGraphEngine


class TigerGraphConnector:
    def __init__(self):
        self.host = os.getenv("TG_HOST", "")
        self.username = os.getenv("TG_USERNAME", "tigergraph")
        self.password = os.getenv("TG_PASSWORD", "tigergraph")
        self.graph_name = os.getenv("TG_GRAPH_NAME", "FraudInvestigationGraph")
        self.secret = os.getenv("TG_SECRET", "")
        self.api_token = os.getenv("TG_API_TOKEN", "")

        self.live_conn = None
        self.local_engine = TigerGraphEngine()

        if self.host:
            self._init_live_connection()

    def _init_live_connection(self):
        try:
            import pyTigerGraph as tg
            self.live_conn = tg.TigerGraphConnection(
                host=self.host,
                graphname=self.graph_name,
                username=self.username,
                password=self.password
            )
            if self.secret:
                self.api_token = self.live_conn.getToken(self.secret)
            print(f"[TigerGraphConnector] Connected to live TigerGraph instance at {self.host}")
        except Exception as e:
            print(f"[TigerGraphConnector] Live connection warning: {e}. Defaulting to Embedded TigerGraph Engine.")
            self.live_conn = None

    @property
    def is_live(self) -> bool:
        return self.live_conn is not None

    def query_card_window(self, card_id: str, target_ts: str, hours_before: int = 24, hours_after: int = 24) -> List[Dict[str, Any]]:
        if self.is_live:
            try:
                res = self.live_conn.runInstalledQuery("card_window", {
                    "target_card": card_id,
                    "target_ts": target_ts,
                    "hours_before": hours_before,
                    "hours_after": hours_after
                })
                return res[0]["Txns"] if res else []
            except Exception as e:
                print(f"[TigerGraph Live Query Error] card_window: {e}")
        return self.local_engine.get_card_window(card_id, target_ts, hours_before, hours_after)

    def query_device_neighbors(self, device_profile: str) -> Dict[str, Any]:
        if self.is_live:
            try:
                res = self.live_conn.runInstalledQuery("device_neighbors", {
                    "target_device": device_profile
                })
                return res[0] if res else {"connected_cards": [], "transactions": [], "connected_closed_cases": []}
            except Exception as e:
                print(f"[TigerGraph Live Query Error] device_neighbors: {e}")
        return self.local_engine.get_device_neighbors(device_profile)

    def query_customer_network(self, customer_id: str) -> Dict[str, Any]:
        if self.is_live:
            try:
                res = self.live_conn.runInstalledQuery("customer_network", {
                    "target_customer": customer_id
                })
                return res[0] if res else {}
            except Exception as e:
                print(f"[TigerGraph Live Query Error] customer_network: {e}")
        return self.local_engine.get_customer_network(customer_id)

    def query_card_testing(self, card_id: str, target_ts: str) -> Dict[str, Any]:
        if self.is_live:
            try:
                res = self.live_conn.runInstalledQuery("detect_card_testing", {
                    "target_card": card_id,
                    "target_ts": target_ts,
                    "small_threshold": 5.0,
                    "large_threshold": 50.0
                })
                return res[0] if res else {"is_testing": False, "exposure_usd": 0.0}
            except Exception as e:
                print(f"[TigerGraph Live Query Error] detect_card_testing: {e}")
        return self.local_engine.detect_card_testing(card_id, target_ts)

    def write_case_memory(self, case_id: str, case_data: Dict[str, Any]) -> str:
        if self.is_live:
            try:
                c = case_data.get("case", {})
                self.live_conn.runInstalledQuery("write_investigation_case", {
                    "case_id": case_id,
                    "status": c.get("status", "open"),
                    "verdict": c.get("verdict", "uncertain"),
                    "fraud_prob": c.get("fraud_probability", 0.0),
                    "pattern": c.get("pattern", "none"),
                    "pattern_desc": c.get("pattern_description", ""),
                    "exposure": c.get("exposure_usd", 0.0),
                    "stop_reason": case_data.get("stop_reason", ""),
                    "summary": c.get("summary", ""),
                    "target_card": case_data.get("card_id", ""),
                    "affected_txns": c.get("affected_txn_ids", []),
                    "connected_cards": c.get("connected_card_ids", [])
                })
            except Exception as e:
                print(f"[TigerGraph Live Write Error] write_case_memory: {e}")
        return self.local_engine.write_case_to_graph(case_id, case_data)
