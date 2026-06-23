"""Data Plane crews and the crew registry.

The registry lets the Control Plane discover and deploy crews by key. Add new
crews (Content Factory, Marketing & Distribution, Automated Service Delivery) by
implementing a builder module and registering it here.
"""

from __future__ import annotations

from ..constitution import BrandConstitution
from ..models import CrewInfo, CrewName
from ..vault import Vault
from . import market_intelligence
from .base import Crew
from .blackboard import Blackboard

# key -> (display_name, description, builder)
_REGISTRY = {
    CrewName.MARKET_INTELLIGENCE: (
        market_intelligence.DISPLAY_NAME,
        market_intelligence.DESCRIPTION,
        market_intelligence.build,
    ),
}


def list_crews() -> list[CrewInfo]:
    return [
        CrewInfo(key=key, display_name=name, description=desc)
        for key, (name, desc, _builder) in _REGISTRY.items()
    ]


def is_registered(key: CrewName) -> bool:
    return key in _REGISTRY


def build_crew(
    key: CrewName,
    *,
    blackboard: Blackboard,
    vault: Vault,
    constitution: BrandConstitution,
) -> Crew:
    if key not in _REGISTRY:
        raise KeyError(f"unknown crew: {key}")
    _name, _desc, builder = _REGISTRY[key]
    return builder(blackboard=blackboard, vault=vault, constitution=constitution)
