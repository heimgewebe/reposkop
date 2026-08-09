from __future__ import annotations

from typing import Any

from .canonical import sha256_json
from .evidence import subject_matches, validate_lifecycle_evidence
from .model import MANAGED_ROLES, ProjectionState
from .schema_validation import validate_artifact

_TERMINAL_TASK_STATES = {
    "succeeded",
    "failed",
    "canceled",
    "cancelled",
    "verified",
    "closed",
    "archived",
    "terminal",
}


def _active_bindings(evidence: dict[str, Any]) -> list[str]:
    bindings = evidence.get("bindings", {})
    active: list[str] = []
    for item in bindings.get("tasks", []):
        if isinstance(item, dict) and str(item.get("state", "")).lower() not in _TERMINAL_TASK_STATES:
            active.append(f"task:{item.get('id', 'unknown')}")
    for item in bindings.get("leases", []):
        if isinstance(item, dict) and item.get("active") is True:
            active.append(f"lease:{item.get('resource_key', 'unknown')}")
    for item in bindings.get("processes", []):
        if isinstance(item, dict) and item.get("active") is True:
            active.append(f"process:{item.get('pid', 'unknown')}")
    for item in bindings.get("tmux", []):
        if isinstance(item, dict) and item.get("active") is True:
            active.append(f"tmux:{item.get('session', 'unknown')}")
    for item in bindings.get("pull_requests", []):
        if isinstance(item, dict) and str(item.get("state", "")).upper() in {"OPEN", "DRAFT"}:
            active.append(f"pull_request:{item.get('id', 'unknown')}")
    return active


def project_coherence(
    observation: dict[str, Any],
    lifecycle_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    foreign_authority_gaps: list[str] = []
    role = observation.get("role", {}).get("value", "unknown")
    dirty = observation.get("git", {}).get("dirty") is True
    observation_complete = observation.get("observation_complete") is True
    observation_validation = validate_artifact(observation)
    state = ProjectionState.INCONCLUSIVE.value
    evidence_validation: dict[str, Any] | None = None
    active_bindings: list[str] = []

    if lifecycle_evidence is not None:
        evidence_validation = validate_lifecycle_evidence(lifecycle_evidence)
        if evidence_validation["valid"]:
            evidence_matches, mismatches = subject_matches(observation, lifecycle_evidence)
            if evidence_matches:
                active_bindings = _active_bindings(lifecycle_evidence)
                if evidence_validation["freshness"] != "fresh":
                    foreign_authority_gaps.append("lifecycle_evidence_stale")
            else:
                foreign_authority_gaps.extend(
                    f"lifecycle_subject_mismatch:{value}" for value in mismatches
                )
        else:
            foreign_authority_gaps.append("lifecycle_evidence_invalid")
    else:
        foreign_authority_gaps.append("lifecycle_evidence_missing")

    if not observation_validation["valid"]:
        reasons.append("observation_invalid")
    elif not observation.get("is_git_checkout") or not observation_complete:
        reasons.append("git_observation_incomplete")
    else:
        state = ProjectionState.LOCAL_COHERENT.value
        reasons.append("local_checkout_observation_complete")
        if role in MANAGED_ROLES:
            reasons.append(f"managed_role:{role}")
        if dirty:
            reasons.append("git_dirty")

    projection: dict[str, Any] = {
        "schema_version": 2,
        "kind": "reposkop_coherence_projection",
        "state": state,
        "reasons": list(dict.fromkeys(reasons)),
        "active_bindings": active_bindings,
        "foreign_authority_gaps": list(dict.fromkeys(foreign_authority_gaps)),
        "observation_sha256": observation.get("observation_sha256"),
        "observation_validation": observation_validation,
        "evidence_validation": evidence_validation,
        "effect_authorized": False,
        "does_not_establish": [
            "deletion_authority",
            "archive_authority",
            "task_or_queue_truth",
            "current_process_or_lease_absence_beyond_supplied_evidence",
            "remote_or_pull_request_freshness_beyond_supplied_evidence",
        ],
    }
    projection["projection_sha256"] = sha256_json(projection)
    return projection
