from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from reposkop.canonical import sha256_json
from reposkop.observation import observe_checkout
from reposkop.schema_validation import validate_artifact
from reposkop.shadow import build_shadow_transition
from reposkop.shadow_value import build_shadow_value_assessment
from reposkop.shadow_value_set import MAX_ASSESSMENTS, build_shadow_value_set


def _git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _seed(path: Path, *, purpose: str, remote: str | None = None) -> tuple[Path, dict]:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "shadow-set@example.invalid")
    _git(path, "config", "user.name", "Reposkop Shadow Set")
    (path / "file.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", "file.txt")
    _git(path, "commit", "-qm", "initial")
    if remote is not None:
        _git(path, "remote", "add", "origin", remote)
    return path, observe_checkout(path, purpose=purpose)


def _assessment(before: dict, after: dict) -> dict:
    shadow = build_shadow_transition(before, after)
    assessment = build_shadow_value_assessment(shadow)
    assert validate_artifact(assessment)["valid"] is True
    return assessment


def test_set_aggregates_canonical_order_counts_and_window(tmp_path: Path) -> None:
    purpose = "real-consumer-shadow"
    stable_repo, stable_before = _seed(tmp_path / "stable", purpose=purpose)
    stable = _assessment(stable_before, observe_checkout(stable_repo, purpose=purpose))

    changed_repo, changed_before = _seed(
        tmp_path / "changed",
        purpose=purpose,
        remote="git@host-a.invalid:owner/repo.git",
    )
    _git(changed_repo, "remote", "set-url", "origin", "git@host-b.invalid:owner/repo.git")
    changed = _assessment(changed_before, observe_checkout(changed_repo, purpose=purpose))
    assert changed["differential_value"] == "unique_identity_signal"

    value_set = build_shadow_value_set([stable, changed], purpose=purpose)

    assert value_set["assessment_sha256s"] == sorted(
        [stable["assessment_sha256"], changed["assessment_sha256"]]
    )
    assert [item["assessment_sha256"] for item in value_set["assessments"]] == value_set[
        "assessment_sha256s"
    ]
    assert value_set["classification_counts"] == {
        "unique_identity_signal": 1,
        "baseline_visible_change": 0,
        "no_identity_break": 1,
        "inconclusive": 0,
    }
    assert value_set["bounds"] == {
        "max_assessments": MAX_ASSESSMENTS,
        "input_assessments": 2,
        "included_assessments": 2,
        "truncated": False,
    }
    assert validate_artifact(value_set)["valid"] is True


def test_set_rejects_mixed_purpose(tmp_path: Path) -> None:
    repo, before = _seed(tmp_path / "repo", purpose="purpose-a")
    assessment = _assessment(before, observe_checkout(repo, purpose="purpose-a"))

    with pytest.raises(ValueError, match="not bound to purpose"):
        build_shadow_value_set([assessment], purpose="purpose-b")


def test_set_rejects_duplicate_assessments(tmp_path: Path) -> None:
    repo, before = _seed(tmp_path / "repo", purpose="duplicate-test")
    assessment = _assessment(before, observe_checkout(repo, purpose="duplicate-test"))

    with pytest.raises(ValueError, match="duplicate assessment digests"):
        build_shadow_value_set([assessment, assessment], purpose="duplicate-test")


def test_set_rejects_more_than_hard_bound(tmp_path: Path) -> None:
    repo, before = _seed(tmp_path / "repo", purpose="bounded-test")
    assessment = _assessment(before, observe_checkout(repo, purpose="bounded-test"))

    with pytest.raises(ValueError, match=f"at most {MAX_ASSESSMENTS}"):
        build_shadow_value_set([assessment] * (MAX_ASSESSMENTS + 1), purpose="bounded-test")


def test_validator_recomputes_counts_even_if_outer_digest_is_recomputed(tmp_path: Path) -> None:
    repo, before = _seed(tmp_path / "repo", purpose="tamper-test")
    assessment = _assessment(before, observe_checkout(repo, purpose="tamper-test"))
    value_set = build_shadow_value_set([assessment], purpose="tamper-test")

    value_set["classification_counts"]["unique_identity_signal"] = 1
    value_set["classification_counts"]["no_identity_break"] = 0
    unsigned = dict(value_set)
    unsigned.pop("set_sha256")
    value_set["set_sha256"] = sha256_json(unsigned)

    validation = validate_artifact(value_set)
    assert validation["valid"] is False
    assert any(
        error.get("path") == "classification_counts"
        and "derived claim" in error.get("message", "")
        for error in validation["errors"]
        if isinstance(error, dict)
    )
