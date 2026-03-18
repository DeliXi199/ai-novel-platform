from __future__ import annotations

"""Prompt template facade split by domain-specific modules."""

from app.services.prompt_templates_shared import *
from app.services.prompt_templates_bootstrap import *
from app.services.prompt_templates_selection import *
from app.services.prompt_templates_drafting import *
from app.services.prompt_templates_summary import *

# Re-export selected internal helpers that are imported by tests and a few support modules.
from app.services.prompt_templates_bootstrap import _planning_payoff_compensation_prompt_payload
from app.services.prompt_templates_drafting import (
    _chapter_body_plan_packet_summary,
    _chapter_body_plan_summary,
)

__all__ = [name for name in globals() if not name.startswith('__')]
