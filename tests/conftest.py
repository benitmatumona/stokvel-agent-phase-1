import pytest


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """Tests must never call Groq, even if a real key is in your .env.

    Tests that need a key set one themselves with monkeypatch.
    """
    monkeypatch.setattr("agent.llm.GROQ_API_KEY", None)
