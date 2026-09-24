"""
FastAPI Server for Analyst Investigation Dashboard.
Provides REST APIs for case queue inspection, graph topology retrieval,
action approval workflows, and static web dashboard hosting.
"""

import os
import json
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TigerGraph Agentic Fraud Investigation Portal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(BASE_DIR, "cases")
AUTO_DIR = os.path.join(BASE_DIR, "autonomous_monitoring")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/api/cases")
def list_cases(source: str = "benchmark"):
    """Returns summarized list of cases (benchmark or autonomous)."""
    target_dir = AUTO_DIR if source == "autonomous" else CASES_DIR
    cases = []
    if not os.path.exists(target_dir):
        return {"cases": []}

    for fname in sorted(os.listdir(target_dir)):
        if fname.endswith(".json"):
            fpath = os.path.join(target_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                c = data.get("case", {})
                cases.append({
                    "case_id": data.get("case_id"),
                    "status": c.get("status"),
                    "verdict": c.get("verdict"),
                    "fraud_probability": c.get("fraud_probability"),
                    "pattern": c.get("pattern"),
                    "exposure_usd": c.get("exposure_usd"),
                    "sar_filed": data.get("sar", {}).get("file", False),
                    "connected_cards_count": len(c.get("connected_card_ids", [])),
                    "written_to_graph": c.get("written_to_graph", True),
                    "graph_case_id": c.get("graph_case_id", ""),
                    "latency_s": data.get("latency_s")
                })
    return {"cases": cases}


@app.get("/api/case/{case_id}")
def get_case(case_id: str):
    """Returns full details of a specific case."""
    fpath = os.path.join(CASES_DIR, f"{case_id}.json")
    if not os.path.exists(fpath):
        fpath = os.path.join(AUTO_DIR, f"{case_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Case not found")
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/stats")
def get_stats():
    """Calculates dashboard summary metrics."""
    cases_resp = list_cases("benchmark")["cases"]
    total = len(cases_resp)
    fraud = sum(1 for c in cases_resp if c["verdict"] == "fraud")
    legit = sum(1 for c in cases_resp if c["verdict"] == "legitimate")
    uncertain = sum(1 for c in cases_resp if c["verdict"] == "uncertain")
    sars = sum(1 for c in cases_resp if c["sar_filed"])
    exposure = sum(c["exposure_usd"] for c in cases_resp)

    return {
        "total_cases": total,
        "fraud_cases": fraud,
        "legitimate_cases": legit,
        "uncertain_cases": uncertain,
        "sars_filed": sars,
        "total_exposure_usd": round(exposure, 2),
        "graph_persisted_count": total
    }


@app.get("/api/topology/{case_id}")
def get_case_topology(case_id: str):
    """Generates graph topology nodes and links for canvas rendering."""
    fpath = os.path.join(CASES_DIR, f"{case_id}.json")
    if not os.path.exists(fpath):
        fpath = os.path.join(AUTO_DIR, f"{case_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Case not found")

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    c = data.get("case", {})
    affected = c.get("affected_txn_ids", [])
    connected_cards = c.get("connected_card_ids", [])
    dev_profs = c.get("connected_device_profiles", [])

    nodes = [
        {"id": case_id, "label": f"Case: {case_id}", "type": "case", "status": c.get("status")}
    ]
    links = []

    # Target Card
    card_id = "CARD-001"
    for e in c.get("evidence", []):
        for eid in e.get("entity_ids", []):
            if "-K" in eid:
                card_id = eid
                break
    nodes.append({"id": card_id, "label": f"Card: {card_id}", "type": "card"})
    links.append({"source": case_id, "target": card_id, "rel": "ON_CARD"})

    # Customer node
    cust_id = card_id.split("-")[0] if "-" in card_id else "CUST"
    nodes.append({"id": cust_id, "label": f"Customer: {cust_id}", "type": "customer"})
    links.append({"source": cust_id, "target": card_id, "rel": "OWNS"})

    # Affected Txns
    for tid in affected[:4]:
        nodes.append({"id": str(tid), "label": f"Txn: {tid}", "type": "transaction"})
        links.append({"source": card_id, "target": str(tid), "rel": "MADE"})

    # Connected Cards
    for cc in connected_cards[:3]:
        nodes.append({"id": cc, "label": f"Linked Card: {cc}", "type": "connected_card"})
        links.append({"source": case_id, "target": cc, "rel": "CONNECTED_TO"})

    # Device Profile
    if dev_profs:
        d_label = dev_profs[0].split("|")[0].strip() if "|" in dev_profs[0] else dev_profs[0][:20]
        nodes.append({"id": "DEV-01", "label": f"Device: {d_label}", "type": "device"})
        links.append({"source": card_id, "target": "DEV-01", "rel": "FROM_DEVICE"})
        for cc in connected_cards[:3]:
            links.append({"source": cc, "target": "DEV-01", "rel": "SHARED_DEVICE"})

    # Similar Cases
    for sc in c.get("similar_prior_cases", [])[:2]:
        nodes.append({"id": sc, "label": f"Prior Case: {sc}", "type": "closed_case"})
        links.append({"source": case_id, "target": sc, "rel": "CASE_MEMORY"})

    return {"nodes": nodes, "links": links}


@app.post("/api/approve/{case_id}")
def approve_action(case_id: str, payload: Dict[str, Any]):
    """Simulates an L1 / L2 analyst approval."""
    fpath = os.path.join(CASES_DIR, f"{case_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Case not found")

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    route = payload.get("route", "L1")
    action = payload.get("action", "")

    # Record approval into audit log
    if "approvals" not in data:
        data["approvals"] = []
    data["approvals"].append({
        "action": action,
        "route": route,
        "approved_by": "Senior Fraud Specialist / Manager",
        "timestamp": "2026-09-23 03:00:00"
    })

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return {"status": "approved", "case_id": case_id, "action": action, "route": route}


# Mount static frontend
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "TigerGraph Agentic Fraud Investigation API running. Frontend static index not found."})
