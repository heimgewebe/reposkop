from __future__ import annotations

from reposkop.observation import observe_checkout


def test_clean_repository_observation(git_repo):
    result = observe_checkout(git_repo)
    assert result["kind"] == "reposkop_checkout_observation"
    assert result["is_git_checkout"] is True
    assert result["git"]["dirty"] is False
    assert result["role"]["value"] == "canonical_checkout"
    assert len(result["observation_sha256"]) == 64


def test_dirty_repository_is_observed(git_repo):
    (git_repo / "file.txt").write_text("changed\n", encoding="utf-8")
    result = observe_checkout(git_repo)
    assert result["git"]["dirty"] is True
    assert result["git"]["unstaged"] is True


def test_missing_target_fails_as_data(tmp_path):
    result = observe_checkout(tmp_path / "missing")
    assert result["exists"] is False
    assert result["errors"] == ["target_missing"]
    assert result["role"]["value"] == "unknown"


def test_remote_credentials_are_not_emitted(git_repo):
    import subprocess

    subprocess.run(
        ["git", "-C", str(git_repo), "remote", "add", "origin", "https://secret@example.invalid/owner/repo.git"],
        check=True,
    )
    result = observe_checkout(git_repo)
    assert result["identities"]["remote"] == "owner/repo"
    assert "secret" not in str(result)
    assert "origin_url" not in result["git"]


def test_failed_status_probe_is_incomplete(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    original = module._git

    def probe(path, arguments, *, timeout=10):
        if arguments and arguments[0] == "status":
            return subprocess.CompletedProcess(arguments, 1, "", "status failed")
        return original(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    result = module.observe_checkout(git_repo)
    assert result["observation_complete"] is False
    assert result["git"]["dirty"] is None
    assert "status_failed" in result["errors"]


def test_git_timeout_is_reported_without_crash(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 10))

    monkeypatch.setattr(module.subprocess, "run", timeout)
    result = module.observe_checkout(git_repo)
    assert result["observation_complete"] is False
    assert result["errors"] == ["git_toplevel_probe_timeout"]
    assert result["git_probe"]["returncode"] == 124


def test_unreviewed_git_probe_is_rejected(git_repo):
    import pytest

    import reposkop.observation as module

    with pytest.raises(ValueError, match="unsupported Git observation probe"):
        module._git(git_repo, ["fetch", "origin"])
