from __future__ import annotations

from typing import Any

from .canonical import sha256_json, valid_sha256_or_none
from .timeutil import utc_now

BASELINE_FIELDS = ("path", "branch", "head", "git_common_dir")
DOES_NOT_ESTABLISH = (
    "materiality",
    "recovery_improvement",
    "wrong_checkout_prevention",
    "operation_intent",
    "operation_allowed",
    "effect_authorization",
    "task_or_lease_truth",
    "pull_request_truth",
    "remote_freshness",
)


def _embedded_observations(shadow: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    continuity = shadow.get("continuity")
    transition = continuity.get("transition") if isinstance(continuity, dict) else None
    if not isinstance(transition, dict):
        return {}, {}
    before = transition.get("before")
    after = transition.get("after")
    return (
        before if isinstance(before, dict) else {},
        after if isinstance(after, dict) else {},
    )


def _baseline_value(observation: dict[str, Any], field: str) -> Any:
    if field in {"path", "git_common_dir"}:
        identities = observation.get("identities")
        return identities.get(field) if isinstance(identities, dict) else None
    git = observation.get("git")
    return git.get(field) if isinstance(git, dict) else None


def derive_shadow_value_claims(
    shadow: dict[str, Any], *, shadow_valid: bool
) -> dict[str, Any]:
    if shadow_valid:
        before, after = _embedded_observations(shadow)
        changed_fields = [
            field
            for field in BASELINE_FIELDS
            if _baseline_value(before, field) != _baseline_value(after, field)
        ]
        identity_continuity = shadow.get("identity_continuity")
        local_identity_continuity = shadow.get("local_identity_continuity")
    else:
        changed_fields = []
        identity_continuity = "inconclusive"
        local_identity_continuity = "could_not_be_established"

    if local_identity_continuity == "broken":
        differential_value = (
            "unique_identity_signal" if not changed_fields else "baseline_visible_change"
        )
    elif local_identity_continuity == "continuous":
        differential_value = "no_identity_break"
    else:
        differential_value = "inconclusive"

    return {
        "shadow_transition_sha256": valid_sha256_or_none(
            shadow.get("shadow_transition_sha256")
        ),
        "baseline_fields": list(BASELINE_FIELDS),
        "baseline_changed_fields": changed_fields,
        "identity_continuity": identity_continuity,
        "local_identity_continuity": local_identity_continuity,
        "differential_value": differential_value,
    }


def build_shadow_value_assessment(shadow: dict[str, Any]) -> dict[str, Any]:
    from .schema_validation import validate_artifact

    shadow_validation = validate_artifact(shadow)
    if shadow_validation.get("valid") is not True or shadow.get("kind") != "reposkop_shadow_transition":
        raise ValueError("shadow transition is not a valid Reposkop shadow artifact")

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_shadow_value_assessment",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_identity_differential",
            "claim": "canonical",
        },
        "shadow_transition": shadow,
        **derive_shadow_value_claims(shadow, shadow_valid=True),
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    artifact["assessment_sha256"] = sha256_json(artifact)
    return artifact
