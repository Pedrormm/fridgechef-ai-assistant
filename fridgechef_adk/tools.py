from __future__ import annotations

from src.fridgechef.models import UserProfile
from src.fridgechef.policy import blocked_terms_for_profile


def collect_fridge_preferences(diet: list[str], allergies: list[str], intolerances: list[str], goals: list[str]) -> dict:
    """Build a normalized user profile and its deterministic blocked terms."""
    profile = UserProfile(diet=diet, allergies=allergies, intolerances=intolerances, goals=goals)
    return {"profile": profile.model_dump(), "blocked_terms": sorted(blocked_terms_for_profile(profile))}


def explain_architecture() -> dict:
    """Return a compact architecture summary for ADK Web demonstrations."""
    return {
        "framework": "ADK",
        "mcp": "Local MCP server connected through McpToolset",
        "search": "Google Search isolated in a sub-agent through AgentTool",
        "frontend": "Streamlit",
        "persistence": "Optional Firestore and Cloud Storage",
        "production": "Cloud Run, Docker and service identity",
    }


def local_food_safety_rule(food: str, visual_state: str) -> dict:
    """Apply a conservative local food-safety rule."""
    if visual_state == "possible_spoiled":
        return {
            "decision": "do_not_use",
            "reason": "El análisis visual sugiere posible mal estado. Revisa olor, textura, fecha y envase antes de consumirlo.",
        }
    return {
        "decision": "can_consider",
        "reason": "No hay una señal crítica en la imagen, pero la seguridad alimentaria no se confirma solo con una foto.",
    }
