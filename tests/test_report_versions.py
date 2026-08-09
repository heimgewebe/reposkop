from __future__ import annotations

from copy import deepcopy

from reposkop.canonical import sha256_json
from reposkop.report import build_report
from reposkop.schema_validation import validate_artifact


def _rehash_report(report):
    report = deepcopy(report)
    report.pop("report_sha256", None)
    report["report_sha256"] = sha256_json(report)
    return report


def _as_legacy_projection(projection):
    projection = deepcopy(projection)
    projection["schema_version"] = 1
    projection["state"] = "inconclusive"
    projection["reasons"] = ["lifecycle_evidence_missing"]
    projection.pop("foreign_authority_gaps")
    projection.pop("projection_sha256", None)
    projection["projection_sha256"] = sha256_json(projection)
    return projection


def test_build_report_emits_scoped_authority_v3(git_repo):
    report = build_report(git_repo, purpose="test")
    assert report["schema_version"] == 3
    assert report["projection"]["schema_version"] == 2
    assert report["authority_boundary"]["checkout_identity_truth"] == "reposkop"
    assert report["authority_boundary"]["checkout_transition_truth"] == "reposkop"
    assert validate_artifact(report)["valid"] is True


def test_persisted_v2_report_and_v1_projection_remain_valid(git_repo):
    report = build_report(git_repo, purpose="test")
    report["schema_version"] = 2
    report["projection"] = _as_legacy_projection(report["projection"])
    report = _rehash_report(report)

    validation = validate_artifact(report)

    assert validation["valid"] is True
    assert validation["schema"] == "coherence-report.v2.schema.json"


def test_persisted_v1_authority_shape_remains_valid(git_repo):
    report = build_report(git_repo, purpose="test")
    report["schema_version"] = 1
    report["projection"] = _as_legacy_projection(report["projection"])
    report["authority_boundary"] = {
        "observer": "reposkop",
        "effect_executor": "grabowski",
        "task_truth": "bureau",
        "pull_request_truth": "github",
        "display": "leitstand",
    }
    report = _rehash_report(report)
    validation = validate_artifact(report)
    assert validation["valid"] is True
    assert validation["schema"] == "coherence-report.v1.schema.json"
