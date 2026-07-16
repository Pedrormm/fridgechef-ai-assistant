from __future__ import annotations

import re


def replace_once(text: str, old: str, new: str, description: str) -> str:
    """Replace one exact source block and fail if the target has drifted."""
    occurrences = text.count(old)
    if occurrences != 1:
        raise RuntimeError(f"Expected exactly one {description} block, found {occurrences}.")
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, replacement: str, description: str) -> str:
    """Replace one regex-delimited source block and fail if it is ambiguous."""
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {description} block, found {count}.")
    return updated
