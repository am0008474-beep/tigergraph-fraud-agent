# 3–5 Minute End-to-End Demo Video Script & Storyboard

**Title**: TigerGraph Sentinel: Autonomous Agentic Fraud Investigation & Next-Best Action  
**Target Duration**: 4 Minutes (240 Seconds)  
**Presenter**: Lead Engineer  
**Live UI Link**: `http://localhost:8000`  

---

## Storyboard & Timing Overview

| Timestamp | Segment | Visual On Screen | Key Narration Focus |
|---|---|---|---|
| **0:00 - 0:35** | **The Hook & Problem** | Title slide + Analyst Dashboard overview | Why fraud investigation is a graph problem, manual bottlenecks, false positives. |
| **0:35 - 1:15** | **Architecture & TigerGraph Engine** | Architecture diagram + GSQL Schema in IDE | Dual-mode TigerGraph layer, schema vertices/edges, GSQL stored queries, MCP. |
| **1:15 - 2:05** | **Deep Dive: Syndicate Ring (HHG-014)** | UI selecting HHG-014 + Canvas Topology | 2-hop `device_neighbors` traversal, uncovering 26 connected cards, Policy R9 undocumented ring, automated SAR drafting. |
| **2:05 - 2:50** | **The 50% False Alarm Trap (HHG-007)** | UI selecting HHG-007 + Gauge comparison | Model scored 0.87, but graph reveals 2,552 baseline home transactions. Clearing alert with `CLOSE_NO_FRAUD`. |
| **2:50 - 3:35** | **Cloned Card & Impossible Travel (HHG-018)** | UI selecting HHG-018 + Timeline stepper | Physical time-space impossibility (region 126 vs 325 in 8 mins), card block, Policy R2. |
| **3:35 - 4:10** | **Policy Approvals & Graph Memory Write** | Interactive approval buttons + Terminal | Simulating `L1`/`L2` approvals, writing `FraudCase` vertex to graph memory, sub-100ms benchmark. |
| **4:10 - 4:30** | **Conclusion & Impact** | GitHub repo + Benchmark summary stats | 31 unit tests, 20/20 benchmark files generated in 1.9s, call to action. |

---

## Detailed Voiceover Script & Visual Actions

### Segment 1: The Problem & The Solution (0:00 - 0:35)
**Visual**: Open browser at `http://localhost:8000`. Show the dark-mode TigerGraph Sentinel Analyst Dashboard with the live connection badge and stats bar.
> **Voiceover (0:00 - 0:35)**:  
> "Hello everyone! Today, fraud investigation teams at financial institutions are under immense pressure. When a real-time model flags a transaction, human analysts must spend hours manually tracing card history, checking device footprints, looking up past closed cases, and deciding whether to freeze an account. Most of the time, the funds are already gone—or worse, a legitimate cardholder is falsely blocked during a grocery run.  
> 
> To solve this, we built **TigerGraph Sentinel**—an autonomous agentic fraud investigator powered by TigerGraph that navigates complex relationship graphs, balances uncertainty, gathers policy-governed evidence, and executes defensible next-best actions in real time."

---

### Segment 2: TigerGraph Architecture & GSQL Engine (0:35 - 1:15)
**Visual**: Split screen between `graph/schema.gsql` and the interactive Canvas on the dashboard showing nodes (Customer, Cards, Transactions, DeviceProfile, ClosedCases).
> **Voiceover (0:35 - 1:15)**:  
> "At the heart of Sentinel is a dual-mode TigerGraph architecture. Our graph schema models Customers, Cards, Transactions, Device Profiles, and historical Closed Cases.  
> 
> We engineered specialized GSQL graph algorithms: `card_window` for temporal velocity analysis, and `device_neighbors` for multi-hop hardware ring detection. Through our TigerGraph Model Context Protocol (MCP) server, the agent invokes these queries as native tools.  
> 
> Best of all, our system supports live TigerGraph Savanna cloud workspaces while also featuring an embedded in-memory graph engine capable of executing graph traversals in sub-milliseconds."

---

### Segment 3: Live Case Walkthrough — Syndicate Fraud Ring (HHG-014) (1:15 - 2:05)
**Visual**: Click on **HHG-014** in the queue. Show the Canvas graph expand, dragging nodes to show the device node connected to 26 cards.
> **Voiceover (1:15 - 2:05)**:  
> "Let's see the agent in action on Case **HHG-014**. This was triggered by an analyst report noticing unusual device activity on card C13487-K1.  
> 
> Notice what happens: Sentinel calls `tg_device_neighbors`. In a single 2-hop graph traversal, it discovers that this mobile device fingerprint—a Samsung Galaxy S7 on Android 7.0 using anonymous rotating proxies—is secretly shared across **26 different payment cards**!  
> 
> The agent identifies this as an undocumented syndicate fraud ring under Policy R9. It assesses fraud probability at 0.96, recommends declining the authorization, blocking the card with L1 approval, placing all 26 connected cards under 72-hour monitoring, and automatically formulates an exhaustive FinCEN Suspicious Activity Report covering Who, What, When, Where, How, and Why."

---

### Segment 4: Overcoming the 50% False Alarm Trap (HHG-007) (2:05 - 2:50)
**Visual**: Click on **HHG-007** in the case queue. Highlight the Uncertainty Gauge: Model Score `0.87` vs Agent Fraud Prob `0.10`.
> **Voiceover (2:05 - 2:50)**:  
> "Now, here is where most fraud models fail. In the IEEE dataset, over half of high-scoring transactions are actually legitimate! If an agent blindly blocks everything, customer churn skyrockets.  
> 
> Look at **HHG-007**. The bank's real-time model scored this transaction at **0.87**—an alarming red flag. But watch how Sentinel investigates: it calls `tg_customer_network` and examines the customer's historical baseline.  
> 
> The graph reveals that this card-present purchase took place in billing region 264.0—which is the customer's everyday hometown where they have made **over 2,500 prior transactions**! Sentinel recognizes the model score as a false alarm, lowers the fraud probability to 0.10, and cleanly clears the alert with `CLOSE_NO_FRAUD`. The customer experiences zero disruption."

---

### Segment 5: Impossible Travel & Card Cloning (HHG-018) (2:50 - 3:35)
**Visual**: Click on **HHG-018**. Zoom in on the 8-Step Stepper timeline showing the surrounding transactions in region 325 and region 126.
> **Voiceover (2:50 - 3:35)**:  
> "Next, look at Case **HHG-018**. Customer C02354 reported an unauthorized $39 charge in billing region 126.  
> 
> Is the customer mistaken, or was the card cloned? Sentinel inspects the temporal sequence in the graph: the card was physically swiped in region 325 at 12:40 PM, swiped in region 126 at 1:41 PM, and swiped back in region 325 at 1:49 PM—just 8 minutes later!  
> 
> By time-space physics, a customer cannot travel between those distant regions in 8 minutes. The card was cloned. Sentinel confirms the fraud, blocks the card for reissue, and updates the case record."

---

### Segment 6: Human Approval Workflow & Case Memory Persistence (3:35 - 4:10)
**Visual**: Click the **"Approve L1"** and **"Approve L2"** buttons in the UI. Show the green confirmation toast and graph vertex ID. Then switch to terminal and show `python -m pytest tests/` passing.
> **Voiceover (3:35 - 4:10)**:  
> "Governance is built into every step. Actions like card blocking or SAR filings require human sign-off under Policy Rules R1 through R10. Analysts can approve `L1` or `L2` actions with a single click, instantly appending their digital signature to the audit trail.  
> 
> Crucially, when Sentinel concludes an investigation, it executes `write_investigation_case` to store a `FraudCase` vertex directly into TigerGraph. Tomorrow's investigations will retrieve this case as historical memory!  
> 
> In our benchmark tests, Sentinel investigated and formatted all 20 exam cases in **under two seconds**, with all 31 unit tests passing with 100% schema accuracy."

---

### Segment 7: Conclusion & Wrap-Up (4:10 - 4:30)
**Visual**: Show the project GitHub repository, the `cases/` folder containing all 20 JSON deliverables, and the technical blog post.
> **Voiceover (4:10 - 4:30)**:  
> "TigerGraph Sentinel proves that graph-native reasoning is the missing link in autonomous financial security. By uniting TigerGraph's high-speed traversals with explainable, policy-governed agentic workflows, we protect both the bank's bottom line and the customer's trust.  
> 
> Thank you so much, and we invite you to explore our code, documentation, and benchmark answers on GitHub!"

---
*End of Demo Recording.*
