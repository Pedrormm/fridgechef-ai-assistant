from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app" / "app.py"

_OLD_EXPANDER = "        with st.expander(title, expanded=initially_expanded):\n"
_NEW_EXPANDER = """        with st.expander(
            title,
            expanded=initially_expanded,
            key=f"{key_scope}_expander",
            width="stretch",
        ):
"""


def apply() -> None:
    """Materialize a stable keyed expander for the saved inventory section."""
    source = APP.read_text(encoding="utf-8")
    if _NEW_EXPANDER in source:
        return
    if source.count(_OLD_EXPANDER) != 1:
        raise RuntimeError(
            "Expected exactly one saved-inventory expander call before applying the runtime fix."
        )
    APP.write_text(source.replace(_OLD_EXPANDER, _NEW_EXPANDER, 1), encoding="utf-8")


if __name__ == "__main__":
    apply()
