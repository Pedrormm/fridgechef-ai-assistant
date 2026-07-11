from src.fridgechef.security import is_valid_email, redact_sensitive


def test_email_validation():
    assert is_valid_email("test@example.com")
    assert not is_valid_email("not-an-email")


def test_redact_sensitive():
    data = {"token": "abc", "safe": "ok", "nested": {"private_key": "secret"}}
    redacted = redact_sensitive(data)
    assert redacted["token"] == "***REDACTED***"
    assert redacted["nested"]["private_key"] == "***REDACTED***"
