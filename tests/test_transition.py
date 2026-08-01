from __future__ import annotations

import subprocess
from copy import deepcopy

from reposkop.canonical import sha256_json
from reposkop.observation import observe_checkout
from reposkop.schema_validation import validate_artifact
from reposkop.transition import build_continuity, build_transition, observe_continuity


def _rehash(artifact, digest_field):
    artifact = deepcopy(artifact)
    artifact.pop(digest_field, None)
    artifact[digest_field] = sha256_json(artifact)
    return artifact


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
    assert continuity["transition_validation"]["valid"] is True
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


def test_invalid_transition_yields_valid_inconclusive_continuity(git_repo):
    observation = observe_checkout(git_repo, purpose="resume")
    transition = build_transition(observation, observation)
    transition["transition_sha256"] = "0" * 64

    continuity = build_continuity(transition)
    assert continuity["state"] == "inconclusive"
    assert continuity["transition_validation"]["valid"] is False
    assert "evidence.transition_invalid" in continuity["reason_codes"]
    assert validate_artifact(continuity)["valid"] is True


def test_forged_transition_claim_is_rejected_after_rehash(git_repo, tmp_path):
    worktree = tmp_path / "linked-forgery"
    subprocess.run(
        ["git", "-C", str(git_repo), "worktree", "add", "-qb", "forgery", str(worktree)],
        check=True,
    )
    transition = build_transition(
        observe_checkout(git_repo, purpose="resume"),
        observe_checkout(worktree, purpose="resume"),
    )
    transition["identity_continuity"] = "same_checkout"
    transition = _rehash(transition, "transition_sha256")

    validation = validate_artifact(transition)
    assert validation["valid"] is False
    assert any(error.get("path") == "identity_continuity" for error in validation["errors"])
    assert build_continuity(transition)["state"] == "inconclusive"


def test_forged_continuity_claim_is_rejected_after_rehash(git_repo):
    observation = observe_checkout(git_repo, purpose="resume")
    transition = build_transition(observation, observation)
    continuity = build_continuity(transition)
    continuity["state"] = "identity_break"
    continuity = _rehash(continuity, "continuity_sha256")

    validation = validate_artifact(continuity)
    assert validation["valid"] is False
    assert any(error.get("path") == "state" for error in validation["errors"])


def test_ahead_and_behind_are_transition_state(git_repo):
    before = observe_checkout(git_repo, purpose="resume")
    before["git"]["upstream"] = "origin/main"
    before["git"]["ahead"] = 0
    before["git"]["behind"] = 0
    before = _rehash(before, "observation_sha256")
    after = deepcopy(before)
    after["git"]["ahead"] = 1
    after = _rehash(after, "observation_sha256")

    transition = build_transition(before, after)
    assert transition["state_changes"]["ahead"]["changed"] is True
    assert "continuity.ahead_changed" in transition["reason_codes"]
    assert build_continuity(transition)["state"] == "explainable_drift"
