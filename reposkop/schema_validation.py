from __future__ import annotations

import json
from contextvars import ContextVar
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import sha256_json, valid_sha256_or_none
from .shadow_value import derive_shadow_value_claims
from .shadow_value_set import (
    assessment_matches_purpose,
    derive_shadow_value_set_claims,
)
from .timeutil import parse_utc
from .transition_claims import derive_continuity_claims, derive_transition_claims

_SCHEMA_BY_KIND_VERSION = {
    ("reposkop_checkout_observation", 1): "checkout-observation.v1.schema.json",
    ("reposkop_checkout_observation", 2): "checkout-observation.v2.schema.json",
    ("reposkop_checkout_transition", 1): "checkout-transition.v1.schema.json",
    ("reposkop_checkout_continuity", 1): "checkout-continuity.v1.schema.json",
    ("reposkop_shadow_transition", 1): "shadow-transition.v1.schema.json",
    ("reposkop_shadow_value_assessment", 1): "shadow-value-assessment.v1.schema.json",
    ("reposkop_shadow_value_set", 1): "shadow-value-set.v1.schema.json",
    ("reposkop_lifecycle_evidence", 1): "lifecycle-evidence.v1.schema.json",
    ("reposkop_coherence_projection", 1): "coherence-projection.v1.schema.json",
    ("reposkop_coherence_projection", 2): "coherence-projection.v2.schema.json",
    ("reposkop_coherence_report", 1): "coherence-report.v1.schema.json",
    ("reposkop_coherence_report", 2): "coherence-report.v2.schema.json",
    ("reposkop_coherence_report", 3): "coherence-report.v3.schema.json",
    ("reposkop_inventory_config", 1): "inventory-config.v1.schema.json",
    ("reposkop_explicit_inventory", 1): "explicit-inventory.v1.schema.json",
}
_DIGEST_BY_KIND = {
    "reposkop_checkout_observation": "observation_sha256",
    "reposkop_checkout_transition": "transition_sha256",
    "reposkop_checkout_continuity": "continuity_sha256",
    "reposkop_shadow_transition": "shadow_transition_sha256",
    "reposkop_shadow_value_assessment": "assessment_sha256",
    "reposkop_shadow_value_set": "set_sha256",
    "reposkop_coherence_projection": "projection_sha256",
    "reposkop_coherence_report": "report_sha256",
    "reposkop_explicit_inventory": "inventory_sha256",
}

_VALIDATION_CACHE: ContextVar[dict[int, dict[str, Any]] | None] = ContextVar(
    "reposkop_validation_cache", default=None
)


@cache
def _schema(filename: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


@cache
def _validator(filename: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(filename))


def _version(value: dict[str, Any]) -> int | None:
    version = value.get("schema_version")
    return version if type(version) is int else None


def _nested_validation_error(
    rendered_errors: list[Any],
    *,
    path: str,
    value: Any,
    expected_kind: str,
) -> None:
    if not isinstance(value, dict):
        rendered_errors.append({"path": path, "message": "nested artifact is not an object"})
        return
    if value.get("kind") != expected_kind:
        rendered_errors.append({"path": path, "message": f"nested artifact is not {expected_kind}"})
        return
    child = validate_artifact(value)
    if not child["valid"]:
        rendered_errors.append({"path": path, "message": "nested artifact is invalid"})


def _claim_mismatch_errors(
    rendered_errors: list[Any],
    value: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            rendered_errors.append(
                {
                    "path": field,
                    "message": "derived claim does not match embedded source artifacts",
                }
            )


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    validation_cache = _VALIDATION_CACHE.get()
    if validation_cache is not None:
        return _validate_artifact(value, validation_cache)

    validation_cache = {}
    token = _VALIDATION_CACHE.set(validation_cache)
    try:
        return _validate_artifact(value, validation_cache)
    finally:
        _VALIDATION_CACHE.reset(token)


def _validate_artifact(
    value: dict[str, Any], validation_cache: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"valid": False, "kind": None, "schema": None, "errors": ["artifact_not_object"]}
    cache_key = id(value)
    cached = validation_cache.get(cache_key)
    if cached is not None:
        return cached

    kind = value.get("kind")
    version = _version(value)
    filename = _SCHEMA_BY_KIND_VERSION.get((kind, version))
    if filename is None:
        return {
            "valid": False,
            "kind": kind,
            "schema": None,
            "errors": ["unsupported_kind_or_schema_version"],
        }
    errors = sorted(
        _validator(filename).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    rendered_errors: list[Any] = [
        {
            "path": "/".join(str(part) for part in error.absolute_path),
            "message": error.message,
        }
        for error in errors
    ]
    digest_field = _DIGEST_BY_KIND.get(kind)
    if digest_field and isinstance(value.get(digest_field), str):
        unsigned = dict(value)
        expected = unsigned.pop(digest_field)
        actual = sha256_json(unsigned)
        if actual != expected:
            rendered_errors.append(
                {"path": digest_field, "message": "digest does not match canonical artifact"}
            )

    timestamp_fields = {
        "reposkop_checkout_observation": ("observed_at",),
        "reposkop_checkout_transition": ("generated_at",),
        "reposkop_checkout_continuity": ("generated_at",),
        "reposkop_shadow_transition": ("generated_at",),
        "reposkop_shadow_value_assessment": ("generated_at",),
        "reposkop_shadow_value_set": ("generated_at",),
        "reposkop_coherence_report": ("generated_at",),
        "reposkop_explicit_inventory": ("generated_at",),
    }.get(kind, ())
    for field in timestamp_fields:
        try:
            parse_utc(value.get(field))
        except (TypeError, ValueError):
            rendered_errors.append({"path": field, "message": "timestamp is not normalized UTC"})

    if kind == "reposkop_shadow_transition":
        continuity = value.get("continuity")
        _nested_validation_error(
            rendered_errors,
            path="continuity",
            value=continuity,
            expected_kind="reposkop_checkout_continuity",
        )
        transition = continuity.get("transition") if isinstance(continuity, dict) else None
        if (
            isinstance(continuity, dict)
            and value.get("continuity_sha256") != continuity.get("continuity_sha256")
        ):
            rendered_errors.append(
                {
                    "path": "continuity_sha256",
                    "message": "shadow is not bound to embedded continuity",
                }
            )
        if isinstance(transition, dict):
            if value.get("transition_sha256") != transition.get("transition_sha256"):
                rendered_errors.append(
                    {
                        "path": "transition_sha256",
                        "message": "shadow is not bound to embedded transition",
                    }
                )
            before = transition.get("before")
            after = transition.get("after")
            before_validation = (
                validate_artifact(before) if isinstance(before, dict) else {"valid": False}
            )
            after_validation = (
                validate_artifact(after) if isinstance(after, dict) else {"valid": False}
            )
            expected_transition_claims = derive_transition_claims(
                before,
                after,
                before_valid=before_validation.get("valid") is True,
                after_valid=after_validation.get("valid") is True,
            )
            transition_validation = validate_artifact(transition)
            if (
                before_validation.get("valid") is True
                and after_validation.get("valid") is True
                and transition_validation.get("valid") is not True
            ):
                rendered_errors.append(
                    {
                        "path": "continuity/transition",
                        "message": "transition is invalid despite valid embedded observations",
                    }
                )
            expected_continuity_claims = derive_continuity_claims(
                transition,
                transition_valid=transition_validation.get("valid") is True,
            )
            identity_continuity = expected_transition_claims["identity_continuity"]
            expected_local_identity = {
                "same_checkout": "continuous",
                "same_repository_different_checkout": "broken",
                "different_repository": "broken",
                "inconclusive": "could_not_be_established",
            }[identity_continuity]
            before_identities = before.get("identities", {}) if isinstance(before, dict) else {}
            after_identities = after.get("identities", {}) if isinstance(after, dict) else {}
            expected_shadow_claims = {
                "before_observation_sha256": valid_sha256_or_none(
                    before.get("observation_sha256") if isinstance(before, dict) else None
                ),
                "after_observation_sha256": valid_sha256_or_none(
                    after.get("observation_sha256") if isinstance(after, dict) else None
                ),
                "before_repository_identity_sha256": valid_sha256_or_none(
                    before_identities.get("repository_identity_sha256")
                ),
                "after_repository_identity_sha256": valid_sha256_or_none(
                    after_identities.get("repository_identity_sha256")
                ),
                "before_checkout_identity_sha256": valid_sha256_or_none(
                    before_identities.get("checkout_identity_sha256")
                ),
                "after_checkout_identity_sha256": valid_sha256_or_none(
                    after_identities.get("checkout_identity_sha256")
                ),
                "identity_continuity": identity_continuity,
                "continuity_state": expected_continuity_claims["state"],
                "local_identity_continuity": expected_local_identity,
                "reason_codes": expected_continuity_claims["reason_codes"],
                "anomaly_codes": expected_transition_claims["anomaly_codes"],
            }
            _claim_mismatch_errors(rendered_errors, value, expected_shadow_claims)
        else:
            rendered_errors.append(
                {
                    "path": "continuity/transition",
                    "message": "embedded continuity does not contain a transition",
                }
            )

    if kind == "reposkop_shadow_value_assessment":
        shadow = value.get("shadow_transition")
        _nested_validation_error(
            rendered_errors,
            path="shadow_transition",
            value=shadow,
            expected_kind="reposkop_shadow_transition",
        )
        shadow_validation = (
            validate_artifact(shadow) if isinstance(shadow, dict) else {"valid": False}
        )
        if isinstance(shadow, dict):
            expected_claims = derive_shadow_value_claims(
                shadow, shadow_valid=shadow_validation.get("valid") is True
            )
            _claim_mismatch_errors(rendered_errors, value, expected_claims)

    if kind == "reposkop_shadow_value_set":
        assessments = value.get("assessments")
        if isinstance(assessments, list):
            nested_valid = True
            for index, assessment in enumerate(assessments):
                _nested_validation_error(
                    rendered_errors,
                    path=f"assessments/{index}",
                    value=assessment,
                    expected_kind="reposkop_shadow_value_assessment",
                )
                validation = (
                    validate_artifact(assessment)
                    if isinstance(assessment, dict)
                    else {"valid": False}
                )
                nested_valid = nested_valid and validation.get("valid") is True
            if nested_valid:
                purpose = value.get("purpose")
                if isinstance(purpose, str):
                    for index, assessment in enumerate(assessments):
                        if not assessment_matches_purpose(assessment, purpose):
                            rendered_errors.append(
                                {
                                    "path": f"assessments/{index}",
                                    "message": "assessment purpose does not match set purpose",
                                }
                            )
                    expected_claims = derive_shadow_value_set_claims(
                        assessments, purpose=purpose
                    )
                    _claim_mismatch_errors(rendered_errors, value, expected_claims)
                    actual_order = [
                        assessment.get("assessment_sha256")
                        for assessment in assessments
                        if isinstance(assessment, dict)
                    ]
                    if actual_order != expected_claims["assessment_sha256s"]:
                        rendered_errors.append(
                            {
                                "path": "assessments",
                                "message": "assessments are not in canonical digest order",
                            }
                        )
        else:
            rendered_errors.append(
                {"path": "assessments", "message": "assessments is not an array"}
            )

    if kind == "reposkop_coherence_report":
        observation = value.get("observation")
        projection = value.get("projection")
        _nested_validation_error(
            rendered_errors,
            path="observation",
            value=observation,
            expected_kind="reposkop_checkout_observation",
        )
        _nested_validation_error(
            rendered_errors,
            path="projection",
            value=projection,
            expected_kind="reposkop_coherence_projection",
        )
        if isinstance(observation, dict) and isinstance(projection, dict):
            if projection.get("observation_sha256") != observation.get("observation_sha256"):
                rendered_errors.append(
                    {
                        "path": "projection/observation_sha256",
                        "message": "projection is not bound to report observation",
                    }
                )
            actual_observation_validation = validate_artifact(observation)
            if projection.get("observation_validation") != actual_observation_validation:
                rendered_errors.append(
                    {
                        "path": "projection/observation_validation",
                        "message": "embedded observation validation is inconsistent",
                    }
                )

    if kind == "reposkop_explicit_inventory":
        for index, observation in enumerate(value.get("observations", [])):
            if not isinstance(observation, dict) or not validate_artifact(observation)["valid"]:
                rendered_errors.append(
                    {"path": f"observations/{index}", "message": "nested observation is invalid"}
                )

    if kind == "reposkop_checkout_transition":
        before = value.get("before")
        after = value.get("after")
        before_validation = (
            validate_artifact(before) if isinstance(before, dict) else {"valid": False}
        )
        after_validation = (
            validate_artifact(after) if isinstance(after, dict) else {"valid": False}
        )
        _nested_validation_error(
            rendered_errors,
            path="before",
            value=before,
            expected_kind="reposkop_checkout_observation",
        )
        _nested_validation_error(
            rendered_errors,
            path="after",
            value=after,
            expected_kind="reposkop_checkout_observation",
        )
        if (
            isinstance(before, dict)
            and value.get("before_observation_sha256") != before.get("observation_sha256")
        ):
            rendered_errors.append(
                {
                    "path": "before_observation_sha256",
                    "message": "transition is not bound to before observation",
                }
            )
        if (
            isinstance(after, dict)
            and value.get("after_observation_sha256") != after.get("observation_sha256")
        ):
            rendered_errors.append(
                {
                    "path": "after_observation_sha256",
                    "message": "transition is not bound to after observation",
                }
            )
        expected_claims = derive_transition_claims(
            before,
            after,
            before_valid=before_validation.get("valid") is True,
            after_valid=after_validation.get("valid") is True,
        )
        _claim_mismatch_errors(rendered_errors, value, expected_claims)

    if kind == "reposkop_checkout_continuity":
        transition = value.get("transition")
        if not isinstance(transition, dict):
            transition_validation = {
                "valid": False,
                "kind": None,
                "schema": None,
                "errors": ["artifact_not_object"],
            }
            rendered_errors.append(
                {"path": "transition", "message": "nested transition is not an object"}
            )
        elif transition.get("kind") != "reposkop_checkout_transition":
            transition_validation = validate_artifact(transition)
            rendered_errors.append(
                {"path": "transition", "message": "nested artifact is not a transition"}
            )
        else:
            transition_validation = validate_artifact(transition)
            if value.get("transition_sha256") != transition.get("transition_sha256"):
                rendered_errors.append(
                    {
                        "path": "transition_sha256",
                        "message": "continuity is not bound to transition",
                    }
                )
        if value.get("transition_validation") != transition_validation:
            rendered_errors.append(
                {
                    "path": "transition_validation",
                    "message": "embedded transition validation is inconsistent",
                }
            )
        expected_claims = derive_continuity_claims(
            transition,
            transition_valid=transition_validation.get("valid") is True,
        )
        _claim_mismatch_errors(rendered_errors, value, expected_claims)

    result = {
        "valid": not rendered_errors,
        "kind": kind,
        "schema": filename,
        "errors": rendered_errors,
    }
    validation_cache[cache_key] = result
    return result
