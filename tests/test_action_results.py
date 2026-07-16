from src.fridgechef.action_results import (
    restore_manual_parse_result,
    snapshot_manual_parse_result,
)
from src.fridgechef.models import IgnoredTextFragment, IngredientMention
from src.fridgechef.text_parser import ManualIngredientParseResult


def test_manual_parse_result_round_trip_preserves_structured_feedback():
    original = ManualIngredientParseResult(
        accepted=["2 patatas"],
        ignored=["una bombilla"],
        accepted_items=[
            IngredientMention(
                name="patatas",
                quantity_label="2 unidades",
                state="fresh",
                source_text="2 patatas",
                confidence=0.95,
            )
        ],
        ignored_fragments=[
            IgnoredTextFragment(
                text="una bombilla",
                reason="No es un alimento.",
            )
        ],
        agent_notes=["tested"],
        used_agent=True,
        search_used=True,
        search_queries=["patata alimento"],
    )

    restored = restore_manual_parse_result(snapshot_manual_parse_result(original))

    assert restored == original


def test_invalid_snapshot_is_ignored_safely():
    assert restore_manual_parse_result(None) is None
    assert restore_manual_parse_result("invalid") is None
    assert restore_manual_parse_result({"accepted_items": [{"bad": "shape"}]}) is None
