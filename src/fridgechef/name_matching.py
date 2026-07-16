from __future__ import annotations

from src.fridgechef.availability import normalize_text


def _singularize_word(word: str) -> str:
    """Apply conservative Spanish and English plural rules for inventory matching."""
    if len(word) <= 3:
        return word
    if word.endswith("ces") and len(word) > 4:
        return word[:-3] + "z"
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4 and word[-3] not in "aeiou":
        return word[:-2]
    if word.endswith("s") and len(word) > 3 and word[-2] in "aeiou":
        return word[:-1]
    return word


def inventory_name_key(value: object) -> str:
    """Create a stable key that matches common singular and plural food names."""
    normalized = normalize_text(str(value or ""))
    words = normalized.split()
    if not words:
        return ""
    words[-1] = _singularize_word(words[-1])
    return " ".join(words)
