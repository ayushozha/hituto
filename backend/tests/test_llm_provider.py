"""Provider robustness: routes that reject `temperature` get it stripped and cached."""
from app.providers.llm import (
    _TEMPERATURE_UNSUPPORTED,
    OpenAICompatLLM,
    model_rejects_temperature,
)


def test_claude5_models_omit_temperature_upfront() -> None:
    """Claude 5 OpenAI-compat routes reject temperature — never send it (no 400 round-trip)."""
    for model in ("claude-sonnet-5", "claude-opus-5", "claude-haiku-5", "claude-sonnet-5-20260301"):
        assert model_rejects_temperature(model), model
        llm = OpenAICompatLLM(base_url="https://api.anthropic.com/v1", api_key="k", model=model)
        assert "temperature" not in llm._chat_payload([], temperature=0.6, max_tokens=5)

    # Claude 4.5 / 4.6 still accept temperature.
    for model in ("claude-sonnet-4-5", "claude-opus-4-5", "claude-haiku-4-5", "claude-opus-4-6"):
        assert not model_rejects_temperature(model), model
        llm = OpenAICompatLLM(base_url="https://api.anthropic.com/v1", api_key="k", model=model)
        assert "temperature" in llm._chat_payload([], temperature=0.6, max_tokens=5)


def test_temperature_strip_marks_route_and_persists() -> None:
    llm = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="quirky-model")
    key = ("https://router.test", "quirky-model")
    try:
        assert "temperature" in llm._chat_payload([], temperature=0.6, max_tokens=5)
        # The router-style rejection marks the route for an immediate retry…
        assert llm._mark_temperature_unsupported(
            400, '{"error":{"message":"invalid temperature: only 1 is allowed"}}', sent=True
        )
        # …after which every payload (buffered and streaming) omits the parameter.
        p = llm._chat_payload([], temperature=0.6, max_tokens=5, stream=True)
        assert "temperature" not in p and p["stream"] is True
        assert "temperature" not in llm._chat_payload([], temperature=0.2, max_tokens=5)
        # Section fan-out fires N requests before any of them sees the 400 — every caller
        # that already sent the parameter must retry, not just the one that marked it.
        assert llm._mark_temperature_unsupported(400, "invalid temperature", sent=True)
        # A retry that already omitted the parameter doesn't signal again (no infinite loop).
        assert not llm._mark_temperature_unsupported(400, "invalid temperature", sent=False)
        # A fresh instance for the same route inherits the knowledge (module cache).
        again = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="quirky-model")
        assert "temperature" not in again._chat_payload([], temperature=0.6, max_tokens=5)
        # Unrelated 400s never strip temperature.
        other = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="fine-model")
        assert not other._mark_temperature_unsupported(400, "context length exceeded", sent=True)
        assert "temperature" in other._chat_payload([], temperature=0.6, max_tokens=5)
    finally:
        _TEMPERATURE_UNSUPPORTED.discard(key)
