"""Fault-injection differential tests for Reposkop's narrow identity value.

The baseline below is deliberately non-authoritative. It models only a common set
of guard fields (path, branch, HEAD, and common-dir path) so these tests can ask
whether Reposkop's inode-bound and remote-bound identity catches anything beyond
those fields. It is not Grabowski code, policy, or a claim about Grabowski's real
guards.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from reposkop.observation import observe_checkout
from reposkop.schema_validation import validate_artifact
from reposkop.shadow import build_shadow_transition
from reposkop.transition import build_continuity, build_transition

_PURPOSE = "differential-falsification"


@dataclass(frozen=True)
class NonAuthoritativeBaselineObservation:
    path: str | None
    branch: str | None
    head: str | None
    git_common_dir: str | None


@dataclass(frozen=True)
class ExpectedDifferentialOutcome:
    baseline_changed_fields: tuple[str, ...]
    identity_continuity: str
    transition_reasons: tuple[str, ...]
    anomaly_codes: tuple[str, ...]
    continuity_state: str
    local_identity_continuity: str


def _git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _seed(path: Path, text: str = "one\n") -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "differential@example.invalid")
    _git(path, "config", "user.name", "Reposkop Differential")
    (path / "file.txt").write_text(text, encoding="utf-8")
    _git(path, "add", "file.txt")
    _git(path, "commit", "-qm", "initial")
    return path


def _clone(seed: Path, target: Path) -> Path:
    subprocess.run(
        ["git", "clone", "-q", str(seed), str(target)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return target


def _observe(path: Path):
    observation = observe_checkout(path, purpose=_PURPOSE)
    assert observation["observation_complete"] is True
    assert validate_artifact(observation)["valid"] is True
    return observation


def _baseline(observation) -> NonAuthoritativeBaselineObservation:
    identities = observation["identities"]
    git = observation["git"]
    return NonAuthoritativeBaselineObservation(
        path=identities["path"],
        branch=git["branch"],
        head=git["head"],
        git_common_dir=identities["git_common_dir"],
    )


def _baseline_changed_fields(before, after) -> tuple[str, ...]:
    before_baseline = _baseline(before)
    after_baseline = _baseline(after)
    return tuple(
        field
        for field in ("path", "branch", "head", "git_common_dir")
        if getattr(before_baseline, field) != getattr(after_baseline, field)
    )


def _stat_key(observation, field: str) -> tuple[int, int]:
    stat_identity = observation["identities"][field]
    return stat_identity["device"], stat_identity["inode"]


def _assert_differential(before, after, expected: ExpectedDifferentialOutcome) -> None:
    assert _baseline_changed_fields(before, after) == expected.baseline_changed_fields

    transition = build_transition(before, after)
    assert transition["identity_continuity"] == expected.identity_continuity
    assert transition["reason_codes"] == list(expected.transition_reasons)
    assert transition["anomaly_codes"] == list(expected.anomaly_codes)
    assert validate_artifact(transition)["valid"] is True

    continuity = build_continuity(transition)
    assert continuity["state"] == expected.continuity_state
    assert continuity["reason_codes"] == sorted(
        set(expected.transition_reasons) | set(expected.anomaly_codes)
    )
    assert validate_artifact(continuity)["valid"] is True

    shadow = build_shadow_transition(before, after)
    assert shadow["identity_continuity"] == expected.identity_continuity
    assert shadow["continuity_state"] == expected.continuity_state
    assert shadow["local_identity_continuity"] == expected.local_identity_continuity
    assert shadow["reason_codes"] == continuity["reason_codes"]
    assert shadow["anomaly_codes"] == list(expected.anomaly_codes)
    assert validate_artifact(shadow)["valid"] is True


def test_unique_same_path_checkout_replacement_preserving_apparent_git_state(tmp_path):
    """Unique target: the modeled path/branch/HEAD/common-dir guard stays unchanged."""
    seed = _seed(tmp_path / "seed")
    target = _clone(seed, tmp_path / "target")
    replacement = _clone(seed, tmp_path / "replacement")
    before = _observe(target)

    target.rename(tmp_path / "displaced-target")
    replacement.rename(target)
    after = _observe(target)

    assert before["git"]["status_sha256"] == after["git"]["status_sha256"]
    assert before["identities"]["remote"] == after["identities"]["remote"]
    assert _stat_key(before, "target_stat") != _stat_key(after, "target_stat")
    assert _stat_key(before, "git_dir_stat") != _stat_key(after, "git_dir_stat")
    assert _stat_key(before, "git_common_dir_stat") != _stat_key(
        after, "git_common_dir_stat"
    )
    assert before["identities"]["repository_identity_sha256"] == after["identities"][
        "repository_identity_sha256"
    ]
    assert before["identities"]["checkout_identity_sha256"] != after["identities"][
        "checkout_identity_sha256"
    ]
    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=(),
            identity_continuity="same_repository_different_checkout",
            transition_reasons=("identity.checkout_changed",),
            anomaly_codes=("identity.checkout_break",),
            continuity_state="identity_break",
            local_identity_continuity="broken",
        ),
    )


def test_unique_git_metadata_substitution_behind_stable_redirection_path(tmp_path):
    """Unique target: stable .git redirection text/path hides replaced Git metadata."""
    seed = _seed(tmp_path / "seed")
    target = _clone(seed, tmp_path / "target")
    donor = _clone(seed, tmp_path / "donor")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (target / ".git").rename(metadata / "current")
    (donor / ".git").rename(metadata / "replacement")
    (target / ".git").write_text(f"gitdir: {metadata / 'current'}\n", encoding="utf-8")
    before = _observe(target)

    (metadata / "current").rename(metadata / "displaced")
    (metadata / "replacement").rename(metadata / "current")
    after = _observe(target)

    assert _stat_key(before, "target_stat") == _stat_key(after, "target_stat")
    assert _stat_key(before, "git_dir_stat") != _stat_key(after, "git_dir_stat")
    assert _stat_key(before, "git_common_dir_stat") != _stat_key(
        after, "git_common_dir_stat"
    )
    assert before["identities"]["remote"] == after["identities"]["remote"]
    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=(),
            identity_continuity="same_repository_different_checkout",
            transition_reasons=("identity.checkout_changed",),
            anomaly_codes=("identity.checkout_break",),
            continuity_state="identity_break",
            local_identity_continuity="broken",
        ),
    )


def test_generic_git_dir_and_common_dir_pointer_redirection(tmp_path):
    """Generic control: common-dir path drift is already visible to the baseline."""
    seed = _seed(tmp_path / "seed")
    target = _clone(seed, tmp_path / "target")
    donor = _clone(seed, tmp_path / "donor")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (target / ".git").rename(metadata / "first")
    (donor / ".git").rename(metadata / "second")
    marker = target / ".git"
    marker.write_text(f"gitdir: {metadata / 'first'}\n", encoding="utf-8")
    before = _observe(target)

    marker.write_text(f"gitdir: {metadata / 'second'}\n", encoding="utf-8")
    after = _observe(target)

    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=("git_common_dir",),
            identity_continuity="same_repository_different_checkout",
            transition_reasons=(
                "identity.checkout_changed",
                "identity.git_common_dir_changed",
                "identity.git_dir_changed",
            ),
            anomaly_codes=("identity.checkout_break",),
            continuity_state="identity_break",
            local_identity_continuity="broken",
        ),
    )


def test_unique_remote_identity_substitution(tmp_path):
    """Unique target: remote lineage changes while all modeled guard fields stay fixed."""
    target = _clone(_seed(tmp_path / "seed"), tmp_path / "target")
    _git(target, "remote", "set-url", "origin", "git@host-a.invalid:owner/repo.git")
    before = _observe(target)

    _git(target, "remote", "set-url", "origin", "git@host-b.invalid:owner/repo.git")
    after = _observe(target)

    assert before["identities"]["remote"] == "host-a.invalid/owner/repo"
    assert after["identities"]["remote"] == "host-b.invalid/owner/repo"
    assert _stat_key(before, "target_stat") == _stat_key(after, "target_stat")
    assert _stat_key(before, "git_common_dir_stat") == _stat_key(
        after, "git_common_dir_stat"
    )
    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=(),
            identity_continuity="different_repository",
            transition_reasons=(
                "identity.checkout_changed",
                "identity.remote_changed",
                "identity.repository_changed",
            ),
            anomaly_codes=("identity.checkout_break", "identity.repository_break"),
            continuity_state="identity_break",
            local_identity_continuity="broken",
        ),
    )


def test_generic_different_repository_with_superficially_similar_git_state(tmp_path):
    """Generic control: similar branch/clean state still has baseline-visible HEAD drift."""
    first_seed = _seed(tmp_path / "first-seed", "first\n")
    second_seed = _seed(tmp_path / "second-seed", "second\n")
    target = _clone(first_seed, tmp_path / "target")
    replacement = _clone(second_seed, tmp_path / "replacement")
    before = _observe(target)

    target.rename(tmp_path / "displaced-target")
    replacement.rename(target)
    after = _observe(target)

    assert before["git"]["branch"] == after["git"]["branch"] == "main"
    assert before["git"]["dirty"] is after["git"]["dirty"] is False
    assert before["git"]["status_sha256"] == after["git"]["status_sha256"]
    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=("head",),
            identity_continuity="different_repository",
            transition_reasons=(
                "continuity.head_changed",
                "identity.checkout_changed",
                "identity.remote_changed",
                "identity.repository_changed",
            ),
            anomaly_codes=("identity.checkout_break", "identity.repository_break"),
            continuity_state="identity_break",
            local_identity_continuity="broken",
        ),
    )


def test_negative_control_harmless_worktree_state_drift(tmp_path):
    """Negative control: local state changes, but checkout identity does not break."""
    target = _clone(_seed(tmp_path / "seed"), tmp_path / "target")
    before = _observe(target)

    (target / "file.txt").write_text("ordinary edit\n", encoding="utf-8")
    after = _observe(target)

    assert before["identities"]["checkout_identity_sha256"] == after["identities"][
        "checkout_identity_sha256"
    ]
    _assert_differential(
        before,
        after,
        ExpectedDifferentialOutcome(
            baseline_changed_fields=(),
            identity_continuity="same_checkout",
            transition_reasons=(
                "continuity.dirty_state_changed",
                "continuity.status_changed",
            ),
            anomaly_codes=(),
            continuity_state="explainable_drift",
            local_identity_continuity="continuous",
        ),
    )
