from __future__ import annotations

from typing import Any

from src.fridgechef.models import IgnoredTextFragment, IngredientMention
from src.fridgechef.text_parser import ManualIngredientParseResult


def snapshot_manual_parse_result(result: ManualIngredientParseResult) -> dict[str, Any]:
    """Convert a manual parse result into Streamlit session-safe primitives."""
    return {
        "accepted": list(result.accepted),
        "ignored": list(result.ignored),
        "accepted_items": [item.model_dump() for item in result.accepted_items],
        "ignored_fragments": [fragment.model_dump() for fragment in result.ignored_fragments],
        "agent_notes": list(result.agent_notes),
        "used_agent": bool(result.used_agent),
        "search_used": bool(result.search_used),
        "search_queries": list(result.search_queries),
    }


def restore_manual_parse_result(payload: object) -> ManualIngredientParseResult | None:
    """Restore a manual parse result after the application performs one rerun."""
    if not isinstance(payload, dict):
        return None

    try:
        return ManualIngredientParseResult(
            accepted=[str(value) for value in payload.get("accepted", [])],
            ignored=[str(value) for value in payload.get("ignored", [])],
            accepted_items=[
                IngredientMention.model_validate(item)
                for item in payload.get("accepted_items", [])
            ],
            ignored_fragments=[
                IgnoredTextFragment.model_validate(item)
                for item in payload.get("ignored_fragments", [])
            ],
            agent_notes=[str(value) for value in payload.get("agent_notes", [])],
            used_agent=bool(payload.get("used_agent", False)),
            search_used=bool(payload.get("search_used", False)),
            search_queries=[str(value) for value in payload.get("search_queries", [])],
        )
    except Exception:
        return None
