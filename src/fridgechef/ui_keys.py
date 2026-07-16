from __future__ import annotations

import re


def _slug(value: object) -> str:
    """Convert arbitrary display text into a stable Streamlit key segment."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "")).strip("_").lower() or "item"


def inventory_action_key(
    namespace: str,
    action: str,
    item_name: str,
    index: int,
) -> str:
    """Build a unique key for one inventory action in one rendered section."""
    return "_".join(
        (
            _slug(namespace),
            _slug(action),
            "inventory",
            str(max(0, int(index))),
            _slug(item_name),
        )
    )
