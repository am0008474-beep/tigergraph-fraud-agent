"""
Core Domain Models and Schemas for TigerGraph Agentic Fraud Investigation System.
Strictly adheres to the HHGOA IEEE Hackathon specification and answer format.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Graph Entity Models
# -----------------------------------------------------------------------------

class TransactionRecord(BaseModel):
    transaction_id: str
    amt: float
    product_cd: str
    card1: str
    card2: str
    card4: str
    card6: str
    addr1: str
    addr2: str
    p_emaildomain: str
    customer_id: str
    card_id: str
    ts: str
    channel: str
    risk_score: float
    device_profile: Optional[str] = None
    device_type: Optional[str] = None
    is_new_device: Optional[str] = None
    proxy: Optional[str] = None


class ClosedCaseRecord(BaseModel):
    case_id: str
    customer_id: str
    card_id: str
    opened_at: str
    closed_at: str
    outcome: Literal["confirmed_fraud", "cleared"]
    pattern: str
    first_fraud_txn_id: str
    txn_ids: List[str]
    n_txns: int
    exposure_usd: float
    connected_card_ids: List[str]
    actions_taken: str
    report_filed: str
    analyst_notes: str


class CasePackItem(BaseModel):
    case_id: str
    opened_at: str
    trigger_type: Literal["risk_score", "customer_report", "analyst_request"]
    trigger_text: str
    flagged_txn_id: str
    card_id: str
    customer_id: str
    risk_score: Optional[float] = None


# -----------------------------------------------------------------------------
# Investigation Deliverables Models (Answer Format)
# -----------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    claim: str
    source: Literal["graph", "document", "customer", "external"]
    ref: str
    entity_ids: List[str] = Field(default_factory=list)


class EvidenceRequest(BaseModel):
    type: Literal["customer_validation", "step_up_auth", "analyst_info"]
    asked_after_step: int
    assumed_response: str


class PolicyAction(BaseModel):
    action: Literal[
        "ALLOW_TRANSACTION",
        "DECLINE_TRANSACTION",
        "MONITOR_CARD",
        "MONITOR_CONNECTED_CARDS",
        "WARN_CUSTOMER",
        "VERIFY_WITH_CUSTOMER",
        "STEP_UP_AUTH",
        "BLOCK_CARD",
        "BLOCK_ALL_CARDS",
        "GENERATE_REPORT",
        "CREATE_CASE",
        "FILE_REPORT",
        "ESCALATE_TO_ANALYST",
        "CLOSE_NO_FRAUD",
    ]
    route: Literal["auto", "L1", "L2"]
    reason: str


class NextBestActions(BaseModel):
    initial: List[PolicyAction] = Field(default_factory=list)
    final: List[PolicyAction] = Field(default_factory=list)
    what_changed: str = "nothing"


class SARReport(BaseModel):
    file: bool
    reason: str = ""
    narrative: str = ""
    subjects: List[str] = Field(default_factory=list)
    total_amount_usd: float = 0.0
    activity_dates: List[str] = Field(default_factory=list)


class CaseDetails(BaseModel):
    status: Literal["open", "closed_fraud", "closed_legitimate", "escalated"]
    verdict: Literal["fraud", "legitimate", "uncertain"]
    fraud_probability: float
    pattern: Literal[
        "card_testing",
        "card_not_present_fraud",
        "card_not_present_new_device",
        "out_of_region_use",
        "account_takeover",
        "undocumented",
        "none",
    ]
    pattern_description: str = ""
    affected_txn_ids: List[str] = Field(default_factory=list)
    first_suspicious_txn_id: str = ""
    connected_card_ids: List[str] = Field(default_factory=list)
    connected_device_profiles: List[str] = Field(default_factory=list)
    exposure_usd: float = 0.0
    evidence: List[EvidenceItem] = Field(default_factory=list)
    similar_prior_cases: List[str] = Field(default_factory=list)
    summary: str
    written_to_graph: bool = True
    graph_case_id: str = ""


class BenchmarkAnswer(BaseModel):
    case_id: str
    case: CaseDetails
    evidence_requests: List[EvidenceRequest] = Field(default_factory=list)
    next_best_actions: NextBestActions
    sar: SARReport
    stop_reason: str
    tool_calls: int = 0
    tokens: int = 0
    latency_s: float = 0.0
