import asyncio
from types import SimpleNamespace

import httpx

import tutor_service


def test_transient_provider_failures_are_retried(monkeypatch) -> None:
    class FlakyAgent:
        calls = 0

        async def run(self, prompt: str) -> SimpleNamespace:
            del prompt
            self.calls += 1
            if self.calls < 3:
                raise httpx.ConnectError("temporary outage")
            return SimpleNamespace(output="verified output")

    async def no_delay(seconds: float) -> None:
        del seconds

    monkeypatch.setattr(tutor_service.asyncio, "sleep", no_delay)
    agent = FlakyAgent()

    assert asyncio.run(tutor_service._run(agent, "prompt")) == "verified output"
    assert agent.calls == 3
