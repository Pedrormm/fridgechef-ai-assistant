from __future__ import annotations

import json
import re


class JsonExtractionError(ValueError):
    """Raised when a model response cannot be converted into JSON."""


def extract_json_object(text: str) -> dict:
    """Extract a JSON object even when a model unexpectedly wraps it in text."""
    if not text:
        raise JsonExtractionError("The model returned an empty response. Please try again.")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise JsonExtractionError("The model response did not contain a valid JSON object.")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JsonExtractionError("The model returned JSON-like text, but it could not be parsed.") from exc
