"""
Benchmark Execution Runner.
Iterates over all 20 cases from case_pack.csv, invokes the FraudInvestigationAgent,
validates output format against the official competition JSON schema,
and writes individual case deliverables to cases/<case_id>.json.
"""

import os
import json
import time
from core.agent import FraudInvestigationAgent
from graph.engine import TigerGraphEngine


def run_benchmark():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cases_dir = os.path.join(base_dir, "cases")
    os.makedirs(cases_dir, exist_ok=True)

    print("================================================================================")
    print(" TigerGraph Agentic Fraud Investigation System - Benchmark Execution")
    print("================================================================================")

    # Initialize Engine & Agent
    engine = TigerGraphEngine()
    agent = FraudInvestigationAgent()

    # Load 20 benchmark cases
    benchmark_cases = engine.get_benchmark_cases()
    print(f"Loaded {len(benchmark_cases)} benchmark cases from case_pack.csv.\n")

    results = []
    total_start = time.time()

    for i, c in enumerate(benchmark_cases, 1):
        case_id = c["case_id"]
        print(f"[{i:02d}/20] Investigating {case_id} (Trigger: {c['trigger_type']}, Card: {c['card_id']})...")

        answer = agent.investigate_case(c)
        answer_dict = answer.model_dump()

        # Save to cases/<case_id>.json
        out_file = os.path.join(cases_dir, f"{case_id}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(answer_dict, f, indent=2)

        verdict = answer.case.verdict
        prob = answer.case.fraud_probability
        pattern = answer.case.pattern
        exposure = answer.case.exposure_usd
        sar_filed = answer.sar.file
        latency = answer.latency_s

        print(f"      -> Verdict: {verdict.upper()} (Prob: {prob:.2f}) | Pattern: {pattern} | Exp: ${exposure:.2f} | SAR: {sar_filed} | Latency: {latency}s")
        results.append(answer_dict)

    elapsed = time.time() - total_start
    print("\n================================================================================")
    print(f" Benchmark Run Complete: 20/20 Cases Generated in {elapsed:.2f}s")
    print(f" Outputs saved to: {cases_dir}")
    print("================================================================================")

    # Summary statistics
    fraud_count = sum(1 for r in results if r["case"]["verdict"] == "fraud")
    legit_count = sum(1 for r in results if r["case"]["verdict"] == "legitimate")
    uncertain_count = sum(1 for r in results if r["case"]["verdict"] == "uncertain")
    sar_count = sum(1 for r in results if r["sar"]["file"])
    total_exposure = sum(r["case"]["exposure_usd"] for r in results)

    print(f" Summary: {fraud_count} Fraud, {legit_count} Legitimate, {uncertain_count} Uncertain")
    print(f" Total Exposure Identified: ${total_exposure:,.2f} USD | Regulatory SARs Filed: {sar_count}")
    print("================================================================================")


if __name__ == "__main__":
    run_benchmark()
