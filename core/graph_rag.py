"""
GraphRAG Context Retriever & Synthesis Engine.
Fuses connected graph topology, historical case memory (5,565 closed cases),
bank fraud policy guidelines (R1-R10), and FinCEN/FATF regulatory references
into structured evidence claims for agentic reasoning.
"""

from typing import Dict, Any, List, Optional
from core.models import EvidenceItem, ClosedCaseRecord
from mcp.server import TigerGraphMCPServer


class GraphRAGRetriever:
    def __init__(self, mcp_server: Optional[TigerGraphMCPServer] = None):
        self.mcp = mcp_server or TigerGraphMCPServer()

    def retrieve_investigation_context(
        self,
        case_id: str,
        flagged_txn_id: str,
        card_id: str,
        customer_id: str,
        target_ts: str
    ) -> Dict[str, Any]:
        """
        Retrieves multi-hop graph topology, device profiles, customer baseline,
        and relevant case memory for a target case.
        """
        # 1. Fetch flagged transaction
        txn = self.mcp.tg.local_engine.get_transaction(flagged_txn_id)
        if not txn:
            return {"error": f"Transaction {flagged_txn_id} not found"}

        device_profile = txn.get("device_profile") or ""
        channel = txn.get("channel", "online")
        amt = float(txn.get("TransactionAmt", 0.0))
        addr1 = txn.get("addr1", "")

        # 2. Card Window Traversal (GSQL: card_window)
        window_txns = self.mcp.call_tool("tg_card_window", {
            "card_id": card_id,
            "target_ts": target_ts,
            "hours_before": 48,
            "hours_after": 48
        })["transactions"]

        # 3. Customer Baseline Network (GSQL: customer_network)
        cust_network = self.mcp.call_tool("tg_customer_network", {
            "customer_id": customer_id
        })

        # 4. Device Profile Neighbors (GSQL: device_neighbors)
        device_neighbors = {"connected_cards": [], "transactions": [], "connected_closed_cases": []}
        if device_profile:
            device_neighbors = self.mcp.call_tool("tg_device_neighbors", {
                "device_profile": device_profile
            })

        # 5. Card Testing Algorithm Check (GSQL: detect_card_testing)
        testing_eval = self.mcp.call_tool("tg_detect_card_testing", {
            "card_id": card_id,
            "target_ts": target_ts
        })

        # 6. Historical Case Memory (GSQL: search_closed_cases)
        # Determine likely pattern to search memory
        search_pattern = None
        if testing_eval.get("is_testing"):
            search_pattern = "card_testing"
        elif channel == "online" and txn.get("is_new") == "New":
            search_pattern = "card_not_present_new_device"
        elif channel == "online":
            search_pattern = "card_not_present_fraud"
        elif channel == "in_person" and addr1:
            # Check if out of region
            primary_regions = [r["addr1"] for r in cust_network.get("primary_regions", []) if r.get("cnt", 0) > 3]
            if primary_regions and addr1 not in primary_regions:
                search_pattern = "out_of_region_use"

        similar_cases = self.mcp.call_tool("tg_search_closed_cases", {
            "pattern": search_pattern,
            "limit": 3
        })["similar_cases"]

        return {
            "flagged_txn": txn,
            "window_txns": window_txns,
            "customer_network": cust_network,
            "device_neighbors": device_neighbors,
            "testing_eval": testing_eval,
            "similar_cases": similar_cases,
            "device_profile": device_profile,
            "channel": channel,
            "amt": amt,
            "addr1": addr1
        }

    def synthesize_evidence_claims(
        self,
        context: Dict[str, Any],
        card_id: str,
        customer_id: str,
        flagged_txn_id: str
    ) -> List[EvidenceItem]:
        """
        Transforms raw graph traversals and memory retrievals into defensible,
        policy-grounded EvidenceItem objects with verifiable refs and entity IDs.
        """
        evidence: List[EvidenceItem] = []
        txn = context["flagged_txn"]
        window_txns = context["window_txns"]
        dev_neighbors = context["device_neighbors"]
        cust_network = context["customer_network"]
        testing_eval = context["testing_eval"]
        similar_cases = context["similar_cases"]

        # Claim 1: Transaction and Window behavior
        online_window = [t for t in window_txns if t.get("channel") == "online"]
        if testing_eval.get("is_testing"):
            small_tids = [t["TransactionID"] for t in testing_eval["small_txns"]]
            large_tids = [t["TransactionID"] for t in testing_eval["large_txns"]]
            all_testing = small_tids + large_tids
            l_amt = float(testing_eval['large_txns'][0].get('TransactionAmt') or testing_eval['large_txns'][0].get('amt') or 0.0)
            evidence.append(EvidenceItem(
                claim=f"Card testing sequence observed: {len(testing_eval['small_txns'])} micro-authorizations under $5 within 2 hours followed by authorization of ${l_amt:.2f}",
                source="graph",
                ref=f"query:card_window(card_id={card_id}, hours=2)",
                entity_ids=all_testing
            ))
        elif len(online_window) >= 2 and txn.get("channel") == "online":
            recent_tids = [t["TransactionID"] for t in online_window[:4]]
            burst_sum = sum(float(t.get('TransactionAmt') or t.get('amt') or 0.0) for t in online_window)
            evidence.append(EvidenceItem(
                claim=f"Burst of {len(online_window)} online authorizations totaling ${burst_sum:.2f} on card {card_id} within 48-hour monitoring window",
                source="graph",
                ref=f"query:card_window(card_id={card_id}, hours=48)",
                entity_ids=recent_tids
            ))
        else:
            evidence.append(EvidenceItem(
                claim=f"Flagged authorization of ${txn['TransactionAmt']:.2f} recorded on {txn['ts']} via {txn['channel']} channel with model risk score {txn['risk_score']:.2f}",
                source="graph",
                ref=f"query:transaction(id={flagged_txn_id})",
                entity_ids=[flagged_txn_id]
            ))

        # Claim 2: Device Profile & Identity Signals
        dev_prof = context["device_profile"]
        if dev_prof:
            connected_cards = [c for c in dev_neighbors.get("connected_cards", []) if c != card_id]
            is_new = txn.get("is_new") == "New"
            proxy_type = txn.get("proxy") or ""

            if connected_cards:
                evidence.append(EvidenceItem(
                    claim=f"Device profile ({dev_prof[:60]}...) is shared across {len(connected_cards)} other card(s) ({', '.join(connected_cards[:2])}), indicating syndicated card-not-present ring activity",
                    source="graph",
                    ref="query:device_neighbors",
                    entity_ids=connected_cards
                ))
            elif is_new:
                proxy_clause = f" through {proxy_type} proxy" if proxy_type else ""
                evidence.append(EvidenceItem(
                    claim=f"Transaction originated from an unrecognized device profile marked New for this account ({dev_prof[:50]}...){proxy_clause}",
                    source="graph",
                    ref="query:transaction_identity",
                    entity_ids=[flagged_txn_id]
                ))

        # Claim 3: Geographic / Billing Region analysis
        primary_regions = [r["addr1"] for r in cust_network.get("primary_regions", []) if r.get("cnt", 0) > 2]
        txn_addr = txn.get("addr1")
        if txn_addr and primary_regions and txn_addr not in primary_regions:
            evidence.append(EvidenceItem(
                claim=f"Card-present authorization billed in region {txn_addr}, which deviates completely from customer's established primary billing region(s) {', '.join(primary_regions)}",
                source="graph",
                ref=f"query:customer_network(customer_id={customer_id})",
                entity_ids=[flagged_txn_id]
            ))

        # Claim 4: Case Memory Grounding
        if similar_cases:
            prior_ids = [c["case_id"] for c in similar_cases[:2]]
            p_desc = similar_cases[0].get("pattern", "fraud")
            evidence.append(EvidenceItem(
                claim=f"Typology matches historical closed cases {', '.join(prior_ids)} with confirmed {p_desc} outcome and comparable transactional topology",
                source="document",
                ref="query:closed_cases_memory",
                entity_ids=prior_ids
            ))

        return evidence
