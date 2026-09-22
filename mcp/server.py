"""
TigerGraph Model Context Protocol (MCP) Server.
Exposes TigerGraph database capabilities, graph traversals, and algorithms
as standardized MCP tools for AI agents and LLM orchestration.
Reference: https://github.com/tigergraph/tigergraph-mcp
"""

import json
from typing import Dict, Any, List
from graph.tigergraph_connector import TigerGraphConnector


class TigerGraphMCPServer:
    def __init__(self):
        self.tg = TigerGraphConnector()

    def list_tools(self) -> List[Dict[str, Any]]:
        """Returns the list of available MCP tools and schemas."""
        return [
            {
                "name": "tg_card_window",
                "description": "Retrieve transactions on a payment card within a temporal window around a target timestamp.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "The card identifier, e.g., C01234-K1"},
                        "target_ts": {"type": "string", "description": "Timestamp in YYYY-MM-DD HH:MM:SS format"},
                        "hours_before": {"type": "integer", "description": "Hours to look back before target timestamp", "default": 24},
                        "hours_after": {"type": "integer", "description": "Hours to look forward after target timestamp", "default": 24}
                    },
                    "required": ["card_id", "target_ts"]
                }
            },
            {
                "name": "tg_device_neighbors",
                "description": "Perform 2-hop graph traversal from a DeviceProfile to discover all connected cards, transactions, and historical fraud cases.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_profile": {"type": "string", "description": "Device signature string (DeviceInfo | OS | Browser | Screen)"}
                    },
                    "required": ["device_profile"]
                }
            },
            {
                "name": "tg_customer_network",
                "description": "Inspect customer topology: all owned payment cards, normal billing regions, email domains, and past investigations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Customer identifier, e.g., C01234"}
                    },
                    "required": ["customer_id"]
                }
            },
            {
                "name": "tg_detect_card_testing",
                "description": "Graph algorithm identifying micro-authorization sequences (3+ small online transactions < $5 followed by larger purchase).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string", "description": "Target card ID"},
                        "target_ts": {"type": "string", "description": "Target transaction timestamp"}
                    },
                    "required": ["card_id", "target_ts"]
                }
            },
            {
                "name": "tg_search_closed_cases",
                "description": "Retrieve historical closed investigations from case memory matching a typology or outcome to ground agent reasoning.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Typology pattern to filter by (or empty for any)"},
                        "limit": {"type": "integer", "description": "Maximum number of past cases to retrieve", "default": 3}
                    }
                }
            },
            {
                "name": "tg_write_case_vertex",
                "description": "Store the concluded investigation, findings, decisions, and connected entities into TigerGraph case memory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string", "description": "Case identifier, e.g., HHG-001"},
                        "case_data": {"type": "object", "description": "Complete investigation deliverable object"}
                    },
                    "required": ["case_id", "case_data"]
                }
            }
        ]

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an MCP tool call to the underlying TigerGraph engine."""
        if tool_name == "tg_card_window":
            return {
                "transactions": self.tg.query_card_window(
                    card_id=arguments["card_id"],
                    target_ts=arguments["target_ts"],
                    hours_before=arguments.get("hours_before", 24),
                    hours_after=arguments.get("hours_after", 24)
                )
            }
        elif tool_name == "tg_device_neighbors":
            return self.tg.query_device_neighbors(device_profile=arguments["device_profile"])
        elif tool_name == "tg_customer_network":
            return self.tg.query_customer_network(customer_id=arguments["customer_id"])
        elif tool_name == "tg_detect_card_testing":
            return self.tg.query_card_testing(card_id=arguments["card_id"], target_ts=arguments["target_ts"])
        elif tool_name == "tg_search_closed_cases":
            return {
                "similar_cases": self.tg.local_engine.find_similar_closed_cases(
                    pattern=arguments.get("pattern"),
                    limit=arguments.get("limit", 3)
                )
            }
        elif tool_name == "tg_write_case_vertex":
            graph_id = self.tg.write_case_memory(
                case_id=arguments["case_id"],
                case_data=arguments["case_data"]
            )
            return {"graph_case_id": graph_id, "status": "persisted"}
        else:
            raise ValueError(f"Unknown MCP tool: {tool_name}")
