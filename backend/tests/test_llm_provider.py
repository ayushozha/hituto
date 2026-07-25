"""Provider robustness: routes that reject `temperature` get it stripped and cached."""
from app.providers.llm import _TEMPERATURE_UNSUPPORTED, OpenAICompatLLM


def test_temperature_strip_marks_route_and_persists() -> None:
    llm = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="quirky-model")
    key = ("https://router.test", "quirky-model")
    try:
        assert "temperature" in llm._chat_payload([], temperature=0.6, max_tokens=5)
        # The router-style rejection marks the route for an immediate retry…
        assert llm._mark_temperature_unsupported(
            400, '{"error":{"message":"invalid temperature: only 1 is allowed"}}'
        )
        # …after which every payload (buffered and streaming) omits the parameter.
        p = llm._chat_payload([], temperature=0.6, max_tokens=5, stream=True)
        assert "temperature" not in p and p["stream"] is True
        assert "temperature" not in llm._chat_payload([], temperature=0.2, max_tokens=5)
        # Marked once — later 400s don't signal another retry (no infinite loop).
        assert not llm._mark_temperature_unsupported(400, "invalid temperature")
        # A fresh instance for the same route inherits the knowledge (module cache).
        again = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="quirky-model")
        assert "temperature" not in again._chat_payload([], temperature=0.6, max_tokens=5)
        # Unrelated 400s never strip temperature.
        other = OpenAICompatLLM(base_url="https://router.test", api_key="k", model="fine-model")
        assert not other._mark_temperature_unsupported(400, "context length exceeded")
        assert "temperature" in other._chat_payload([], temperature=0.6, max_tokens=5)
    finally:
        _TEMPERATURE_UNSUPPORTED.discard(key)
