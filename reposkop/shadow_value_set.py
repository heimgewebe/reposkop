from __future__ import annotations

from typing import Any

from .canonical import sha256_json
from .timeutil import utc_now

DIFFERENTIAL_VALUES = (
    "unique_identity_signal",
    "baseline_visible_change",
    "no_identity_break",
    "inconclusive",
)
MAX_ASSESSMENTS = 128
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
    "consumer_outcome_truth",
    "evidence_sufficiency",
    "sampling_representativeness",
    "retention_decision",
)


def _embedded_observations(assessment: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    shadow = assessment.get("shadow_transition")
    continuity = shadow.get("continuity") if isinstance(shadow, dict) else None
    transition = continuity.get("transition") if isinstance(continuity, dict) else None
    if not isinstance(transition, dict):
        return {}, {}
    before = transition.get("before")
    after = transition.get("after")
    return (
        before if isinstance(before, dict) else {},
        after if isinstance(after, dict) else {},
    )


def assessment_matches_purpose(assessment: dict[str, Any], purpose: str) -> bool:
    before, after = _embedded_observations(assessment)
    purposes = []
    for observation in (before, after):
        target = observation.get("target") if isinstance(observation, dict) else None
        purposes.append(target.get("purpose") if isinstance(target, dict) else None)
    return purposes == [purpose, purpose]


def _observation_times(assessment: dict[str, Any]) -> tuple[str, str]:
    before, after = _embedded_observations(assessment)
    return str(before.get("observed_at", "")), str(after.get("observed_at", ""))


def derive_shadow_value_set_claims(
    assessments: list[dict[str, Any]], *, purpose: str
) -> dict[str, Any]:
    ordered = sorted(assessments, key=lambda item: str(item.get("assessment_sha256", "")))
    digests = [str(item.get("assessment_sha256", "")) for item in ordered]
    counts = {value: 0 for value in DIFFERENTIAL_VALUES}
    times: list[str] = []
    for assessment in ordered:
        value = assessment.get("differential_value")
        if value in counts:
            counts[value] += 1
        times.extend(_observation_times(assessment))
    normalized_times = sorted(item for item in times if item)
    return {
        "purpose": purpose,
        "bounds": {
            "max_assessments": MAX_ASSESSMENTS,
            "input_assessments": len(assessments),
            "included_assessments": len(ordered),
            "truncated": False,
        },
        "assessment_sha256s": digests,
        "classification_counts": counts,
        "observation_window": {
            "earliest_observed_at": normalized_times[0] if normalized_times else None,
            "latest_observed_at": normalized_times[-1] if normalized_times else None,
        },
    }


def build_shadow_value_set(
    assessments: list[dict[str, Any]], *, purpose: str
) -> dict[str, Any]:
    from .schema_validation import validate_artifact

    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("shadow-value set purpose must be a non-empty string")
    if not isinstance(assessments, list) or not assessments:
        raise ValueError("shadow-value set requires at least one assessment")
    if len(assessments) > MAX_ASSESSMENTS:
        raise ValueError(f"shadow-value set supports at most {MAX_ASSESSMENTS} assessments")

    normalized_purpose = purpose.strip()
    for index, assessment in enumerate(assessments):
        validation = validate_artifact(assessment) if isinstance(assessment, dict) else {"valid": False}
        if (
            validation.get("valid") is not True
            or not isinstance(assessment, dict)
            or assessment.get("kind") != "reposkop_shadow_value_assessment"
        ):
            raise ValueError(f"assessment {index} is not a valid Reposkop shadow-value artifact")
        if not assessment_matches_purpose(assessment, normalized_purpose):
            raise ValueError(f"assessment {index} is not bound to purpose {normalized_purpose!r}")

    digests = [str(item["assessment_sha256"]) for item in assessments]
    if len(set(digests)) != len(digests):
        raise ValueError("shadow-value set rejects duplicate assessment digests")

    ordered = sorted(assessments, key=lambda item: item["assessment_sha256"])
    claims = derive_shadow_value_set_claims(ordered, purpose=normalized_purpose)
    artifact: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_shadow_value_set",
        "generated_at": utc_now(),
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_identity_differential_set",
            "claim": "canonical",
        },
        **claims,
        "assessments": ordered,
        "does_not_establish": list(DOES_NOT_ESTABLISH),
    }
    artifact["set_sha256"] = sha256_json(artifact)
    return artifact
