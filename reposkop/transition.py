from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .observation import observe_checkout
from .schema_validation import validate_artifact
from .timeutil import utc_now
from .transition_claims import derive_continuity_claims, derive_transition_claims


def build_transition(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_validation = validate_artifact(before) if isinstance(before, dict) else {"valid": False}
    after_validation = validate_artifact(after) if isinstance(after, dict) else {"valid": False}
    claims = derive_transition_claims(
        before,
        after,
        before_valid=before_validation.get("valid") is True,
        after_valid=after_validation.get("valid") is True,
    )
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
        **claims,
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
    claims = derive_continuity_claims(
        transition,
        transition_valid=validation.get("valid") is True,
    )
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_checkout_continuity",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_continuity",
            "claim": "canonical",
        },
        **claims,
        "transition": transition,
        "transition_sha256": transition.get("transition_sha256")
        if isinstance(transition, dict)
        else None,
        "transition_validation": validation,
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
