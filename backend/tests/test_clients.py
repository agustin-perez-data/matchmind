"""How the agents decide to reach Foundry, and that telemetry stays off without a connection string. No network."""

from __future__ import annotations

import pytest

from matchmind.agents import clients, observability


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("FOUNDRY_PROJECT_ENDPOINT", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "MATCHMIND_AUTH",
              "APPLICATIONINSIGHTS_CONNECTION_STRING"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(clients, "load_env", lambda: None)  # never read backend/.env in tests


def test_auth_mode_prefers_the_project_then_key_then_identity(monkeypatch):
    assert clients.auth_mode() is None and not clients.foundry_configured()
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.cognitiveservices.azure.com/")
    assert clients.auth_mode() is None  # endpoint alone is not enough
    monkeypatch.setenv("MATCHMIND_AUTH", "identity")
    assert clients.auth_mode() == "identity"
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    assert clients.auth_mode() == "key"
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://x.services.ai.azure.com/api/projects/p")
    assert clients.auth_mode() == "project" and clients.foundry_configured()
    assert clients.project_endpoint().endswith("/projects/p")
    assert "project" in clients.describe_auth()


def test_chat_client_without_configuration_raises(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1-mini")
    with pytest.raises(RuntimeError):
        clients.chat_client("fast")


def test_chat_client_builds_the_key_client(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_FAST", "gpt-4.1-mini")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "k")
    client = clients.chat_client("fast")
    assert type(client).__name__ == "OpenAIChatCompletionClient"


def test_observability_is_a_no_op_without_a_connection_string():
    assert observability.configure_observability(None) is False
    assert observability.telemetry_enabled() is False
    with observability.moment_span("M", "goal", "analyst", cache_hit=True):
        observability.record_moment(12.5, True, "goal")
    observability.record_tokens("Analyst", {"input": 10, "output": 5})
    observability.record_tokens("Analyst", None)
