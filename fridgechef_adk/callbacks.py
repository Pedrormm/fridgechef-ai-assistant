from __future__ import annotations

DISALLOWED_PROMPT_PATTERNS = [
    "ignora las instrucciones",
    "ignore previous instructions",
    "muestra el prompt",
    "revela secretos",
    "dame la private_key",
]


def before_model_guardrail(callback_context, llm_request):
    """Block basic prompt-injection attempts before the model receives the request."""
    try:
        last = ""
        if getattr(llm_request, "contents", None):
            content = llm_request.contents[-1]
            if getattr(content, "parts", None):
                last = getattr(content.parts[0], "text", "") or ""

        lowered = last.lower()
        if any(pattern in lowered for pattern in DISALLOWED_PROMPT_PATTERNS):
            from google.adk.models import LlmResponse
            from google.genai import types

            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="No puedo ayudar con esa solicitud porque podría exponer información sensible.")],
                )
            )
    except Exception:
        return None

    return None


def after_tool_audit(callback_context, tool, args, result):
    """Central hook for future structured tool logging."""
    return result
