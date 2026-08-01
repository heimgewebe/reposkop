from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import sha256_json
from .timeutil import parse_utc

_SCHEMA_BY_KIND_VERSION = {
    ("reposkop_checkout_observation", 1): "checkout-observation.v1.schema.json",
    ("reposkop_checkout_observation", 2): "checkout-observation.v2.schema.json",
    ("reposkop_checkout_transition", 1): "checkout-transition.v1.schema.json",
    ("reposkop_checkout_continuity", 1): "checkout-continuity.v1.schema.json",
    ("reposkop_lifecycle_evidence", 1): "lifecycle-evidence.v1.schema.json",
    ("reposkop_coherence_projection", 1): "coherence-projection.v1.schema.json",
    ("reposkop_coherence_report", 1): "coherence-report.v1.schema.json",
    ("reposkop_inventory_config", 1): "inventory-config.v1.schema.json",
    ("reposkop_explicit_inventory", 1): "explicit-inventory.v1.schema.json",
}
_DIGEST_BY_KIND = {
    "reposkop_checkout_observation": "observation_sha256",
    "reposkop_checkout_transition": "transition_sha256",
    "reposkop_checkout_continuity": "continuity_sha256",
    "reposkop_coherence_projection": "projection_sha256",
    "reposkop_coherence_report": "report_sha256",
    "reposkop_explicit_inventory": "inventory_sha256",
}


@cache
def _schema(filename: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


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


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"valid": False, "kind": None, "schema": None, "errors": ["artifact_not_object"]}
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
        Draft202012Validator(_schema(filename)).iter_errors(value),
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
        "reposkop_coherence_report": ("generated_at",),
        "reposkop_explicit_inventory": ("generated_at",),
    }.get(kind, ())
    for field in timestamp_fields:
        try:
            parse_utc(value.get(field))
        except (TypeError, ValueError):
            rendered_errors.append({"path": field, "message": "timestamp is not normalized UTC"})

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

    if kind == "reposkop_checkout_continuity":
        transition = value.get("transition")
        if not isinstance(transition, dict):
            rendered_errors.append(
                {"path": "transition", "message": "nested transition is not an object"}
            )
        elif transition.get("kind") != "reposkop_checkout_transition":
            rendered_errors.append(
                {"path": "transition", "message": "nested artifact is not a transition"}
            )
        else:
            actual_transition_validation = validate_artifact(transition)
            if value.get("transition_validation") != actual_transition_validation:
                rendered_errors.append(
                    {
                        "path": "transition_validation",
                        "message": "embedded transition validation is inconsistent",
                    }
                )
            if value.get("transition_sha256") != transition.get("transition_sha256"):
                rendered_errors.append(
                    {
                        "path": "transition_sha256",
                        "message": "continuity is not bound to transition",
                    }
                )

    return {
        "valid": not rendered_errors,
        "kind": kind,
        "schema": filename,
        "errors": rendered_errors,
    }
