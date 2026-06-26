"""The 'Marketing & Distribution' crew (docs/03-agent-crews.md, 3.3).

Campaign Manager (orchestrator) coordinating Social Media Manager, Affiliate
Program Manager, and Engagement Bot to publish, monetize, and engage around a
content package. The final campaign plan is gated by HITL before launch.
"""

from __future__ import annotations

from ..constitution import BrandConstitution
from ..models import CrewName
from ..vault import Vault
from .base import Agent, Crew, Task
from .blackboard import Blackboard, EventBus

DISPLAY_NAME = "Marketing & Distribution"
DESCRIPTION = (
    "Maximize reach and monetization: schedule platform-native publishing, attach "
    "trackable affiliate links, and run first-line community engagement."
)


def build(
    *,
    blackboard: Blackboard,
    vault: Vault,
    constitution: BrandConstitution,
) -> Crew:
    orchestrator = Agent(
        role="Campaign Manager",
        goal="Coordinate the distribution workflow and assemble the campaign plan.",
        backstory="Triggered by a new content package; orchestrates publishing and promotion.",
        artifact_type="distribution_plan",
    )

    tasks = [
        Task(
            description="Schedule platform-native publishing at optimal times across channels.",
            agent=Agent(
                role="Social Media Manager",
                goal="Publish content to social channels at optimal times.",
                backstory="Handles native uploads and data-driven scheduling.",
                artifact_type="publishing_schedule",
            ),
        ),
        Task(
            description="Discover relevant products and generate trackable affiliate links.",
            agent=Agent(
                role="Affiliate Program Manager",
                goal="Monetize content with affiliate links and partner outreach.",
                backstory="Connects to affiliate networks and inserts tracked links.",
                artifact_type="affiliate_plan",
            ),
        ),
        Task(
            description="Draft on-brand first responses for comments and questions.",
            agent=Agent(
                role="Engagement Bot",
                goal="Provide initial, on-brand audience interaction.",
                backstory="Monitors comments and escalates complex inquiries to a human.",
                artifact_type="engagement_plan",
            ),
        ),
    ]

    return Crew(
        name=CrewName.MARKETING_DISTRIBUTION,
        display_name=DISPLAY_NAME,
        orchestrator=orchestrator,
        tasks=tasks,
        blackboard=blackboard,
        event_bus=EventBus(),
        vault=vault,
        constitution=constitution,
        final_artifact_type="distribution_plan",
        final_checkpoint=True,  # HITL: approve the campaign before launch
    )
