# Building TigerGraph Sentinel: An Autonomous Agentic Fraud Investigation & Next-Best Action Engine

*By the Engineering Team at Hacker House Goa 2026*

---

## Introduction & Executive Summary

Fraud analysis in modern financial institutions is fundamentally a graph problem masquerading as a tabular classification problem. Every transaction is surrounded by an intricate web of invisible relationships: cards belonging to the same customer, devices shared across accounts, proxy networks cloaking IP origins, and velocity clusters executed across milliseconds.

Yet, traditional fraud detection stacks remain stubbornly linear. A machine learning model assigns a raw "risk score" between 0.0 and 1.0 to a transaction. When that score exceeds a static threshold, a human analyst is summoned to manually cross-reference SQL tables, search logs for device strings, pull up cardholder profiles, guess whether out-of-region swipes represent vacation travel or cloned magnetic stripes, and decide whether to block the card. This process is slow, fragmented, and vulnerable to analyst fatigue. By the time a case is manually confirmed, the funds have already left the banking perimeter.

For the **TigerGraph × Hacker House Goa (HHGOA) 2026 Challenge**, we set out to eliminate this operational bottleneck. We built **TigerGraph Sentinel**: a fully autonomous, graph-native AI agent for fraud investigation and next-best action recommendation. Powered by TigerGraph Savanna, GSQL graph traversals, Model Context Protocol (MCP), and GraphRAG, our system navigates 590,000+ real-world transactions and 144,000+ device identity records, calibrates uncertain signals, simulates controlled evidence-gathering, enforces strict bank policy approval routes (`auto`, `L1`, `L2`), files regulatory Suspicious Activity Reports (SAR), and writes new findings back into TigerGraph as persistent case memory.

Here is a deep-dive into what we built, our architecture, how TigerGraph makes it possible, the agentic capabilities we engineered, our lessons learned, and where we are taking the platform next.

---

## 1. What We Built

TigerGraph Sentinel is an end-to-end autonomous agentic investigation system designed to replace fragmented manual workflows with automated, defensible, and auditable decisions. 

Given an alert triggered by a model risk score, a customer complaint, or an analyst anomaly report, Sentinel executes an 8-stage investigation pipeline:
1. **Trigger Ingestion**: Consumes the flagged transaction ID and initial alert context.
2. **Multi-Hop Graph Traversal**: Queries TigerGraph to reconstruct the customer's behavioral baseline, temporal transaction windows, device neighbors, and shared infrastructure rings.
3. **GraphRAG Case Memory Retrieval**: Matches the observed topology against 5,565 closed historical cases and bank policy rules (R1–R10).
4. **Uncertainty Assessment & Typology Identification**: Calibrates the raw risk score against structural graph evidence, classifying the activity into recognized typologies (`card_testing`, `card_not_present_fraud`, `card_not_present_new_device`, `out_of_region_use`, `account_takeover`, or `undocumented`).
5. **Initial Policy Action Routing**: Formulates immediate actions based on available evidence, strictly enforcing approval hierarchies (`auto` for automated actions, `L1` for Team Lead, `L2` for Fraud Manager).
6. **Controlled Policy Actions**: Simulates policy-governed evidence gathering—such as cardholder verification, step-up two-factor challenges, or analyst consultations—when residual uncertainty remains.
7. **Final Recommendation Update & SAR Formulation**: Re-evaluates next-best actions post-evidence, documents what changed, and drafts complete 6–12 sentence FinCEN-compliant Suspicious Activity Reports (SAR) if regulatory thresholds ($1,000+ exposure or syndicate fraud rings) are breached.
8. **Dynamic Case Memory Write-Back**: Creates a new `FraudCase` vertex in TigerGraph with relationships to affected cards and transactions, ensuring subsequent investigations can build upon this knowledge.

Along with the autonomous agent backend, we built an interactive, dark-mode **Analyst Web Dashboard** that visualizes the 2-hop topology on an interactive Canvas, displays the chronological 8-step investigation stepper, compares model risk scores with agent-assessed fraud probabilities, and enables human analysts to authorize `L1` and `L2` actions with a single click.

---

## 2. Architecture & System Design

Our architecture was intentionally designed for zero-latency operational resilience, separating the graph storage layer, the orchestration layer, and the analyst interface.

```
                      +-----------------------------------+
                      |     Trigger Alert Event           |
                      | (Risk Score / Report / Analyst)   |
                      +-----------------+-----------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                       Autonomous Agent Core (agent.py)                        |
|                                                                               |
|  +--------------------+   +---------------------+   +----------------------+  |
|  | 1. Ingest Trigger  |-->| 2. Graph Traversal  |-->| 3. Evidence Assembly |  |
|  +--------------------+   +---------------------+   +----------------------+  |
|                                                                  |            |
|  +--------------------+   +---------------------+   +------------v---------+  |
|  | 6. Controlled      |<--| 5. Initial Routing  |<--| 4. Uncertainty &     |  |
|  |    Evidence        |   |    (auto / L1 / L2) |   |    Typology (R1-R10) |  |
|  +---------+----------+   +---------------------+   +----------------------+  |
|            |                                                                  |
|  +---------v----------+   +---------------------+                             |
|  | 7. Final Action &  |-->| 8. Case Memory      |                             |
|  |    SAR Formulation |   |    Write-Back       |                             |
|  +--------------------+   +----------+----------+                             |
+--------------------------------------|----------------------------------------+
                                       |
           +---------------------------+---------------------------+
           |                                                       |
           v                                                       v
+-------------------------+                             +-----------------------+
|  TigerGraph MCP Server  |                             |  Analyst Web Portal   |
|  (mcp/server.py)        |                             |  (FastAPI + Canvas)   |
|  - tg_card_window       |                             |  - Live Topology View |
|  - tg_device_neighbors  |                             |  - 8-Step Stepper     |
|  - tg_customer_network  |                             |  - Action Approvals   |
|  - tg_write_case_vertex |                             |  - SAR Export         |
+------------+------------+                             +-----------------------+
             |
             v
+-------------------------------------------------------------------------------+
|                      TigerGraph Dual-Mode Graph Engine                        |
|                                                                               |
|  [Mode A: Live Savanna Cloud / CE]            [Mode B: Embedded Graph Engine] |
|   - pyTigerGraph REST++ client                 - High-throughput In-Memory    |
|   - Pre-installed GSQL queries                 - Sub-millisecond index lookup |
|   - Multi-tenant cloud scale                   - Zero-dependency execution    |
+-------------------------------------------------------------------------------+
```

### The Dual-Mode Graph Bridge
One of our proudest architectural innovations is our **Dual-Mode TigerGraph Layer**. 
While building and testing our agent, we needed to ensure that our solution could run against a live cloud-hosted **TigerGraph Savanna** instance via REST++ and `pyTigerGraph`, but also execute completely offline with sub-millisecond query latencies during automated regression test runs and hackathon evaluation.

Our `TigerGraphConnector` automatically checks for environment variables (`TG_HOST`, `TG_USERNAME`, `TG_PASSWORD`, `TG_GRAPH_NAME`, `TG_SECRET`). If live credentials are provided, it executes parameterized GSQL queries against the remote cluster. If offline, it transparently falls back to our embedded high-performance graph engine, which maintains identical graph schema definitions, indices, and GSQL query semantics locally.

---

## 3. How TigerGraph is Used: Graph Modeling & GSQL Algorithms

### Graph Schema Design
In fraud detection, relations are first-class citizens. Our schema models entities as vertices and transactions as behavioral bridges:

- **Vertices**:
  - `Customer`: Primary cardholder account.
  - `Card`: Unique payment instrument (`card1`, `card2`, `card4`, `card6`).
  - `Transaction`: Individual transaction event (`amt`, `ts`, `channel`, `risk_score`, `product_cd`).
  - `DeviceProfile`: Hardware and software fingerprint (`device_info`, `os`, `browser`, `screen`, `device_type`, `is_new`, `proxy`).
  - `BillingRegion`: Anonymized geographic location code (`addr1`).
  - `EmailDomain`: Recipient/purchaser domain.
  - `ClosedCase`: Historical case precedent (5,565 closed records).
  - `FraudCase`: Concluded cases written into live graph memory.

- **Edges**:
  - `Customer -(OWNS)-> Card -(MADE)-> Transaction`
  - `Transaction -(FROM_DEVICE)-> DeviceProfile`
  - `Transaction -(BILLED_IN)-> BillingRegion`
  - `Transaction -(NEXT)-> Transaction` (temporal sequence)
  - `ClosedCase -(ON_CARD)-> Card`, `ClosedCase -(INVOLVES)-> Transaction`
  - `FraudCase -(CASE_ON_CARD)-> Card`, `FraudCase -(CASE_INVOLVES)-> Transaction`

### High-Impact GSQL Algorithms

#### 1. Temporal Window Traversal (`card_window`)
To detect velocity bursts, rapid card testing, or sudden channel switches, we wrote the `card_window` GSQL query, which traverses backward and forward in time around a target timestamp within a card's subgraph:
```gsql
CREATE QUERY card_window(VERTEX<Card> target_card, DATETIME target_ts, INT hours_before, INT hours_after)
FOR GRAPH FraudInvestigationGraph {
    Start = {target_card};
    Txns = SELECT t FROM Start:s -(MADE:e)-> Transaction:t
           WHERE datetime_diff(t.ts, target_ts) >= -hours_before * 3600 
             AND datetime_diff(t.ts, target_ts) <= hours_after * 3600
           ORDER BY t.ts ASC;
    PRINT Txns[Txns.id, Txns.amt, Txns.ts, Txns.channel, Txns.risk_score, Txns.product_cd];
}
```

#### 2. Cross-Account Syndicate Ring Detection (`device_neighbors`)
Fraudsters rarely attack with a single card. By traversing from a suspicious `DeviceProfile` across all connected transactions and back into other cards, Sentinel discovers coordinated multi-card syndicates in a single 2-hop jump:
```gsql
CREATE QUERY device_neighbors(VERTEX<DeviceProfile> target_device)
FOR GRAPH FraudInvestigationGraph {
    SetAccum<VERTEX<Card>> @@connected_cards;
    SetAccum<VERTEX<ClosedCase>> @@connected_closed_cases;

    Start = {target_device};
    Txns = SELECT t FROM Start:d -(USED_IN_TXN:e)-> Transaction:t;
    Cards = SELECT c FROM Txns:t -(MADE_BY:e)-> Card:c ACCUM @@connected_cards += c;
    Cases = SELECT cs FROM Cards:c -(HAD_CLOSED_CASE:e)-> ClosedCase:cs ACCUM @@connected_closed_cases += cs;

    PRINT @@connected_cards, @@connected_closed_cases;
}
```
In Case **HHG-014**, this query instantly revealed that a flagged mobile device (`SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0`) had made purchases across **26 different payment cards** through anonymous rotating proxies!

#### 3. Dynamic Case Memory Persistence (`write_investigation_case`)
When an investigation concludes, writing the verdict to a static database is insufficient—it must become graph evidence for tomorrow's investigations. Our stored query inserts a `FraudCase` vertex and links it to all affected transactions and connected cards:
```gsql
CREATE QUERY write_investigation_case(
    STRING case_id, STRING status, STRING verdict, DOUBLE fraud_prob,
    STRING pattern, DOUBLE exposure, STRING summary,
    VERTEX<Card> target_card, SET<VERTEX<Transaction>> affected_txns, SET<VERTEX<Card>> connected_cards
) FOR GRAPH FraudInvestigationGraph {
    INSERT INTO FraudCase VALUES (case_id, now(), status, verdict, fraud_prob, pattern, exposure, summary);
    INSERT INTO CASE_ON_CARD (FROM, TO) VALUES (case_id, target_card);
    FOREACH t IN affected_txns DO
        INSERT INTO CASE_INVOLVES (FROM, TO) VALUES (case_id, t);
    END;
    FOREACH c IN connected_cards DO
        INSERT INTO CASE_CONNECTED_CARD (FROM, TO) VALUES (case_id, c);
    END;
}
```

---

## 4. Agentic Capabilities Implemented

Building an autonomous agent for a regulated financial environment requires far more than generic prompt engineering. We implemented four specific agentic pillars:

### I. The 50% False Positive Reality & Calibrated Probability
The dataset documentation contains a profound warning: *"Above 0.7, most flagged transactions turn out to be legitimate. Many look suspicious. Half the cases are legitimate. An agent that blocks everything scores badly."*

In raw tabular models, unfamiliar merchants or high dollar amounts trigger elevated risk scores. But when Sentinel examines the graph, it evaluates the customer's *home baseline*:
- In **HHG-007**, the model gave transaction 3514948 a risk score of **0.87** because the amount was $111.92. However, TigerGraph revealed that the billing region `264.0` was the customer's primary everyday hometown region, where they had completed **2,552 prior transactions**! Sentinel correctly overruled the model risk score, assessed the true fraud probability at 0.10, and cleared the alert with `CLOSE_NO_FRAUD`.
- In **HHG-001**, transaction 3514030 ($77.07, in-person) scored **0.61**. The billing region was seen 15 times on the cardholder's baseline. Sentinel cleared it without disrupting the cardholder.

### II. Multi-Tier Governance & Approval Workflows (R1–R10)
Autonomous agents in finance must operate within rigid governance boundaries. Sentinel distinguishes between an agent's *recommendation* and its *authorized execution*:
- `auto`: Actions the agent may execute immediately without human review (`ALLOW_TRANSACTION`, `MONITOR_CARD`, `WARN_CUSTOMER`, `VERIFY_WITH_CUSTOMER`, `STEP_UP_AUTH`, `CREATE_CASE`, `CLOSE_NO_FRAUD`).
- `L1` (Team Lead): Actions requiring operational sign-off, such as `DECLINE_TRANSACTION` and `BLOCK_CARD` with exposure $\le \$2,500$.
- `L2` (Fraud Manager): Critical actions with severe customer or legal impact, including `BLOCK_CARD` with exposure $> \$2,500$, `BLOCK_ALL_CARDS`, and regulatory `FILE_REPORT` (SAR).

### III. Policy R7: Disputed but Legitimate Subscriptions
In Case **HHG-009**, customer C08299 reported an unauthorized $30.02 online transaction. A naive agent would immediately block the card. Sentinel traversed the customer's history, identified a recurring monthly charge pattern with the merchant, and applied **Policy Rule R7**:
- Opened internal investigation case (`CREATE_CASE` [auto]).
- Validated with customer (`VERIFY_WITH_CUSTOMER` [auto]).
- Issued cancellation guidance (`WARN_CUSTOMER` [auto]).
- Refrained from blocking the card, preventing unnecessary card reissuance costs and customer churn!

### IV. Automated SAR Narrative Generation
When a case satisfies Policy 3a ($1,000+ exposure, shared device ring, or undocumented coordinated pattern), Sentinel automatically drafts an exhaustive 6–12 sentence FinCEN-compliant SAR narrative answering **Who, What, When, Where, How, and Why**:
```json
{
  "file": true,
  "reason": "R2/Policy 3a: activity links to shared device/ring infrastructure across 26 connected card(s); pattern represents coordinated undocumented syndicate activity (R9)",
  "narrative": "On 2016-11-22 16:11:00, payment card C13487-K1 registered to customer C13487 was utilized in an unauthorized transaction totaling $74.96 via the online channel. Investigation revealed activity matching typology 'undocumented', characterized by anomalous device fingerprinting (SM-G935F Build/NRD90M | Android 7.0 | chrome 62.0 for android | 1920x1080). Analysis identified common infrastructure linking this compromise to 26 additional payment card(s). Upon direct cardholder inquiry, the primary account owner formally denied authorizing or executing the transactions while confirming continued physical possession of the card. Total cumulative unauthorized exposure identified across the compromise episode is $74.96 USD. The financial institution has taken immediate mitigating action by declining pending transactions and blocking card C13487-K1 with reissue initiated. Heightened 72-hour fraud monitoring has been deployed across all connected accounts. This report is submitted pursuant to federal Bank Secrecy Act and FinCEN suspicious activity reporting mandates regarding suspected payment card compromise and illicit fund redirection.",
  "subjects": ["C13487", "C13487-K1", "C01289-K1", "C01996-K1", "SM-G935F Build/NRD90M | Android 7.0 | ch"],
  "total_amount_usd": 74.96,
  "activity_dates": ["2016-11-22", "2016-11-22"]
}
```

---

## 5. Benchmark Performance & Key Lessons Learned

We executed Sentinel across the entire 20-case evaluation suite (`case_pack.csv`).

### Benchmark Results
- **20 / 20 Cases Completed**: 100% execution success rate.
- **Balanced Verdict Calibration**: 12 Confirmed Fraud cases, 8 Legitimate / Cleared / Disputed cases (matching the expected ~50% real-world false alarm distribution).
- **Total Fraud Exposure Identified**: **$6,502.63 USD**.
- **Regulatory SAR Filings**: **10 SARs formulated** under Policy 3a thresholds.
- **Investigation Latency**: All 20 cases investigated, formatted, validated, and written to graph memory in **1.91 seconds** (~95 ms per case).
- **Test Suite**: **31 / 31 unit tests passing in 0.91s**, validating 100% JSON schema conformance.

### What We Learned
1. **Raw Risk Scores are Inadequate**: A score of 0.87 can easily be a normal grocery run in a customer's hometown (HHG-007), while a score of 0.05 can be an automated multi-card syndicate attack (HHG-014). Graph context is the only reliable ground truth.
2. **Generic User-Agents are Not Device Rings**: Early in our testing, our device neighbor query flagged common desktop strings like `Windows 10 | ie 11.0` as fraud rings because hundreds of cards shared that string. We refined our engine to distinguish between generic browser user-agents and specific hardware build strings (`DeviceInfo` like `SM-G935F Build/NRD90M`), eliminating false ring classifications.
3. **Card Cloning is Proven by Time-Space Physics**: In Case **HHG-018**, the customer had transactions in region 325 at 12:40 PM, a flagged transaction in region 126 at 1:41 PM, and another transaction back in region 325 at 1:49 PM. Traveling between those regions in 8 minutes is physically impossible. Graph traversals turn ambiguous disputes into open-and-shut cloning cases.

---

## 6. What We Would Improve With More Time

While TigerGraph Sentinel represents a production-grade hackathon prototype, there are several exciting avenues for future engineering:

1. **Graph Neural Network (GNN) Embeddings in TigerGraph**: Integrating TigerGraph's in-database Graph Convolutional Networks (GCN) to compute node embeddings for cards and devices directly inside the graph engine, enabling vector similarity search alongside topological traversals.
2. **Real-Time Streaming Ingestion with Kafka / TigerGraph Loader**: Connecting the agent directly to Apache Kafka streams, allowing Sentinel to intercept and decline fraudulent authorizations in sub-20ms before settlement.
3. **Cross-Institutional Federated Graph Queries**: Implementing privacy-preserving federated graph queries so multiple banks can detect shared device rings across financial institutions without exposing confidential cardholder PII.
4. **Autonomous Voice Agent for Cardholder Verification**: Connecting the agent's `VERIFY_WITH_CUSTOMER` action to an interactive real-time conversational voice agent that calls the customer, records verbal authorization, and feeds transcript sentiment back into the graph.

---

## Conclusion

TigerGraph Sentinel demonstrates that the future of fraud investigation is agentic, explainable, and fundamentally graph-powered. By combining TigerGraph's high-speed traversals with policy-governed autonomous decision-making, we can transform fraud teams from reactive cleanup crews into proactive defense networks.

*Code, GSQL schemas, benchmark answer files, and UI are available in our [GitHub Repository](https://github.com/your-username/tigergraph-fraud-agent).*
