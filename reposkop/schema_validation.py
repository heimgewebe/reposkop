from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .canonical import sha256_json
from .timeutil import parse_utc

_SCHEMA_BY_KIND = {
    "reposkop_checkout_observation": "checkout-observation.v1.schema.json",
    "reposkop_lifecycle_evidence": "lifecycle-evidence.v1.schema.json",
    "reposkop_coherence_projection": "coherence-projection.v1.schema.json",
    "reposkop_coherence_report": "coherence-report.v1.schema.json",
    "reposkop_inventory_config": "inventory-config.v1.schema.json",
    "reposkop_explicit_inventory": "explicit-inventory.v1.schema.json",
}
_DIGEST_BY_KIND = {
    "reposkop_checkout_observation": "observation_sha256",
    "reposkop_coherence_projection": "projection_sha256",
    "reposkop_coherence_report": "report_sha256",
    "reposkop_explicit_inventory": "inventory_sha256",
}


@lru_cache(maxsize=None)
def _schema(filename: str) -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "schemas" / filename
    value = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def validate_artifact(value: dict[str, Any]) -> dict[str, Any]:
    kind = value.get("kind")
    filename = _SCHEMA_BY_KIND.get(kind)
    if filename is None:
        return {"valid": False, "kind": kind, "errors": ["unsupported_kind"]}
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
        if isinstance(observation, dict):
            child = validate_artifact(observation)
            if not child["valid"]:
                rendered_errors.append({"path": "observation", "message": "nested observation is invalid"})
        if isinstance(projection, dict):
            child = validate_artifact(projection)
            if not child["valid"]:
                rendered_errors.append({"path": "projection", "message": "nested projection is invalid"})
        if isinstance(observation, dict) and isinstance(projection, dict):
            if projection.get("observation_sha256") != observation.get("observation_sha256"):
                rendered_errors.append(
                    {"path": "projection/observation_sha256", "message": "projection is not bound to report observation"}
                )
            actual_observation_validation = validate_artifact(observation)
            if projection.get("observation_validation") != actual_observation_validation:
                rendered_errors.append(
                    {"path": "projection/observation_validation", "message": "embedded observation validation is inconsistent"}
                )

    if kind == "reposkop_explicit_inventory":
        for index, observation in enumerate(value.get("observations", [])):
            if not isinstance(observation, dict) or not validate_artifact(observation)["valid"]:
                rendered_errors.append(
                    {"path": f"observations/{index}", "message": "nested observation is invalid"}
                )
    return {
        "valid": not rendered_errors,
        "kind": kind,
        "schema": filename,
        "errors": rendered_errors,
    }
