"""The 'Market Intelligence' crew (docs/03-agent-crews.md, 3.1).

Chief Strategist (orchestrator) coordinating Trend Spotter, Competitor Analyst,
and Audience Profiler. Mirrors the reference implementation's crew definition.
"""

from __future__ import annotations

from ..constitution import BrandConstitution
from ..models import CrewName
from ..vault import Vault
from .base import Agent, Crew, Task
from .blackboard import Blackboard, EventBus

DISPLAY_NAME = "Market Intelligence"
DESCRIPTION = (
    "The brand's sensory apparatus: detect trends, analyze competitors, and "
    "profile the audience, then synthesize an actionable intelligence brief."
)


def build(
    *,
    blackboard: Blackboard,
    vault: Vault,
    constitution: BrandConstitution,
) -> Crew:
    orchestrator = Agent(
        role="Chief Strategist",
        goal="Orchestrate market analysis and synthesize an intelligence report.",
        backstory=(
            "A seasoned strategist who understands the byoungimprovements brand and "
            "delegates to specialized agents."
        ),
        artifact_type="intelligence_brief",
    )

    tasks = [
        Task(
            description="Identify the top five emerging trends relevant to the target niche.",
            agent=Agent(
                role="Trend Spotter",
                goal="Identify emerging trends in the personal and business development space.",
                backstory="Analyzes social media, news feeds and forums to detect shifts and patterns.",
                artifact_type="trend_report",
            ),
        ),
        Task(
            description="Analyze three major competitors and summarize their recent strategies.",
            agent=Agent(
                role="Competitor Analyst",
                goal="Analyze competitor strategies and extract actionable insights.",
                backstory="Benchmarks competitor content and uncovers market gaps.",
                artifact_type="competitor_analysis",
            ),
        ),
        Task(
            description="Create an audience profile with demographic and psychographic insights.",
            agent=Agent(
                role="Audience Profiler",
                goal="Describe audience demographics, interests and pain points.",
                backstory="Deep knowledge of psychographics and community sentiment.",
                artifact_type="audience_profile",
            ),
        ),
    ]

    return Crew(
        name=CrewName.MARKET_INTELLIGENCE,
        display_name=DISPLAY_NAME,
        orchestrator=orchestrator,
        tasks=tasks,
        blackboard=blackboard,
        event_bus=EventBus(),
        vault=vault,
        constitution=constitution,
    )
