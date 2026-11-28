import pytest


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """Tests must never call Groq, even if a real key is in your .env.

    Tests that need a key set one themselves with monkeypatch.
    """
    monkeypatch.setattr("agent.llm.GROQ_API_KEY", None)


@pytest.fixture(autouse=True)
def no_real_supabase_or_deploys(monkeypatch):
    """Tests never touch Supabase, a validator or devnet, whatever is in .env."""
    monkeypatch.setattr("agent.config.SUPABASE_URL", "")
    monkeypatch.setattr("agent.config.SUPABASE_KEY", None)
    monkeypatch.setattr("agent.config.TEST_MODE", True)
