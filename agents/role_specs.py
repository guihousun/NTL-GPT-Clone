"""Authoritative runtime metadata for the four NTL-GPT roles.

The role names and skill namespaces in this module are part of the experiment
snapshot.  Tool objects remain in :mod:`tools`; keeping this metadata import
light lets graph construction and tests inspect boundaries without importing
optional geospatial dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass


COMMON_SKILL_SOURCE = "/skills/common/"
GEE_NTL_DATE_BOUNDARY_SKILL_SOURCE = "/skills/gee-ntl-date-boundary-handling/"


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """Stable description of one role's orchestration boundary."""

    name: str
    description: str
    tool_group: str
    skill_sources: tuple[str, ...]
    expected_package_type: str
    can_delegate: bool = False


def _role_skills(namespace: str, *shared_sources: str) -> tuple[str, ...]:
    """Build an ordered role Skill surface with optional shared procedures."""
    return (COMMON_SKILL_SOURCE, f"/skills/{namespace}/", *shared_sources)


ROLE_SPECS: dict[str, RoleSpec] = {
    "NTL_Engineer": RoleSpec(
        name="NTL_Engineer",
        description=(
            "Supervisor and task-truth owner. Plans and conditionally routes work, "
            "can execute bounded routine local code when inputs and semantics are "
            "settled, routes task-specific NTL science to the appropriate specialist, "
            "accepts typed specialist packages, and synthesizes the final EvidenceReport."
        ),
        tool_group="engineer_tools",
        skill_sources=_role_skills("engineer", GEE_NTL_DATE_BOUNDARY_SKILL_SOURCE),
        expected_package_type="EvidenceReport",
        can_delegate=True,
    ),
    "NTL_Data_Searcher": RoleSpec(
        name="NTL_Data_Searcher",
        description=(
            "Observation specialist for product availability, AOI and date resolution, "
            "acquisition, standard preprocessing, provenance, and analysis-ready "
            "ObservationPackage production when a typed handoff is requested; it may "
            "return a bounded evidence summary for summary-only assignments."
        ),
        tool_group="data_searcher_tools",
        skill_sources=_role_skills("data_searcher", GEE_NTL_DATE_BOUNDARY_SKILL_SOURCE),
        expected_package_type="ObservationPackage",
    ),
    "NTL_Analyst": RoleSpec(
        name="NTL_Analyst",
        description=(
            "Scientific-analysis specialist for task-specific nighttime-light methods, "
            "contract-bound code execution, artifacts, bounded technical repair, "
            "internal validation, and AnalysisPackage production when a typed handoff "
            "is requested; it may return a bounded summary-only result otherwise."
        ),
        tool_group="analyst_tools",
        skill_sources=_role_skills("analyst"),
        expected_package_type="AnalysisPackage",
    ),
    "NTL_Event_Tracker": RoleSpec(
        name="NTL_Event_Tracker",
        description=(
            "Source-bounded event-context specialist for requested disaster, conflict, "
            "outage, accident, and recovery tasks; preserves time, provenance, source "
            "conflicts, coverage limits, and produces an EventContext when a typed "
            "handoff is requested; it may return a bounded source summary otherwise."
        ),
        tool_group="event_tracker_tools",
        skill_sources=_role_skills("event_tracker"),
        expected_package_type="EventContext",
    ),
}


ROLE_SKILL_SOURCES: dict[str, tuple[str, ...]] = {
    name: spec.skill_sources for name, spec in ROLE_SPECS.items()
}


_ROLE_ALIASES = {
    "engineer": "NTL_Engineer",
    "ntl_engineer": "NTL_Engineer",
    "data_searcher": "NTL_Data_Searcher",
    "ntl_data_searcher": "NTL_Data_Searcher",
    "analyst": "NTL_Analyst",
    "ntl_analyst": "NTL_Analyst",
    "event_tracker": "NTL_Event_Tracker",
    "ntl_event_tracker": "NTL_Event_Tracker",
}


def get_role_spec(role: str) -> RoleSpec:
    """Resolve a canonical role name or a conservative lowercase alias."""

    raw = str(role or "").strip()
    if raw in ROLE_SPECS:
        return ROLE_SPECS[raw]
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    canonical = _ROLE_ALIASES.get(normalized)
    if canonical is None:
        raise KeyError(f"Unknown NTL-GPT role: {role!r}")
    return ROLE_SPECS[canonical]


SPECIALIST_ROLE_NAMES = (
    "NTL_Data_Searcher",
    "NTL_Analyst",
    "NTL_Event_Tracker",
)


__all__ = [
    "COMMON_SKILL_SOURCE",
    "GEE_NTL_DATE_BOUNDARY_SKILL_SOURCE",
    "ROLE_SKILL_SOURCES",
    "ROLE_SPECS",
    "SPECIALIST_ROLE_NAMES",
    "RoleSpec",
    "get_role_spec",
]
