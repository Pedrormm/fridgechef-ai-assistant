from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app" / "app.py"


def _app_tree() -> ast.Module:
    """Parse the Streamlit entry point without importing or executing the app."""
    return ast.parse(APP.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Return one top-level function and fail clearly when the UI contract drifts."""
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1, f"Expected exactly one {name} function, found {len(matches)}."
    return matches[0]


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    """Read one explicit keyword from a call node."""
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _is_streamlit_call(node: ast.AST, method: str) -> bool:
    """Return whether a node calls one direct method on the Streamlit module."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == method
    )


def test_saved_inventory_renderer_exposes_one_outer_expander() -> None:
    """Keep the complete saved inventory behind one non-nested section control."""
    tree = _app_tree()
    renderer = _function(tree, "show_inventory")
    argument_names = [argument.arg for argument in renderer.args.args]

    assert "collapsible" in argument_names
    assert "initially_expanded" in argument_names

    expanders = [node for node in ast.walk(renderer) if _is_streamlit_call(node, "expander")]
    assert len(expanders) == 1

    expander_call = expanders[0]
    assert isinstance(expander_call.args[0], ast.Name)
    assert expander_call.args[0].id == "title"

    expanded_value = _keyword_value(expander_call, "expanded")
    assert isinstance(expanded_value, ast.Name)
    assert expanded_value.id == "initially_expanded"

    card_renderer = _function(tree, "_render_inventory_cards")
    assert not [node for node in ast.walk(card_renderer) if _is_streamlit_call(node, "expander")]


def test_empty_inventory_message_stays_visible() -> None:
    """Do not hide the explanation when there are no saved food cards to collapse."""
    tree = _app_tree()
    renderer = _function(tree, "show_inventory")
    empty_guards = [
        node
        for node in renderer.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Name)
        and node.test.operand.id == "inventory"
    ]
    assert len(empty_guards) == 1

    guard = empty_guards[0]
    assert any(_is_streamlit_call(node, "subheader") for node in ast.walk(guard))
    assert any(_is_streamlit_call(node, "info") for node in ast.walk(guard))
    assert any(isinstance(node, ast.Return) for node in guard.body)


def test_top_saved_inventory_starts_collapsed() -> None:
    """Configure only the top saved-inventory section as collapsed by default."""
    tree = _app_tree()
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "show_inventory"
    ]

    top_calls = []
    for call in calls:
        namespace = _keyword_value(call, "widget_namespace")
        if isinstance(namespace, ast.Constant) and namespace.value == "saved_inventory_top":
            top_calls.append(call)

    assert len(top_calls) == 1
    top_call = top_calls[0]

    collapsible = _keyword_value(top_call, "collapsible")
    initially_expanded = _keyword_value(top_call, "initially_expanded")
    assert isinstance(collapsible, ast.Constant) and collapsible.value is True
    assert isinstance(initially_expanded, ast.Constant) and initially_expanded.value is False

    other_calls = [call for call in calls if call is not top_call]
    assert all(_keyword_value(call, "collapsible") is None for call in other_calls)
