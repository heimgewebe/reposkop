from __future__ import annotations

from reposkop.observation import observe_checkout


def _porcelain_v1_status(repo):
    import subprocess

    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
        ],
        check=True,
        capture_output=True,
    ).stdout


def test_clean_repository_observation(git_repo):
    result = observe_checkout(git_repo)
    assert result["kind"] == "reposkop_checkout_observation"
    assert result["schema_version"] == 2
    assert result["is_git_checkout"] is True
    assert result["git"]["dirty"] is False
    assert result["role"]["value"] == "canonical_checkout"
    assert len(result["observation_sha256"]) == 64


def test_dirty_repository_is_observed(git_repo):
    (git_repo / "file.txt").write_text("changed\n", encoding="utf-8")
    result = observe_checkout(git_repo)
    assert result["git"]["dirty"] is True
    assert result["git"]["unstaged"] is True


def test_untracked_file_is_not_misclassified_as_unstaged(git_repo):
    (git_repo / "new.txt").write_text("new\n", encoding="utf-8")
    result = observe_checkout(git_repo)
    assert result["git"]["dirty"] is True
    assert result["git"]["staged"] is False
    assert result["git"]["unstaged"] is False
    assert result["git"]["untracked"] is True
    assert result["git"]["status_entry_count"] == 1


def test_staged_rename_is_one_status_entry(git_repo):
    import hashlib
    import subprocess

    renamed = "renamed →\nfile.txt"
    subprocess.run(
        ["git", "-C", str(git_repo), "mv", "file.txt", renamed],
        check=True,
    )
    expected = _porcelain_v1_status(git_repo)
    result = observe_checkout(git_repo)
    assert result["git"]["dirty"] is True
    assert result["git"]["staged"] is True
    assert result["git"]["unstaged"] is False
    assert result["git"]["untracked"] is False
    assert result["git"]["status_entry_count"] == 1
    assert result["git"]["status_sha256"] == hashlib.sha256(expected).hexdigest()


def test_staged_copy_and_special_paths_preserve_v1_status_digest(git_repo):
    import hashlib
    import subprocess

    copied = "copied →\nfile.txt"
    subprocess.run(
        ["git", "-C", str(git_repo), "config", "status.renames", "copies"],
        check=True,
    )
    subprocess.run(["git", "-C", str(git_repo), "mv", "file.txt", copied], check=True)
    (git_repo / "file.txt").write_text("different\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "file.txt"], check=True)
    expected = _porcelain_v1_status(git_repo)

    assert b"C  copied" in expected
    result = observe_checkout(git_repo)

    assert result["git"]["dirty"] is True
    assert result["git"]["staged"] is True
    assert result["git"]["unstaged"] is False
    assert result["git"]["untracked"] is False
    assert result["git"]["status_entry_count"] == 2
    assert result["git"]["status_sha256"] == hashlib.sha256(expected).hexdigest()


def test_unmerged_status_preserves_v1_status_digest(git_repo):
    import hashlib
    import subprocess

    base_branch = subprocess.run(
        ["git", "-C", str(git_repo), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(git_repo), "checkout", "-qb", "conflict"], check=True)
    (git_repo / "file.txt").write_text("conflict branch\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qam", "conflict"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "checkout", "-q", base_branch], check=True)
    (git_repo / "file.txt").write_text("base branch\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qam", "base"], check=True)
    merge = subprocess.run(
        ["git", "-C", str(git_repo), "merge", "conflict"],
        check=False,
        capture_output=True,
    )
    expected = _porcelain_v1_status(git_repo)

    assert merge.returncode == 1
    result = observe_checkout(git_repo)

    assert result["git"]["dirty"] is True
    assert result["git"]["staged"] is True
    assert result["git"]["unstaged"] is True
    assert result["git"]["untracked"] is False
    assert result["git"]["status_entry_count"] == 1
    assert result["git"]["status_sha256"] == hashlib.sha256(expected).hexdigest()


def test_inherited_git_dir_cannot_redirect_target(git_repo, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(git_repo / "missing-git-dir"))
    monkeypatch.setenv("GIT_WORK_TREE", str(git_repo.parent))
    result = observe_checkout(git_repo)
    assert result["is_git_checkout"] is True
    assert result["identities"]["path"] == str(git_repo.resolve())


def test_missing_target_fails_as_data(tmp_path):
    result = observe_checkout(tmp_path / "missing")
    assert result["exists"] is False
    assert result["errors"] == ["target_missing"]
    assert result["role"]["value"] == "unknown"


def test_remote_credentials_are_not_emitted(git_repo):
    import subprocess

    subprocess.run(
        [
            "git",
            "-C",
            str(git_repo),
            "remote",
            "add",
            "origin",
            "https://secret@example.invalid/owner/repo.git",
        ],
        check=True,
    )
    result = observe_checkout(git_repo)
    assert result["identities"]["remote"] == "example.invalid/owner/repo"
    assert "secret" not in str(result)
    assert "origin_url" not in result["git"]


def test_remote_hosts_do_not_collide(git_repo):
    import subprocess

    subprocess.run(
        ["git", "-C", str(git_repo), "remote", "add", "origin", "git@host-a:owner/repo.git"],
        check=True,
    )
    first = observe_checkout(git_repo)
    subprocess.run(
        ["git", "-C", str(git_repo), "remote", "set-url", "origin", "git@host-b:owner/repo.git"],
        check=True,
    )
    second = observe_checkout(git_repo)
    assert first["identities"]["remote"] == "host-a/owner/repo"
    assert second["identities"]["remote"] == "host-b/owner/repo"
    assert (
        first["identities"]["repository_identity_sha256"]
        != second["identities"]["repository_identity_sha256"]
    )


def test_raw_non_utf8_status_bytes_have_distinct_digests(git_repo, monkeypatch):
    import hashlib
    import subprocess

    import reposkop.observation as module

    combined_args = [
        "status",
        "--porcelain=v2",
        "--branch",
        "--ahead-behind",
        "-z",
        "--untracked-files=normal",
    ]
    raw_paths = iter((b"\xff", b"\xfe"))
    real_git_bytes = module._git_bytes

    def raw_probe(path, arguments, *, timeout=10):
        if arguments == combined_args:
            payload = (
                b"# branch.oid "
                + b"0" * 40
                + b"\0# branch.head main\0? "
                + next(raw_paths)
                + b"\0"
            )
            return subprocess.CompletedProcess(arguments, 0, payload, b"")
        return real_git_bytes(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git_bytes", raw_probe)
    first = module.observe_checkout(git_repo)
    second = module.observe_checkout(git_repo)
    assert first["git"]["status_sha256"] == hashlib.sha256(b"?? \xff\0").hexdigest()
    assert second["git"]["status_sha256"] == hashlib.sha256(b"?? \xfe\0").hexdigest()
    assert first["git"]["untracked"] is True
    assert second["git"]["untracked"] is True


def test_failed_status_probe_is_incomplete(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    def probe(path, arguments, *, timeout=10):
        return subprocess.CompletedProcess(arguments, 1, b"", b"status failed")

    monkeypatch.setattr(module, "_git_bytes", probe)
    result = module.observe_checkout(git_repo)
    assert result["observation_complete"] is False
    assert result["git"]["dirty"] is None
    assert "status_failed" in result["errors"]


def test_missing_stat_identity_is_incomplete(git_repo, monkeypatch):
    import reposkop.observation as module

    monkeypatch.setattr(module, "_stat_identity", lambda path: None)
    result = module.observe_checkout(git_repo)
    assert result["observation_complete"] is False
    assert "target_identity_unavailable" in result["errors"]
    assert "git_dir_identity_unavailable" in result["errors"]
    assert "git_common_dir_identity_unavailable" in result["errors"]


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


def test_checkout_path_probes_are_batched_on_normal_checkout(git_repo, monkeypatch):
    import reposkop.observation as module

    real_run = module.subprocess.run
    calls = []

    def traced_run(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", traced_run)
    result = module.observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert sum(
        argv[-4:]
        == ["rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"]
        for argv in calls
    ) == 1
    assert not any(argv[-2:] == ["rev-parse", "--show-toplevel"] for argv in calls)
    assert not any(
        argv[-3:] == ["rev-parse", "--absolute-git-dir", "--git-common-dir"]
        for argv in calls
    )
    assert not any(argv[-2:] == ["rev-parse", "--absolute-git-dir"] for argv in calls)
    assert not any(argv[-2:] == ["rev-parse", "--git-common-dir"] for argv in calls)


def test_checkout_path_probe_falls_back_when_combined_output_is_ambiguous(
    git_repo, monkeypatch
):
    import subprocess

    import reposkop.observation as module

    real_git = module._git
    calls = []
    combined_args = [
        "rev-parse",
        "--show-toplevel",
        "--absolute-git-dir",
        "--git-common-dir",
    ]

    def probe(path, arguments, *, timeout=10):
        calls.append(tuple(arguments))
        if arguments == combined_args:
            return subprocess.CompletedProcess(arguments, 0, "one\ntwo\nthree\nfour\n", "")
        return real_git(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    result = module.observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert tuple(combined_args) in calls
    assert ("rev-parse", "--show-toplevel") in calls
    assert ("rev-parse", "--absolute-git-dir") in calls
    assert ("rev-parse", "--git-common-dir") in calls
    assert ("rev-parse", "--absolute-git-dir", "--git-common-dir") not in calls


def test_checkout_path_probe_timeout_is_not_blindly_retried(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    real_git = module._git
    checkout_path_calls = []
    combined_args = [
        "rev-parse",
        "--show-toplevel",
        "--absolute-git-dir",
        "--git-common-dir",
    ]

    def probe(path, arguments, *, timeout=10):
        if arguments == combined_args or arguments in (
            ["rev-parse", "--show-toplevel"],
            ["rev-parse", "--absolute-git-dir", "--git-common-dir"],
            ["rev-parse", "--absolute-git-dir"],
            ["rev-parse", "--git-common-dir"],
        ):
            checkout_path_calls.append(tuple(arguments))
        if arguments == combined_args:
            return subprocess.CompletedProcess(arguments, 124, "", "git observation probe timed out")
        return real_git(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    result = module.observe_checkout(git_repo)

    assert checkout_path_calls == [tuple(combined_args)]
    assert result["observation_complete"] is False
    assert result["errors"] == ["git_toplevel_probe_timeout"]
    assert result["git_probe"]["returncode"] == 124


def test_subdirectory_observation_uses_repository_toplevel(git_repo):
    nested = git_repo / "nested" / "deeper"
    nested.mkdir(parents=True)

    result = observe_checkout(nested)

    assert result["observation_complete"] is True
    assert result["target"]["path"] == str(nested.resolve())
    assert result["identities"]["path"] == str(git_repo.resolve())


def test_status_and_branch_state_probe_is_batched_on_normal_checkout(git_repo, monkeypatch):
    import reposkop.observation as module

    real_run = module.subprocess.run
    calls = []

    def traced_run(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", traced_run)
    result = module.observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert sum(
        argv[-6:]
        == [
            "status",
            "--porcelain=v2",
            "--branch",
            "--ahead-behind",
            "-z",
            "--untracked-files=normal",
        ]
        for argv in calls
    ) == 1
    assert not any(
        argv[-4:] == ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]
        for argv in calls
    )
    assert not any(
        argv[-6:]
        == [
            "status",
            "--porcelain=v2",
            "--branch",
            "--ahead-behind",
            "-z",
            "--untracked-files=no",
        ]
        for argv in calls
    )
    assert not any(argv[-2:] == ["rev-parse", "HEAD"] for argv in calls)
    assert not any(argv[-4:] == ["symbolic-ref", "--quiet", "--short", "HEAD"] for argv in calls)
    assert not any(
        argv[-4:] == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
        for argv in calls
    )
    assert not any(
        argv[-4:] == ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]
        for argv in calls
    )
    assert len(calls) == 3


def test_combined_status_preserves_v1_digest_and_all_dirty_indicators(git_repo):
    import hashlib
    import subprocess

    (git_repo / "file.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "file.txt"], check=True)
    (git_repo / "file.txt").write_text("unstaged\n", encoding="utf-8")
    (git_repo / "new →\nfile.txt").write_text("untracked\n", encoding="utf-8")
    expected = _porcelain_v1_status(git_repo)

    result = observe_checkout(git_repo)

    assert result["git"]["status_sha256"] == hashlib.sha256(expected).hexdigest()
    assert result["git"]["dirty"] is True
    assert result["git"]["staged"] is True
    assert result["git"]["unstaged"] is True
    assert result["git"]["untracked"] is True
    assert result["git"]["status_entry_count"] == 2


def test_branch_state_batch_observes_detached_head(git_repo):
    import subprocess

    expected_head = subprocess.run(
        ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(git_repo), "checkout", "--detach", "-q"], check=True)

    result = observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert result["git"]["head"] == expected_head
    assert result["git"]["branch"] is None
    assert result["git"]["detached"] is True
    assert result["git"]["upstream"] is None
    assert result["git"]["ahead"] is None
    assert result["git"]["behind"] is None


def test_branch_state_batch_observes_unborn_branch(tmp_path):
    import subprocess

    repo = tmp_path / "unborn"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    expected_branch = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = observe_checkout(repo)

    assert result["is_git_checkout"] is True
    assert result["observation_complete"] is False
    assert result["git"]["head"] is None
    assert result["git"]["branch"] == expected_branch
    assert result["git"]["detached"] is False
    assert result["git"]["upstream"] is None
    assert result["git"]["ahead"] is None
    assert result["git"]["behind"] is None
    assert "head_unavailable" in result["errors"]


def test_branch_state_batch_observes_upstream_counts(git_repo, tmp_path_factory):
    import subprocess

    remote = tmp_path_factory.mktemp("reposkop-remote") / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    subprocess.run(["git", "-C", str(git_repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(git_repo), "push", "-qu", "origin", "HEAD"], check=True)
    (git_repo / "file.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "commit", "-qam", "ahead"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "config", "status.aheadBehind", "false"], check=True)

    result = observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert result["git"]["upstream"] is not None
    assert result["git"]["ahead"] == 1
    assert result["git"]["behind"] == 0


def test_branch_state_probe_falls_back_on_malformed_metadata(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    real_git = module._git
    real_git_bytes = module._git_bytes
    calls = []
    combined_args = [
        "status",
        "--porcelain=v2",
        "--branch",
        "--ahead-behind",
        "-z",
        "--untracked-files=normal",
    ]

    def probe(path, arguments, *, timeout=10):
        calls.append(tuple(arguments))
        return real_git(path, arguments, timeout=timeout)

    def raw_probe(path, arguments, *, timeout=10):
        calls.append(tuple(arguments))
        if arguments == combined_args:
            return subprocess.CompletedProcess(
                arguments,
                0,
                b"# branch.oid invalid\0# branch.head main\0",
                b"",
            )
        return real_git_bytes(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    monkeypatch.setattr(module, "_git_bytes", raw_probe)
    result = module.observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert tuple(combined_args) in calls
    assert ("rev-parse", "HEAD") in calls
    assert ("symbolic-ref", "--quiet", "--short", "HEAD") in calls
    assert ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}") in calls
    assert ("status", "--porcelain=v1", "-z", "--untracked-files=normal") in calls


def test_status_probe_falls_back_on_malformed_combined_status(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    real_git = module._git
    real_git_bytes = module._git_bytes
    calls = []
    combined_args = [
        "status",
        "--porcelain=v2",
        "--branch",
        "--ahead-behind",
        "-z",
        "--untracked-files=normal",
    ]

    def probe(path, arguments, *, timeout=10):
        calls.append(tuple(arguments))
        return real_git(path, arguments, timeout=timeout)

    def raw_probe(path, arguments, *, timeout=10):
        calls.append(tuple(arguments))
        if arguments == combined_args:
            payload = (
                b"# branch.oid "
                + b"0" * 40
                + b"\0# branch.head main\0"
                + b"1 malformed\0"
            )
            return subprocess.CompletedProcess(arguments, 0, payload, b"")
        return real_git_bytes(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    monkeypatch.setattr(module, "_git_bytes", raw_probe)
    result = module.observe_checkout(git_repo)

    assert result["observation_complete"] is True
    assert tuple(combined_args) in calls
    assert ("rev-parse", "HEAD") in calls
    assert ("symbolic-ref", "--quiet", "--short", "HEAD") in calls
    assert ("status", "--porcelain=v1", "-z", "--untracked-files=normal") in calls


def test_combined_status_timeout_is_not_blindly_retried(git_repo, monkeypatch):
    import subprocess

    import reposkop.observation as module

    real_git = module._git
    real_git_bytes = module._git_bytes
    branch_calls = []
    combined_args = [
        "status",
        "--porcelain=v2",
        "--branch",
        "--ahead-behind",
        "-z",
        "--untracked-files=normal",
    ]
    fallback_args = {
        ("rev-parse", "HEAD"),
        ("symbolic-ref", "--quiet", "--short", "HEAD"),
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
        ("rev-list", "--left-right", "--count", "HEAD...@{upstream}"),
        ("status", "--porcelain=v1", "-z", "--untracked-files=normal"),
    }

    def probe(path, arguments, *, timeout=10):
        key = tuple(arguments)
        if key in fallback_args:
            branch_calls.append(key)
        return real_git(path, arguments, timeout=timeout)

    def raw_probe(path, arguments, *, timeout=10):
        key = tuple(arguments)
        if arguments == combined_args or key in fallback_args:
            branch_calls.append(key)
        if arguments == combined_args:
            return subprocess.CompletedProcess(
                arguments,
                124,
                b"",
                b"git observation probe timed out",
            )
        return real_git_bytes(path, arguments, timeout=timeout)

    monkeypatch.setattr(module, "_git", probe)
    monkeypatch.setattr(module, "_git_bytes", raw_probe)
    result = module.observe_checkout(git_repo)

    assert branch_calls == [tuple(combined_args)]
    assert result["observation_complete"] is False
    assert "head_unavailable" in result["errors"]
    assert "status_failed" in result["errors"]
    assert result["git"]["head"] is None
    assert result["git"]["branch"] is None
    assert result["git"]["upstream"] is None
    assert result["git"]["dirty"] is None
