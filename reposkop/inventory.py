from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .observation import observe_checkout
from .schema_validation import validate_artifact
from .timeutil import utc_now

_MAX_TARGETS = 200
_MAX_OBSERVATION_WORKERS = 4


def _observe_target(item: dict[str, Any]) -> dict[str, Any]:
    return observe_checkout(
        Path(item["path"]),
        explicit_role=item.get("role"),
        purpose=item.get("purpose"),
    )


def _observe_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(targets) <= 1:
        return [_observe_target(item) for item in targets]
    worker_count = min(_MAX_OBSERVATION_WORKERS, len(targets))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="reposkop-inventory",
    ) as executor:
        return list(executor.map(_observe_target, targets))


def inspect_inventory(config: dict[str, Any]) -> dict[str, Any]:
    validation = validate_artifact(config)
    if not validation["valid"]:
        raise ValueError(f"invalid inventory config: {validation['errors']}")
    targets = config["targets"]
    if len(targets) > _MAX_TARGETS:
        raise ValueError(f"inventory target count exceeds {_MAX_TARGETS}")
    observations = _observe_targets(targets)
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
