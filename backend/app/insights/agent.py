"""Focused LangChain agent for evidence-bound personal learning narratives."""
from __future__ import annotations

import json

from ..core.config import get_settings
from ..schemas.insight import InsightReport

_SYSTEM_PROMPT = """You are Hi Tuto's private personal learning insight agent.
Use only the supplied aggregate evidence and the supplied deterministic interest
and struggle profiles. Rewrite only entries in `supported_observations`; preserve each
entry's kind and exact evidence_keys. Never create a new claim, struggle, interest, or
topic. Never infer curiosity, motivation, engagement, attention, personality, ability,
intelligence, talent, learning style, or question quality from activity counts. Never
diagnose, grade, rank, or predict. Practice accuracy describes recorded answers; answer
time and tutor reply time are timing signals, never mastery or quality. Help-seeking is
neutral. Do not mention teachers, parents, surveillance, or other learners. Make at
most three concise, warm observations. Treat weak evidence as uncertain. Return the
required structured response and nothing else.
"""


async def generate_report(context: dict) -> InsightReport | None:
    """Generate a validated report, failing closed when the optional model is unavailable."""
    settings = get_settings()
    if not settings.insights_agent_enabled or not settings.resolved_insights_llm_api_key():
        return None
    try:
        from langchain.agents import create_agent
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.resolved_insights_llm_model(),
            api_key=settings.resolved_insights_llm_api_key(),
            base_url=settings.resolved_insights_llm_base_url(),
            temperature=0.2,
            max_retries=1,
            timeout=30,
        )
        agent = create_agent(
            model=model,
            tools=[],
            system_prompt=_SYSTEM_PROMPT,
            response_format=InsightReport,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": json.dumps(context)}]},
            config={"recursion_limit": 4},
        )
        response = result.get("structured_response")
        return response if isinstance(response, InsightReport) else InsightReport.model_validate(response)
    except Exception:
        return None
