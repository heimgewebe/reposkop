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


def test_build_report_emits_scoped_authority_v2(git_repo):
    report = build_report(git_repo, purpose="test")
    assert report["schema_version"] == 2
    assert report["authority_boundary"]["checkout_identity_truth"] == "reposkop"
    assert report["authority_boundary"]["checkout_transition_truth"] == "reposkop"
    assert validate_artifact(report)["valid"] is True


def test_persisted_v1_authority_shape_remains_valid(git_repo):
    report = build_report(git_repo, purpose="test")
    report["schema_version"] = 1
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
