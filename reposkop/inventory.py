from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .observation import observe_checkout
from .schema_validation import validate_artifact
from .timeutil import utc_now

_MAX_TARGETS = 200


def inspect_inventory(config: dict[str, Any]) -> dict[str, Any]:
    validation = validate_artifact(config)
    if not validation["valid"]:
        raise ValueError(f"invalid inventory config: {validation['errors']}")
    targets = config["targets"]
    if len(targets) > _MAX_TARGETS:
        raise ValueError(f"inventory target count exceeds {_MAX_TARGETS}")
    observations = [
        observe_checkout(
            Path(item["path"]),
            explicit_role=item.get("role"),
            purpose=item.get("purpose"),
        )
        for item in targets
    ]
    result: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_explicit_inventory",
        "generated_at": utc_now(),
        "target_count": len(observations),
        "discovery_performed": False,
        "observations": observations,
        "does_not_establish": [
            "absence_of_unlisted_repositories",
            "global_host_inventory",
            "cleanup_or_mutation_authority",
        ],
    }
    result["inventory_sha256"] = sha256_json(result)
    return result
