from __future__ import annotations

import json
from copy import deepcopy

from reposkop.canonical import sha256_json
from reposkop.cli import main
from reposkop.observation import observe_checkout
from reposkop.schema_validation import validate_artifact
from reposkop.shadow import build_shadow_transition


def _rehash_observation(observation):
    observation = deepcopy(observation)
    observation.pop("observation_sha256", None)
    observation["observation_sha256"] = sha256_json(observation)
    return observation


def test_shadow_transition_emits_compact_canonical_identity_summary(git_repo):
    before = observe_checkout(git_repo, purpose="shadow")
    (git_repo / "file.txt").write_text("harmless drift\n", encoding="utf-8")
    after = observe_checkout(git_repo, purpose="shadow")

    shadow = build_shadow_transition(before, after)

    assert shadow["before_observation_sha256"] == before["observation_sha256"]
    assert shadow["after_observation_sha256"] == after["observation_sha256"]
    assert shadow["before_checkout_identity_sha256"] == before["identities"][
        "checkout_identity_sha256"
    ]
    assert shadow["after_checkout_identity_sha256"] == after["identities"][
        "checkout_identity_sha256"
    ]
    assert shadow["identity_continuity"] == "same_checkout"
    assert shadow["continuity_state"] == "explainable_drift"
    assert shadow["local_identity_continuity"] == "continuous"
    assert shadow["reason_codes"] == [
        "continuity.dirty_state_changed",
        "continuity.status_changed",
    ]
    assert shadow["anomaly_codes"] == []
    assert "operation_allowed" not in shadow
    assert "operation_allowed" in shadow["does_not_establish"]
    assert validate_artifact(shadow)["valid"] is True


def test_shadow_transition_cannot_establish_identity_from_incomplete_observation(git_repo):
    before = observe_checkout(git_repo, purpose="shadow")
    after = deepcopy(before)
    after["observation_complete"] = False
    after["errors"] = ["status_failed"]
    after = _rehash_observation(after)

    shadow = build_shadow_transition(before, after)

    assert validate_artifact(after)["valid"] is True
    assert shadow["identity_continuity"] == "inconclusive"
    assert shadow["continuity_state"] == "inconclusive"
    assert shadow["local_identity_continuity"] == "could_not_be_established"
    assert shadow["reason_codes"] == ["evidence.after_incomplete"]
    assert shadow["anomaly_codes"] == ["evidence.after_incomplete"]
    assert validate_artifact(shadow)["valid"] is True


def test_shadow_transition_rejects_rehashed_inconsistent_identity_flag(git_repo):
    observation = observe_checkout(git_repo, purpose="shadow")
    shadow = build_shadow_transition(observation, observation)
    shadow["local_identity_continuity"] = "broken"
    shadow.pop("shadow_transition_sha256")
    shadow["shadow_transition_sha256"] = sha256_json(shadow)

    validation = validate_artifact(shadow)

    assert validation["valid"] is False
    assert any(
        error.get("path") == "local_identity_continuity" for error in validation["errors"]
    )


def test_shadow_transition_sanitizes_noncanonical_source_digest(git_repo):
    before = observe_checkout(git_repo, purpose="shadow")
    after = deepcopy(before)
    after["observation_sha256"] = "not-a-canonical-digest"

    shadow = build_shadow_transition(before, after)

    assert shadow["after_observation_sha256"] is None
    assert shadow["local_identity_continuity"] == "could_not_be_established"
    assert shadow["reason_codes"] == ["evidence.transition_invalid"]
    assert shadow["anomaly_codes"] == ["evidence.after_invalid"]
    assert validate_artifact(shadow)["valid"] is True


def test_shadow_cli_accepts_separately_captured_before_and_after(git_repo, tmp_path, capsys):
    before = observe_checkout(git_repo, purpose="shadow")
    after = observe_checkout(git_repo, purpose="shadow")
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    after_path.write_text(json.dumps(after), encoding="utf-8")

    assert main(
        ["shadow", "--before", str(before_path), "--after", str(after_path), "--json"]
    ) == 0

    shadow = json.loads(capsys.readouterr().out)
    assert shadow["local_identity_continuity"] == "continuous"
    assert shadow["continuity_state"] == "intact"
    assert validate_artifact(shadow)["valid"] is True
