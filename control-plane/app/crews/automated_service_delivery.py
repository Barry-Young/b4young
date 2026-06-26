"""The 'Automated Service Delivery' crew (docs/03-agent-crews.md, 3.4).

Product Manager (orchestrator) coordinating the Webinar Host and Personalized
Coaching Bot to stand up evergreen, scalable revenue streams. The final service
plan is gated by HITL before going live.
"""

from __future__ import annotations

from ..constitution import BrandConstitution
from ..models import CrewName
from ..vault import Vault
from .base import Agent, Crew, Task
from .blackboard import Blackboard, EventBus

DISPLAY_NAME = "Automated Service Delivery"
DESCRIPTION = (
    "Deliver high-value digital services 24/7: evergreen webinar funnels and a "
    "personalized, conversational coaching experience."
)


def build(
    *,
    blackboard: Blackboard,
    vault: Vault,
    constitution: BrandConstitution,
) -> Crew:
    orchestrator = Agent(
        role="Product Manager",
        goal="Oversee automated services and assemble the service delivery plan.",
        backstory="Manages scheduling and performance of evergreen services.",
        artifact_type="service_plan",
    )

    tasks = [
        Task(
            description="Build an evergreen webinar funnel with just-in-time scheduling.",
            agent=Agent(
                role="Webinar Host",
                goal="Deliver evergreen webinars with simulated live engagement.",
                backstory="Creates registration funnels and timed engagement.",
                artifact_type="webinar_funnel",
            ),
        ),
        Task(
            description="Design a personalized coaching flow with a tailored action plan.",
            agent=Agent(
                role="Personalized Coaching Bot",
                goal="Provide scalable, tailored coaching and track progress.",
                backstory="Draws on the brand knowledge base to coach interactively.",
                artifact_type="coaching_plan",
            ),
        ),
    ]

    return Crew(
        name=CrewName.AUTOMATED_SERVICE_DELIVERY,
        display_name=DISPLAY_NAME,
        orchestrator=orchestrator,
        tasks=tasks,
        blackboard=blackboard,
        event_bus=EventBus(),
        vault=vault,
        constitution=constitution,
        final_artifact_type="service_plan",
        final_checkpoint=True,  # HITL: approve before the service goes live
    )
