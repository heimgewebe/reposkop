from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .observation import observe_checkout
from .schema_validation import validate_artifact
from .timeutil import utc_now

_IDENTITY_FIELDS = (
    ("path", "identity.path_changed"),
    ("git_dir", "identity.git_dir_changed"),
    ("git_common_dir", "identity.git_common_dir_changed"),
    ("remote", "identity.remote_changed"),
    ("purpose", "identity.purpose_changed"),
    ("checkout_identity_sha256", "identity.checkout_changed"),
    ("repository_identity_sha256", "identity.repository_changed"),
)
_STATE_FIELDS = (
    ("head", "continuity.head_changed"),
    ("branch", "continuity.branch_changed"),
    ("detached", "continuity.detached_state_changed"),
    ("upstream", "continuity.upstream_changed"),
    ("dirty", "continuity.dirty_state_changed"),
    ("status_sha256", "continuity.status_changed"),
    ("operation_state", "continuity.operation_state_changed"),
    ("alternates_configured", "continuity.alternates_changed"),
    ("gitmodules_present", "continuity.gitmodules_changed"),
)


def _field_change(before: dict[str, Any], after: dict[str, Any], field: str) -> dict[str, Any]:
    before_value = before.get(field)
    after_value = after.get(field)
    return {
        "before": before_value,
        "after": after_value,
        "changed": before_value != after_value,
    }


def _artifact_is_complete_observation(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("kind") == "reposkop_checkout_observation"
        and value.get("schema_version") == 2
        and value.get("is_git_checkout") is True
        and value.get("observation_complete") is True
        and validate_artifact(value).get("valid") is True
    )


def build_transition(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_validation = validate_artifact(before) if isinstance(before, dict) else {"valid": False}
    after_validation = validate_artifact(after) if isinstance(after, dict) else {"valid": False}
    reason_codes: list[str] = []
    anomaly_codes: list[str] = []

    if not before_validation.get("valid"):
        anomaly_codes.append("evidence.before_invalid")
    if not after_validation.get("valid"):
        anomaly_codes.append("evidence.after_invalid")
    if isinstance(before, dict) and before.get("schema_version") != 2:
        anomaly_codes.append("evidence.before_checkout_identity_missing")
    if isinstance(after, dict) and after.get("schema_version") != 2:
        anomaly_codes.append("evidence.after_checkout_identity_missing")
    if isinstance(before, dict) and before.get("observation_complete") is not True:
        anomaly_codes.append("evidence.before_incomplete")
    if isinstance(after, dict) and after.get("observation_complete") is not True:
        anomaly_codes.append("evidence.after_incomplete")

    before_identities = before.get("identities", {}) if isinstance(before, dict) else {}
    after_identities = after.get("identities", {}) if isinstance(after, dict) else {}
    identity_changes: dict[str, Any] = {}
    for field, code in _IDENTITY_FIELDS:
        change = _field_change(before_identities, after_identities, field)
        identity_changes[field] = change
        if change["changed"]:
            reason_codes.append(code)

    before_role = before.get("role", {}).get("value") if isinstance(before, dict) else None
    after_role = after.get("role", {}).get("value") if isinstance(after, dict) else None
    identity_changes["role"] = {
        "before": before_role,
        "after": after_role,
        "changed": before_role != after_role,
    }
    if before_role != after_role:
        reason_codes.append("identity.role_changed")

    before_git = before.get("git", {}) if isinstance(before, dict) else {}
    after_git = after.get("git", {}) if isinstance(after, dict) else {}
    state_changes: dict[str, Any] = {}
    for field, code in _STATE_FIELDS:
        change = _field_change(before_git, after_git, field)
        state_changes[field] = change
        if change["changed"]:
            reason_codes.append(code)

    before_checkout = before_identities.get("checkout_identity_sha256")
    after_checkout = after_identities.get("checkout_identity_sha256")
    before_repository = before_identities.get("repository_identity_sha256")
    after_repository = after_identities.get("repository_identity_sha256")

    if not _artifact_is_complete_observation(before) or not _artifact_is_complete_observation(after):
        identity_continuity = "inconclusive"
    elif before_checkout == after_checkout:
        identity_continuity = "same_checkout"
    elif before_repository == after_repository:
        identity_continuity = "same_repository_different_checkout"
        anomaly_codes.append("identity.checkout_break")
    else:
        identity_continuity = "different_repository"
        anomaly_codes.extend(("identity.checkout_break", "identity.repository_break"))

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_checkout_transition",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_transition",
            "claim": "canonical",
        },
        "before": before,
        "after": after,
        "before_observation_sha256": before.get("observation_sha256")
        if isinstance(before, dict)
        else None,
        "after_observation_sha256": after.get("observation_sha256")
        if isinstance(after, dict)
        else None,
        "identity_continuity": identity_continuity,
        "identity_changes": identity_changes,
        "state_changes": state_changes,
        "reason_codes": sorted(set(reason_codes)),
        "anomaly_codes": sorted(set(anomaly_codes)),
        "effect_authorized": False,
        "does_not_establish": [
            "task_or_lease_truth",
            "pull_request_truth",
            "remote_freshness",
            "effect_success",
            "effect_authorization",
        ],
    }
    artifact["transition_sha256"] = sha256_json(artifact)
    return artifact


def observe_transition(
    before: dict[str, Any],
    raw_path: str | Path,
    *,
    explicit_role: str | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    after = observe_checkout(raw_path, explicit_role=explicit_role, purpose=purpose)
    return build_transition(before, after)


def build_continuity(transition: dict[str, Any]) -> dict[str, Any]:
    validation = validate_artifact(transition)
    if not validation.get("valid"):
        state = "inconclusive"
        reason_codes = ["evidence.transition_invalid"]
    else:
        identity_continuity = transition.get("identity_continuity")
        state_changed = any(
            value.get("changed") is True
            for value in transition.get("state_changes", {}).values()
            if isinstance(value, dict)
        )
        if identity_continuity == "inconclusive":
            state = "inconclusive"
        elif identity_continuity != "same_checkout":
            state = "identity_break"
        elif state_changed:
            state = "explainable_drift"
        else:
            state = "intact"
        reason_codes = list(transition.get("reason_codes", []))
        reason_codes.extend(transition.get("anomaly_codes", []))

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_checkout_continuity",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_continuity",
            "claim": "canonical",
        },
        "state": state,
        "transition": transition,
        "transition_sha256": transition.get("transition_sha256")
        if isinstance(transition, dict)
        else None,
        "reason_codes": sorted(set(reason_codes)),
        "effect_authorized": False,
        "does_not_establish": [
            "task_or_lease_truth",
            "pull_request_truth",
            "remote_freshness",
            "effect_authorization",
        ],
    }
    artifact["continuity_sha256"] = sha256_json(artifact)
    return artifact


def observe_continuity(
    expected: dict[str, Any],
    raw_path: str | Path,
    *,
    explicit_role: str | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    return build_continuity(
        observe_transition(
            expected,
            raw_path,
            explicit_role=explicit_role,
            purpose=purpose,
        )
    )
