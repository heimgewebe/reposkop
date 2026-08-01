from __future__ import annotations

from typing import Any

IDENTITY_FIELDS = (
    ("path", "identity.path_changed"),
    ("git_dir", "identity.git_dir_changed"),
    ("git_common_dir", "identity.git_common_dir_changed"),
    ("remote", "identity.remote_changed"),
    ("purpose", "identity.purpose_changed"),
    ("checkout_identity_sha256", "identity.checkout_changed"),
    ("repository_identity_sha256", "identity.repository_changed"),
)
STATE_FIELDS = (
    ("head", "continuity.head_changed"),
    ("branch", "continuity.branch_changed"),
    ("detached", "continuity.detached_state_changed"),
    ("upstream", "continuity.upstream_changed"),
    ("ahead", "continuity.ahead_changed"),
    ("behind", "continuity.behind_changed"),
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


def derive_transition_claims(
    before: Any,
    after: Any,
    *,
    before_valid: bool,
    after_valid: bool,
) -> dict[str, Any]:
    reason_codes: list[str] = []
    anomaly_codes: list[str] = []

    if not before_valid:
        anomaly_codes.append("evidence.before_invalid")
    if not after_valid:
        anomaly_codes.append("evidence.after_invalid")
    if isinstance(before, dict) and before.get("schema_version") != 2:
        anomaly_codes.append("evidence.before_checkout_identity_missing")
    if isinstance(after, dict) and after.get("schema_version") != 2:
        anomaly_codes.append("evidence.after_checkout_identity_missing")
    if not isinstance(before, dict) or before.get("observation_complete") is not True:
        anomaly_codes.append("evidence.before_incomplete")
    if not isinstance(after, dict) or after.get("observation_complete") is not True:
        anomaly_codes.append("evidence.after_incomplete")

    before_identities = before.get("identities", {}) if isinstance(before, dict) else {}
    after_identities = after.get("identities", {}) if isinstance(after, dict) else {}
    identity_changes: dict[str, Any] = {}
    for field, code in IDENTITY_FIELDS:
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
    for field, code in STATE_FIELDS:
        change = _field_change(before_git, after_git, field)
        state_changes[field] = change
        if change["changed"]:
            reason_codes.append(code)

    before_checkout = before_identities.get("checkout_identity_sha256")
    after_checkout = after_identities.get("checkout_identity_sha256")
    before_repository = before_identities.get("repository_identity_sha256")
    after_repository = after_identities.get("repository_identity_sha256")
    complete = bool(
        before_valid
        and after_valid
        and isinstance(before, dict)
        and isinstance(after, dict)
        and before.get("schema_version") == 2
        and after.get("schema_version") == 2
        and before.get("is_git_checkout") is True
        and after.get("is_git_checkout") is True
        and before.get("observation_complete") is True
        and after.get("observation_complete") is True
    )

    if not complete:
        identity_continuity = "inconclusive"
    elif before_checkout == after_checkout:
        identity_continuity = "same_checkout"
    elif before_repository == after_repository:
        identity_continuity = "same_repository_different_checkout"
        anomaly_codes.append("identity.checkout_break")
    else:
        identity_continuity = "different_repository"
        anomaly_codes.extend(("identity.checkout_break", "identity.repository_break"))

    return {
        "identity_continuity": identity_continuity,
        "identity_changes": identity_changes,
        "state_changes": state_changes,
        "reason_codes": sorted(set(reason_codes)),
        "anomaly_codes": sorted(set(anomaly_codes)),
    }


def derive_continuity_claims(
    transition: Any,
    *,
    transition_valid: bool,
) -> dict[str, Any]:
    if not transition_valid or not isinstance(transition, dict):
        return {
            "state": "inconclusive",
            "reason_codes": ["evidence.transition_invalid"],
        }

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
    return {
        "state": state,
        "reason_codes": sorted(set(reason_codes)),
    }
