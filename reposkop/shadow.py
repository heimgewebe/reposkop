from __future__ import annotations

import re
from typing import Any

from .canonical import sha256_json
from .timeutil import utc_now
from .transition import build_continuity, build_transition

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _identity_digest(observation: Any, field: str) -> str | None:
    if not isinstance(observation, dict):
        return None
    value = observation.get("identities", {}).get(field)
    return value if isinstance(value, str) and _SHA256_RE.fullmatch(value) else None


def _observation_digest(observation: Any) -> str | None:
    if not isinstance(observation, dict):
        return None
    value = observation.get("observation_sha256")
    return value if isinstance(value, str) and _SHA256_RE.fullmatch(value) else None


def build_shadow_transition(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact, operation-agnostic summary of two checkout observations."""
    transition = build_transition(before, after)
    continuity = build_continuity(transition)
    identity_continuity = transition["identity_continuity"]
    if identity_continuity == "same_checkout":
        local_identity_continuity = "continuous"
    elif identity_continuity in {"same_repository_different_checkout", "different_repository"}:
        local_identity_continuity = "broken"
    else:
        local_identity_continuity = "could_not_be_established"

    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_shadow_transition",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_identity_shadow",
            "claim": "canonical",
        },
        "before_observation_sha256": _observation_digest(before),
        "after_observation_sha256": _observation_digest(after),
        "before_repository_identity_sha256": _identity_digest(
            before, "repository_identity_sha256"
        ),
        "after_repository_identity_sha256": _identity_digest(
            after, "repository_identity_sha256"
        ),
        "before_checkout_identity_sha256": _identity_digest(before, "checkout_identity_sha256"),
        "after_checkout_identity_sha256": _identity_digest(after, "checkout_identity_sha256"),
        "transition_sha256": transition["transition_sha256"],
        "continuity_sha256": continuity["continuity_sha256"],
        "identity_continuity": identity_continuity,
        "continuity_state": continuity["state"],
        "local_identity_continuity": local_identity_continuity,
        "reason_codes": continuity["reason_codes"],
        "anomaly_codes": transition["anomaly_codes"],
        "does_not_establish": [
            "operation_intent",
            "operation_allowed",
            "effect_authorization",
            "effect_success",
            "task_or_lease_truth",
            "pull_request_truth",
            "remote_freshness",
        ],
    }
    artifact["shadow_transition_sha256"] = sha256_json(artifact)
    return artifact
