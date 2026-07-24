from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .observation import observe_checkout
from .projection import project_coherence
from .timeutil import utc_now


def build_report(
    raw_path: str | Path,
    *,
    explicit_role: str | None = None,
    purpose: str | None = None,
    lifecycle_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    observation = observe_checkout(raw_path, explicit_role=explicit_role, purpose=purpose)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_coherence_report",
        "generated_at": utc_now(),
        "observation": observation,
        "projection": project_coherence(observation, lifecycle_evidence),
        "authority_boundary": {
            "observer": "reposkop",
            "effect_executor": "grabowski",
            "task_truth": "bureau",
            "pull_request_truth": "github",
            "display": "leitstand",
        },
        "effect_authorized": False,
    }
    report["report_sha256"] = sha256_json(report)
    return report
