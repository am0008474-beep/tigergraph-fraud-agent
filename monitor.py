"""
Autonomous Exam Period Fraud Scanner (Innovation Deliverable).
Continuously monitors November-December 2016 transactions, detects unflagged anomalies
beyond the 20 benchmark cases, and executes end-to-end agentic investigations.
Outputs findings to autonomous_monitoring/ as specified in the hackathon guidelines.
"""

import os
import sys
import json
import sqlite3
import argparse
from typing import List, Dict, Any
from core.agent import FraudInvestigationAgent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "fraud_graph.db")
OUTPUT_DIR = os.path.join(BASE_DIR, "autonomous_monitoring")


EXAM_BENCHMARK_TXNS = {
    "3514030", "3478782", "3530164", "3583227", "3523199", "3476682", "3514948",
    "3558054", "3581141", "3506725", "3583368", "3553342", "3526826", "3478561",
    "3464869", "3534820", "3450629", "3491361", "3503878", "3509359"
}


def scan_exam_period_alerts(limit: int = 5, min_score: float = 0.90) -> List[Dict[str, Any]]:
    """Scans the November-December exam window for unalerted high-risk transactions."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(EXAM_BENCHMARK_TXNS))
    query = f"""
        SELECT TransactionID, card_id, customer_id, ts, risk_score, TransactionAmt, channel, addr1, device_profile
        FROM transactions
        WHERE ts >= '2016-11-01'
          AND risk_score >= ?
          AND TransactionID NOT IN ({placeholders})
        ORDER BY risk_score DESC, TransactionAmt DESC
        LIMIT ?
    """
    params = [min_score] + list(EXAM_BENCHMARK_TXNS) + [limit]
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    alerts = []
    for idx, r in enumerate(rows, 1):
        alerts.append({
            "case_id": f"AUTO-{idx:03d}",
            "opened_at": r[3],
            "trigger_type": "risk_score",
            "trigger_text": f"Autonomous Sentinel Scanner flagged transaction {r[0]} (${r[5]:.2f}, {r[6]}) with model risk score {r[4]:.2f}.",
            "flagged_txn_id": str(r[0]),
            "card_id": r[1],
            "customer_id": r[2],
            "risk_score": r[4]
        })
    return alerts


def run_autonomous_investigation(limit: int = 5):
    """Executes investigations on discovered autonomous alerts and saves to autonomous_monitoring/."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    alerts = scan_exam_period_alerts(limit=limit)

    print("=" * 80)
    print(" TigerGraph Sentinel - Autonomous Exam Period Monitoring Scanner")
    print(f" Identified {len(alerts)} un-alerted anomalies beyond benchmark case pack")
    print("=" * 80)

    agent = FraudInvestigationAgent()
    summary = {"total": len(alerts), "fraud": 0, "legitimate": 0, "exposure": 0.0, "sars": 0}

    for alert in alerts:
        cid = alert["case_id"]
        print(f"\n[*] Scanning & Investigating {cid} (Txn: {alert['flagged_txn_id']}, Card: {alert['card_id']}, Score: {alert['risk_score']:.2f})...")
        answer = agent.investigate_case(alert)

        # Write output file
        out_path = os.path.join(OUTPUT_DIR, f"{cid}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(answer.model_dump(), f, indent=2)

        verdict = answer.case.verdict.upper()
        prob = answer.case.fraud_probability
        exp = answer.case.exposure_usd
        sar = answer.sar.file
        latency = answer.latency_s

        if answer.case.verdict == "fraud":
            summary["fraud"] += 1
            summary["exposure"] += exp
            if sar:
                summary["sars"] += 1
        elif answer.case.verdict == "legitimate":
            summary["legitimate"] += 1

        print(f"    -> Verdict: {verdict} (Prob: {prob:.2f}) | Exp: ${exp:.2f} | SAR: {sar} | Latency: {latency:.2f}s")
        print(f"    -> Summary: {answer.case.summary[:90]}...")

    print("\n" + "=" * 80)
    print(" Autonomous Monitoring Pipeline Complete")
    print(f" Outputs saved to: {OUTPUT_DIR}")
    print(f" Cases Investigated: {summary['total']} | Confirmed Fraud: {summary['fraud']} | Benign Cleared: {summary['legitimate']}")
    print(f" Total Identified Exposure: ${summary['exposure']:.2f} USD | Regulatory SARs Filed: {summary['sars']}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TigerGraph Sentinel Autonomous Exam Monitoring")
    parser.add_argument("--limit", type=int, default=5, help="Number of autonomous cases to investigate")
    args = parser.parse_args()
    run_autonomous_investigation(limit=args.limit)
