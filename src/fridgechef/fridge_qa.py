from __future__ import annotations

try:
    from google.genai import types
except Exception:  # pragma: no cover - allows local tests without google-genai installed
    types = None

from src.fridgechef.config import get_settings
from src.fridgechef.inventory import friendly_state_label
from src.fridgechef.json_utils import extract_json_object
from src.fridgechef.llm_client import get_client
from src.fridgechef.models import FridgeQuestionDecision, InventoryItem
from src.fridgechef.spanish_guard import ensure_fridge_question_spanish


def _format_inventory(items: list[InventoryItem]) -> str:
    """Format inventory items as a short natural language list."""
    if not items:
        return "Todavía no tengo alimentos guardados en tu nevera."
    names = [item.name for item in items]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" y {names[-1]}"


def _is_review_state(state: str) -> bool:
    """Return whether a saved item should be highlighted for review."""
    return state == "aging" or state == "possible_spoiled" or state == "spoiled"


def _local_answer(question: str, inventory: list[InventoryItem]) -> str:
    """Safe local fallback when the question-routing agent cannot be reached."""
    if not inventory:
        return "Todavía no tengo alimentos guardados. Analiza la nevera o escribe ingredientes y podré responder mejor."
    risky = [item for item in inventory if item.expiry_text or _is_review_state(item.state)]
    if risky:
        lines = [f"- {item.name}: {item.expiry_text or friendly_state_label(item.state)}" for item in risky]
        return "Esto es lo que conviene revisar primero:\n" + "\n".join(lines)
    return f"Ahora mismo tengo guardado en tu nevera: {_format_inventory(inventory)}."


def _agent_answer(question: str, inventory: list[InventoryItem]) -> FridgeQuestionDecision:
    """Route and answer a user question with a fridge-scoped language agent."""
    client = get_client()
    settings = get_settings()
    prompt = f"""
Eres el agente de preguntas sobre la nevera de FridgeChef AI Assistant.

Tarea:
- Responde solo preguntas relacionadas con el inventario guardado, alimentación, caducidades, ideas de cocina o prioridades de uso.
- Si la pregunta no pertenece a ese ámbito, no respondas al tema externo y redirige de forma amable.
- Usa solo el inventario indicado. No inventes elementos, fechas, cantidades ni recetas.
- Todos los textos visibles deben estar en español de España.
- Devuelve solo JSON válido.

Pregunta del usuario:
{question}

Inventario guardado:
{[item.model_dump() for item in inventory]}

Estructura obligatoria:
{{
  "is_fridge_related": true,
  "answer": "respuesta amable en español si está relacionada",
  "friendly_redirect": "redirección amable en español si no está relacionada"
}}
"""
    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json"),
    )
    decision = FridgeQuestionDecision.model_validate(extract_json_object(response.text))
    return ensure_fridge_question_spanish(decision)


def answer_fridge_question(question: str, inventory: list[InventoryItem]) -> str:
    """Answer fridge questions without leaving the food/inventory domain."""
    if not question.strip():
        return "Pregúntame algo sobre tu nevera guardada y te ayudo."
    try:
        decision = ensure_fridge_question_spanish(_agent_answer(question, inventory))
        if decision.is_fridge_related:
            return decision.answer or _local_answer(question, inventory)
        return decision.friendly_redirect or (
            "Puedo ayudarte con alimentos guardados, caducidades e ideas de recetas. Para otros temas, mejor usa otra consulta aparte."
        )
    except Exception:
        return _local_answer(question, inventory)
