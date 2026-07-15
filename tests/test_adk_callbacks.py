from fridgechef_adk.callbacks import after_tool_audit


def test_after_tool_audit_accepts_current_adk_keyword_signature():
    assert after_tool_audit(
        tool="demo_tool",
        args={"food": "tomate"},
        tool_context=object(),
        tool_response={"ok": True},
    ) is None


def test_after_tool_audit_accepts_older_positional_signature():
    assert after_tool_audit(object(), "demo_tool", {}, {"ok": True}) is None
