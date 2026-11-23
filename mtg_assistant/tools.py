"""Scryfall-backed tools the agent can call.

Scryfall API docs: https://scryfall.com/docs/api
Etiquette: send a User-Agent + Accept header and wait 50-100 ms between requests.
"""

from __future__ import annotations

import time
from typing import Any

import requests

SCRYFALL_BASE = "https://api.scryfall.com"
HEADERS = {
    "User-Agent": "MTGRulesAssistant/0.1 (portfolio project)",
    "Accept": "application/json",
}
_MIN_INTERVAL_S = 0.1
_last_request_at = 0.0


class ToolError(Exception):
    """Raised when a tool can't produce a result (card not found, API down)."""


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global _last_request_at
    wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    url = path if path.startswith("http") else f"{SCRYFALL_BASE}{path}"
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
    except requests.RequestException as exc:
        raise ToolError(f"Scryfall request failed: {exc}") from exc
    finally:
        _last_request_at = time.monotonic()

    data = resp.json() if resp.content else {}
    if resp.status_code == 404:
        raise ToolError(data.get("details", "Not found"))
    if resp.status_code >= 400:
        raise ToolError(f"Scryfall error {resp.status_code}: {data.get('details', '')}")
    return data


def _summarize_card(card: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields the model needs; double-faced cards keep each face."""
    keys = ("name", "mana_cost", "type_line", "oracle_text", "power", "toughness", "loyalty")
    summary = {k: card[k] for k in keys if k in card}
    summary["keywords"] = card.get("keywords", [])
    summary["scryfall_uri"] = card.get("scryfall_uri")
    if "card_faces" in card:
        summary["faces"] = [{k: f[k] for k in keys if k in f} for f in card["card_faces"]]
    return summary


def get_card(name: str) -> dict[str, Any]:
    """Look up one card by (fuzzy) name and return its Oracle text."""
    card = _get("/cards/named", {"fuzzy": name})
    return _summarize_card(card)


def get_card_rulings(name: str) -> dict[str, Any]:
    """Return official rulings for a card (Wizards + Scryfall notes)."""
    card = _get("/cards/named", {"fuzzy": name})
    rulings = _get(card["rulings_uri"]).get("data", [])
    return {
        "name": card["name"],
        "rulings": [
            {"source": r.get("source"), "date": r.get("published_at"), "text": r.get("comment")}
            for r in rulings
        ],
    }


def search_cards(query: str, limit: int = 5) -> dict[str, Any]:
    """Search with Scryfall syntax, e.g. 'o:deathtouch t:creature cmc<=2'."""
    try:
        data = _get("/cards/search", {"q": query, "order": "edhrec"})
    except ToolError:
        return {"total": 0, "cards": []}
    cards = [_summarize_card(c) for c in data.get("data", [])[:limit]]
    return {"total": data.get("total_cards", len(cards)), "cards": cards}


# ---- Tool registry: Bedrock Converse toolSpec + Python implementation ----

TOOLS: dict[str, dict[str, Any]] = {
    "get_card": {
        "fn": get_card,
        "spec": {
            "name": "get_card",
            "description": "Get a Magic: The Gathering card's official Oracle text, type, "
            "cost and keywords by name. Fuzzy names are OK.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Card name"}},
                "required": ["name"],
            }},
        },
    },
    "get_card_rulings": {
        "fn": get_card_rulings,
        "spec": {
            "name": "get_card_rulings",
            "description": "Get official rulings for a card. Use for questions about "
            "how a card interacts with other cards or rules.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Card name"}},
                "required": ["name"],
            }},
        },
    },
    "search_cards": {
        "fn": search_cards,
        "spec": {
            "name": "search_cards",
            "description": "Search cards using Scryfall query syntax (e.g. "
            "'o:\"draw a card\" t:instant c:u'). Use when the user describes a card "
            "but doesn't name it.",
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Scryfall search query"},
                    "limit": {"type": "integer", "description": "Max results (1-10)"},
                },
                "required": ["query"],
            }},
        },
    },
}


def run_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise ToolError(f"Unknown tool: {name}")
    return TOOLS[name]["fn"](**tool_input)
