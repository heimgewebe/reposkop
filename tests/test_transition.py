from __future__ import annotations

import subprocess

from reposkop.observation import observe_checkout
from reposkop.schema_validation import validate_artifact
from reposkop.transition import build_continuity, build_transition, observe_continuity


def test_observation_v2_has_canonical_checkout_identity(git_repo):
    result = observe_checkout(git_repo, purpose="test")
    assert result["schema_version"] == 2
    assert result["authority"] == {
        "producer": "reposkop",
        "domain": "local_checkout_identity",
        "claim": "canonical",
    }
    assert len(result["identities"]["checkout_identity_sha256"]) == 64
    assert len(result["identities"]["repository_identity_sha256"]) == 64
    assert len(result["git"]["status_sha256"]) == 64
    assert validate_artifact(result)["valid"] is True


def test_state_drift_preserves_checkout_identity(git_repo):
    before = observe_checkout(git_repo, purpose="test")
    (git_repo / "file.txt").write_text("changed\n", encoding="utf-8")
    after = observe_checkout(git_repo, purpose="test")

    assert (
        before["identities"]["checkout_identity_sha256"]
        == after["identities"]["checkout_identity_sha256"]
    )
    assert before["git"]["status_sha256"] != after["git"]["status_sha256"]

    transition = build_transition(before, after)
    assert transition["identity_continuity"] == "same_checkout"
    assert "continuity.status_changed" in transition["reason_codes"]
    assert transition["anomaly_codes"] == []
    assert validate_artifact(transition)["valid"] is True

    continuity = build_continuity(transition)
    assert continuity["state"] == "explainable_drift"
    assert validate_artifact(continuity)["valid"] is True


def test_unchanged_checkout_is_intact(git_repo):
    before = observe_checkout(git_repo, purpose="resume")
    after = observe_checkout(git_repo, purpose="resume")
    continuity = build_continuity(build_transition(before, after))
    assert continuity["state"] == "intact"
    assert continuity["reason_codes"] == []


def test_linked_worktree_is_same_repository_but_identity_break(git_repo, tmp_path):
    worktree = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(git_repo), "worktree", "add", "-qb", "linked", str(worktree)],
        check=True,
    )
    before = observe_checkout(git_repo, purpose="resume")
    after = observe_checkout(worktree, purpose="resume")
    transition = build_transition(before, after)

    assert transition["identity_continuity"] == "same_repository_different_checkout"
    assert "identity.checkout_break" in transition["anomaly_codes"]
    assert build_continuity(transition)["state"] == "identity_break"


def test_purpose_change_breaks_checkout_binding(git_repo):
    before = observe_checkout(git_repo, purpose="review")
    continuity = observe_continuity(before, git_repo, purpose="deploy")
    assert continuity["state"] == "identity_break"
    assert "identity.purpose_changed" in continuity["reason_codes"]
