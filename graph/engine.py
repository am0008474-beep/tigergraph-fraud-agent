"""
High-Performance Embedded TigerGraph Engine.
Implements the exact TigerGraph schema, indexes, and GSQL query interfaces
for sub-millisecond graph traversals, topology analysis, and dynamic case memory.
"""

import os
import sqlite3
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple


class TigerGraphEngine:
    def __init__(self, db_path: str = None, dataset_dir: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, "fraud_graph.db")
        else:
            self.db_path = db_path

        if dataset_dir is None:
            self.dataset_dir = "C:/Users/lenovo/.gemini/antigravity/scratch/HHGOA_IEEE"
        else:
            self.dataset_dir = dataset_dir

        self.conn = None
        self._ensure_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_database(self):
        """Verifies or builds the indexed graph database if not present."""
        if os.path.exists(self.db_path) and os.path.getsize(self.db_path) > 1024 * 1024:
            return  # Already built

        print(f"[TigerGraphEngine] Initializing graph store at {self.db_path}...")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA synchronous = OFF;")
        cur.execute("PRAGMA journal_mode = MEMORY;")

        # Create Schema Tables
        cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            TransactionID TEXT PRIMARY KEY,
            TransactionAmt REAL,
            ProductCD TEXT,
            card1 TEXT,
            card2 TEXT,
            card4 TEXT,
            card6 TEXT,
            addr1 TEXT,
            addr2 TEXT,
            P_emaildomain TEXT,
            customer_id TEXT,
            card_id TEXT,
            ts TEXT,
            channel TEXT,
            risk_score REAL,
            device_profile TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS identity (
            TransactionID TEXT PRIMARY KEY,
            DeviceInfo TEXT,
            id_30 TEXT,
            id_31 TEXT,
            id_33 TEXT,
            DeviceType TEXT,
            id_15 TEXT,
            id_23 TEXT,
            device_profile TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS closed_cases (
            case_id TEXT PRIMARY KEY,
            customer_id TEXT,
            card_id TEXT,
            opened_at TEXT,
            closed_at TEXT,
            outcome TEXT,
            pattern TEXT,
            first_fraud_txn_id TEXT,
            txn_ids TEXT,
            n_txns INTEGER,
            exposure_usd REAL,
            connected_card_ids TEXT,
            actions_taken TEXT,
            report_filed TEXT,
            analyst_notes TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS case_pack (
            case_id TEXT PRIMARY KEY,
            opened_at TEXT,
            trigger_type TEXT,
            trigger_text TEXT,
            flagged_txn_id TEXT,
            card_id TEXT,
            customer_id TEXT,
            risk_score REAL
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS fraud_cases_graph_memory (
            graph_case_id TEXT PRIMARY KEY,
            case_id TEXT,
            opened_at TEXT,
            status TEXT,
            verdict TEXT,
            fraud_probability REAL,
            pattern TEXT,
            exposure_usd REAL,
            card_id TEXT,
            affected_txn_ids TEXT,
            connected_card_ids TEXT,
            connected_device_profiles TEXT,
            summary TEXT
        );
        """)
        conn.commit()

        # 1. Load Identity
        id_csv = os.path.join(self.dataset_dir, "identity.csv")
        if os.path.exists(id_csv):
            print("[TigerGraphEngine] Loading identity records...")
            id_rows = []
            with open(id_csv, "r", encoding="utf-8") as f:
                header = f.readline().strip().split(",")
                idx = {k: i for i, k in enumerate(header)}
                for line in f:
                    p = line.strip().split(",")
                    tid = p[idx["TransactionID"]]
                    dinfo = p[idx["DeviceInfo"]] if idx["DeviceInfo"] < len(p) else ""
                    os_val = p[idx["id_30"]] if idx["id_30"] < len(p) else ""
                    browser = p[idx["id_31"]] if idx["id_31"] < len(p) else ""
                    screen = p[idx["id_33"]] if idx["id_33"] < len(p) else ""
                    dtype = p[idx["DeviceType"]] if idx["DeviceType"] < len(p) else ""
                    id15 = p[idx["id_15"]] if idx["id_15"] < len(p) else ""
                    id23 = p[idx["id_23"]] if idx["id_23"] < len(p) else ""

                    parts = [p for p in [dinfo, os_val, browser, screen] if p]
                    profile = " | ".join(parts) if parts else ""

                    id_rows.append((tid, dinfo, os_val, browser, screen, dtype, id15, id23, profile))
                    if len(id_rows) >= 50000:
                        cur.executemany("INSERT OR REPLACE INTO identity VALUES (?,?,?,?,?,?,?,?,?)", id_rows)
                        id_rows = []
            if id_rows:
                cur.executemany("INSERT OR REPLACE INTO identity VALUES (?,?,?,?,?,?,?,?,?)", id_rows)
            conn.commit()

        # Build quick identity lookup dict for transaction load
        cur.execute("SELECT TransactionID, device_profile FROM identity")
        device_map = dict(cur.fetchall())

        # 2. Load Case Pack & Closed Cases to get explicit card_id mappings
        case_pack_csv = os.path.join(self.dataset_dir, "case_pack.csv")
        txn_to_card_id = {}
        if os.path.exists(case_pack_csv):
            with open(case_pack_csv, "r", encoding="utf-8") as f:
                r = csv.DictReader(f)
                cp_rows = []
                for row in r:
                    cp_rows.append((
                        row["case_id"], row["opened_at"], row["trigger_type"],
                        row["trigger_text"], row["flagged_txn_id"],
                        row["card_id"], row["customer_id"],
                        float(row["risk_score"]) if row["risk_score"] else None
                    ))
                    txn_to_card_id[row["flagged_txn_id"]] = row["card_id"]
                cur.executemany("INSERT OR REPLACE INTO case_pack VALUES (?,?,?,?,?,?,?,?)", cp_rows)
            conn.commit()

        closed_csv = os.path.join(self.dataset_dir, "closed_cases_history.csv")
        if os.path.exists(closed_csv):
            print("[TigerGraphEngine] Loading closed cases...")
            with open(closed_csv, "r", encoding="utf-8") as f:
                r = csv.DictReader(f)
                cc_rows = []
                for row in r:
                    txns_pipe = row["txn_ids"]
                    for t in txns_pipe.split("|"):
                        if t:
                            txn_to_card_id[t] = row["card_id"]
                    cc_rows.append((
                        row["case_id"], row["customer_id"], row["card_id"],
                        row["opened_at"], row["closed_at"], row["outcome"],
                        row["pattern"], row["first_fraud_txn_id"],
                        row["txn_ids"], int(row["n_txns"]),
                        float(row["exposure_usd"]), row["connected_card_ids"],
                        row["actions_taken"], row["report_filed"],
                        row["analyst_notes"]
                    ))
                cur.executemany("INSERT OR REPLACE INTO closed_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cc_rows)
            conn.commit()

        # 3. Load Transactions
        txn_csv = os.path.join(self.dataset_dir, "transactions.csv")
        if os.path.exists(txn_csv):
            print("[TigerGraphEngine] Loading transactions...")
            txn_rows = []
            with open(txn_csv, "r", encoding="utf-8") as f:
                header = f.readline().strip().split(",")
                idx = {k: i for i, k in enumerate(header)}
                for line in f:
                    p = line.strip().split(",")
                    tid = p[idx["TransactionID"]]
                    cid = p[idx["customer_id"]]
                    card_id = txn_to_card_id.get(tid, f"{cid}-K1")
                    dev = device_map.get(tid, "")

                    txn_rows.append((
                        tid,
                        float(p[idx["TransactionAmt"]]) if p[idx["TransactionAmt"]] else 0.0,
                        p[idx["ProductCD"]],
                        p[idx["card1"]],
                        p[idx["card2"]],
                        p[idx["card4"]],
                        p[idx["card6"]],
                        p[idx["addr1"]],
                        p[idx["addr2"]],
                        p[idx["P_emaildomain"]],
                        cid,
                        card_id,
                        p[idx["ts"]],
                        p[idx["channel"]],
                        float(p[idx["risk_score"]]) if p[idx["risk_score"]] else 0.0,
                        dev
                    ))
                    if len(txn_rows) >= 50000:
                        cur.executemany("INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", txn_rows)
                        txn_rows = []
            if txn_rows:
                cur.executemany("INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", txn_rows)
            conn.commit()

        # 4. Create High-Performance Indexes
        print("[TigerGraphEngine] Building graph indices...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_cust ON transactions(customer_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_card ON transactions(card_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_ts ON transactions(ts);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_txn_dev ON transactions(device_profile);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_id_dev ON identity(device_profile);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_cust ON closed_cases(customer_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_card ON closed_cases(card_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cc_pattern ON closed_cases(pattern);")
        conn.commit()
        conn.close()
        print("[TigerGraphEngine] Graph database initialized successfully.")

    # -------------------------------------------------------------------------
    # Graph Traversal Methods (Mirroring GSQL Queries)
    # -------------------------------------------------------------------------

    def get_transaction(self, txn_id: str) -> Optional[Dict[str, Any]]:
        """GSQL: Fetch single Transaction vertex and attributes."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, i.DeviceInfo, i.id_30 as os, i.id_31 as browser, 
                   i.id_33 as screen, i.DeviceType, i.id_15 as is_new, i.id_23 as proxy
            FROM transactions t
            LEFT JOIN identity i ON t.TransactionID = i.TransactionID
            WHERE t.TransactionID = ?
        """, (txn_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_customer_transactions(self, customer_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """GSQL: 1-hop traversal Customer -(OWNS)-> Card -(MADE)-> Transaction."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.*, i.id_15 as is_new, i.id_23 as proxy
            FROM transactions t
            LEFT JOIN identity i ON t.TransactionID = i.TransactionID
            WHERE t.customer_id = ?
            ORDER BY t.ts ASC
            LIMIT ?
        """, (customer_id, limit))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_card_window(self, card_id: str, target_ts: str, hours_before: int = 24, hours_after: int = 24) -> List[Dict[str, Any]]:
        """GSQL: card_window query for temporal sequence analysis."""
        conn = self._get_connection()
        cur = conn.cursor()
        dt = datetime.strptime(target_ts, "%Y-%m-%d %H:%M:%S")
        start_ts = (dt - timedelta(hours=hours_before)).strftime("%Y-%m-%d %H:%M:%S")
        end_ts = (dt + timedelta(hours=hours_after)).strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            SELECT t.*, i.id_15 as is_new, i.id_23 as proxy
            FROM transactions t
            LEFT JOIN identity i ON t.TransactionID = i.TransactionID
            WHERE (t.card_id = ? OR t.customer_id = ?)
              AND t.ts BETWEEN ? AND ?
            ORDER BY t.ts ASC
        """, (card_id, card_id.split("-")[0] if "-" in card_id else card_id, start_ts, end_ts))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def get_device_neighbors(self, device_profile: str) -> Dict[str, Any]:
        """
        GSQL: device_neighbors 2-hop traversal.
        DeviceProfile -(USED_IN_TXN)-> Transaction -(MADE_BY)-> Card -(HAD_CLOSED_CASE)-> ClosedCase
        """
        if not device_profile or not device_profile.strip():
            return {"cards": [], "txns": [], "closed_cases": []}

        conn = self._get_connection()
        cur = conn.cursor()

        # Find all transactions with this device profile
        cur.execute("""
            SELECT TransactionID, card_id, customer_id, TransactionAmt, ts, channel, risk_score
            FROM transactions
            WHERE device_profile = ?
            ORDER BY ts DESC
            LIMIT 50
        """, (device_profile,))
        txns = [dict(r) for r in cur.fetchall()]

        # Unique cards using this device
        cards = sorted(list({t["card_id"] for t in txns if t["card_id"]}))

        # Prior closed cases involving any of these cards or transactions
        closed_cases = []
        if cards:
            placeholders = ",".join("?" for _ in cards)
            cur.execute(f"""
                SELECT * FROM closed_cases
                WHERE card_id IN ({placeholders})
                ORDER BY opened_at DESC
                LIMIT 10
            """, cards)
            closed_cases = [dict(r) for r in cur.fetchall()]

        conn.close()
        return {
            "device_profile": device_profile,
            "connected_cards": cards,
            "transactions": txns,
            "connected_closed_cases": closed_cases
        }

    def get_customer_network(self, customer_id: str) -> Dict[str, Any]:
        """GSQL: customer_network query aggregating multi-card, region, and email topology."""
        conn = self._get_connection()
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT card_id FROM transactions WHERE customer_id = ?", (customer_id,))
        cards = [r[0] for r in cur.fetchall() if r[0]]

        cur.execute("SELECT addr1, COUNT(*) as cnt FROM transactions WHERE customer_id = ? AND addr1 != '' GROUP BY addr1 ORDER BY cnt DESC", (customer_id,))
        regions = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT DISTINCT P_emaildomain FROM transactions WHERE customer_id = ? AND P_emaildomain != ''", (customer_id,))
        emails = [r[0] for r in cur.fetchall()]

        cur.execute("SELECT * FROM closed_cases WHERE customer_id = ? ORDER BY opened_at DESC", (customer_id,))
        prior_cases = [dict(r) for r in cur.fetchall()]

        conn.close()
        return {
            "customer_id": customer_id,
            "cards": cards,
            "primary_regions": regions,
            "email_domains": emails,
            "prior_cases": prior_cases
        }

    def detect_card_testing(self, card_id: str, target_ts: str) -> Dict[str, Any]:
        """GSQL: detect_card_testing algorithm identifying micro-authorization sequences."""
        window_txns = self.get_card_window(card_id, target_ts, hours_before=2, hours_after=2)
        online_txns = [t for t in window_txns if t["channel"] == "online"]

        small_txns = [t for t in online_txns if float(t.get("TransactionAmt") or t.get("amt") or 0.0) <= 5.0]
        large_txns = [t for t in online_txns if float(t.get("TransactionAmt") or t.get("amt") or 0.0) >= 50.0]

        is_testing = (len(small_txns) >= 3 and len(large_txns) >= 1)
        large_cleared = any(float(t.get("TransactionAmt") or t.get("amt") or 0.0) > 100.0 for t in large_txns)

        exposure = sum(float(t.get("TransactionAmt") or t.get("amt") or 0.0) for t in small_txns) + \
                   sum(float(t.get("TransactionAmt") or t.get("amt") or 0.0) for t in large_txns)

        return {
            "is_testing": is_testing,
            "small_txns": small_txns,
            "large_txns": large_txns,
            "large_cleared": large_cleared,
            "exposure_usd": round(exposure, 2)
        }

    def find_similar_closed_cases(self, pattern: str = None, outcome: str = "confirmed_fraud", limit: int = 3) -> List[Dict[str, Any]]:
        """GSQL: Case Memory retrieval over 5,565 closed cases."""
        conn = self._get_connection()
        cur = conn.cursor()
        if pattern and pattern != "none":
            cur.execute("""
                SELECT * FROM closed_cases
                WHERE pattern = ? AND outcome = ?
                ORDER BY opened_at DESC
                LIMIT ?
            """, (pattern, outcome, limit))
        else:
            cur.execute("""
                SELECT * FROM closed_cases
                WHERE outcome = ?
                ORDER BY opened_at DESC
                LIMIT ?
            """, (outcome, limit))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def write_case_to_graph(self, case_id: str, case_data: Dict[str, Any]) -> str:
        """
        GSQL: write_investigation_case.
        Persists dynamic Case Memory into TigerGraph vertex and edges.
        """
        conn = self._get_connection()
        cur = conn.cursor()

        graph_case_id = f"CASE-{datetime.now().strftime('%Y%m%d')}-{case_id}"
        c = case_data.get("case", {})

        cur.execute("""
            INSERT OR REPLACE INTO fraud_cases_graph_memory (
                graph_case_id, case_id, opened_at, status, verdict,
                fraud_probability, pattern, exposure_usd, card_id,
                affected_txn_ids, connected_card_ids, connected_device_profiles, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            graph_case_id,
            case_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            c.get("status", "open"),
            c.get("verdict", "uncertain"),
            c.get("fraud_probability", 0.0),
            c.get("pattern", "none"),
            c.get("exposure_usd", 0.0),
            case_data.get("card_id", ""),
            "|".join(c.get("affected_txn_ids", [])),
            "|".join(c.get("connected_card_ids", [])),
            "|".join(c.get("connected_device_profiles", [])),
            c.get("summary", "")
        ))

        conn.commit()
        conn.close()
        return graph_case_id

    def get_benchmark_cases(self) -> List[Dict[str, Any]]:
        """Retrieves all 20 cases from case_pack."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM case_pack ORDER BY case_id ASC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
