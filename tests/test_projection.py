from __future__ import annotations

from datetime import datetime, timedelta, timezone

from reposkop.canonical import sha256_json
from reposkop.observation import observe_checkout
from reposkop.projection import project_coherence


def evidence_for(observation, *, status="cleanup_candidate", bindings=None, archive=False):
    identities = observation["identities"]
    captured = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1)
    expires = captured + timedelta(minutes=2)
    captured_text = captured.isoformat().replace("+00:00", "Z")
    expires_text = expires.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "kind": "reposkop_lifecycle_evidence",
        "captured_at": captured_text,
        "expires_at": expires_text,
        "subject": {
            "path": identities["path"],
            "git_common_dir": identities["git_common_dir"],
            "remote": identities["remote"],
            "head": observation["git"]["head"],
            "role": observation["role"]["value"],
        },
        "sources": [
            {
                "authority": "grabowski",
                "source_ref": "test:receipt",
                "observed_at": captured_text,
                "sha256": "a" * 64,
            }
        ],
        "bindings": bindings
        or {"tasks": [], "leases": [], "processes": [], "tmux": [], "pull_requests": []},
        "lifecycle": {
            "status": status,
            "unique_commits": False,
            "archive_required": archive,
        },
    }


def test_clean_candidate_is_only_projection(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    result = project_coherence(observation, evidence_for(observation))
    assert result["state"] == "remove_candidate"
    assert result["effect_authorized"] is False


def test_active_lease_protects(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    bindings = {
        "tasks": [],
        "leases": [{"resource_key": "path:x", "active": True}],
        "processes": [],
        "tmux": [],
        "pull_requests": [],
    }
    result = project_coherence(observation, evidence_for(observation, bindings=bindings))
    assert result["state"] == "protected_active"


def test_dirty_state_wins_even_without_evidence(git_repo):
    (git_repo / "file.txt").write_text("changed\n", encoding="utf-8")
    observation = observe_checkout(git_repo)
    result = project_coherence(observation)
    assert result["state"] == "dirty_preserve"


def test_subject_mismatch_is_inconclusive(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    evidence["subject"]["head"] = "0" * 40
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert "subject_mismatch:head" in result["reasons"]


def test_archive_requirement_precedes_cleanup(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    result = project_coherence(observation, evidence_for(observation, archive=True))
    assert result["state"] == "archive_then_remove"


def test_incomplete_observation_cannot_become_remove_candidate(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    observation["observation_complete"] = False
    observation["observation_sha256"] = sha256_json(
        {key: value for key, value in observation.items() if key != "observation_sha256"}
    )
    result = project_coherence(observation, evidence_for(observation))
    assert result["state"] == "inconclusive"
    assert result["reasons"] == ["git_observation_incomplete"]


def test_stale_matching_active_binding_remains_protected(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    bindings = {
        "tasks": [{"id": "T1", "state": "running"}],
        "leases": [],
        "processes": [],
        "tmux": [],
        "pull_requests": [],
    }
    evidence = evidence_for(observation, bindings=bindings)
    evidence["captured_at"] = "2026-07-24T05:00:00Z"
    evidence["expires_at"] = "2026-07-24T05:02:00Z"
    evidence["sources"][0]["observed_at"] = "2026-07-24T05:00:00Z"
    result = project_coherence(observation, evidence)
    assert result["state"] == "protected_active"
    assert "active_bindings_from_stale_evidence" in result["reasons"]


def test_rewrapped_old_source_cannot_project_cleanup(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    captured = datetime.fromisoformat(evidence["captured_at"].replace("Z", "+00:00"))
    evidence["sources"][0]["observed_at"] = (captured - timedelta(minutes=6)).isoformat().replace(
        "+00:00", "Z"
    )
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert "lifecycle_evidence_invalid" in result["reasons"]
    assert "sources[0].observed_too_old" in result["evidence_validation"]["errors"]


def test_partial_binding_shape_is_inconclusive(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    evidence["bindings"]["leases"] = [{"resource_key": "path:x"}]
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert "lifecycle_evidence_invalid" in result["reasons"]


def test_excessive_evidence_ttl_is_inconclusive(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    captured = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=1)
    evidence["captured_at"] = captured.isoformat().replace("+00:00", "Z")
    evidence["expires_at"] = (captured + timedelta(minutes=30)).isoformat().replace(
        "+00:00", "Z"
    )
    evidence["sources"][0]["observed_at"] = evidence["captured_at"]
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert "evidence_ttl_exceeds_5_minutes" in result["evidence_validation"]["errors"]


def test_forged_observation_digest_cannot_project_cleanup(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    observation["target"]["purpose"] = "forged-after-digest"
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert result["reasons"][0] == "observation_invalid"


def test_arbitrary_source_cannot_claim_lifecycle_authority(git_repo):
    observation = observe_checkout(git_repo, explicit_role="linked_worktree")
    evidence = evidence_for(observation)
    evidence["sources"][0]["authority"] = "github"
    result = project_coherence(observation, evidence)
    assert result["state"] == "inconclusive"
    assert "lifecycle_authority_missing" in result["evidence_validation"]["errors"]
