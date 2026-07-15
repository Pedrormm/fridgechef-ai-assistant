from types import SimpleNamespace


def test_vertex_client_configures_exponential_backoff(monkeypatch, tmp_path):
    from src.fridgechef import llm_client

    missing_credentials = tmp_path / "missing.json"
    settings = SimpleNamespace(
        project_id="test-project",
        credentials_path=str(missing_credentials),
        location="global",
        genai_retry_attempts=4,
        genai_timeout_ms=120_000,
    )
    monkeypatch.setattr(llm_client, "get_settings", lambda: settings)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    captured = {}

    class FakeTypes:
        @staticmethod
        def HttpRetryOptions(**kwargs):
            captured["retry"] = kwargs
            return kwargs

        @staticmethod
        def HttpOptions(**kwargs):
            captured["http"] = kwargs
            return kwargs

    class FakeGenAI:
        @staticmethod
        def Client(**kwargs):
            captured["client"] = kwargs
            return kwargs

    monkeypatch.setattr(llm_client, "genai_types", FakeTypes)
    monkeypatch.setattr(llm_client, "genai", FakeGenAI)

    result = llm_client.get_client()

    assert captured["http"]["timeout"] == 120_000
    assert captured["retry"] == {
        "initial_delay": 1.0,
        "attempts": 4,
        "max_delay": 8.0,
        "exp_base": 2.0,
        "jitter": 1.0,
        "http_status_codes": [408, 429, 500, 502, 503, 504],
    }
    assert result["location"] == "global"
