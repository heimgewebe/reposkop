from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .canonical import sha256_json
from .roles import classify_role
from .timeutil import utc_now

_ALLOWED_GIT_PROBES = {
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--absolute-git-dir"),
    ("rev-parse", "--git-common-dir"),
    ("rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"),
    ("rev-parse", "HEAD"),
    ("symbolic-ref", "--quiet", "--short", "HEAD"),
    ("status", "--porcelain=v1", "-z", "--untracked-files=normal"),
    ("config", "--get", "remote.origin.url"),
    ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
    ("rev-list", "--left-right", "--count", "HEAD...@{upstream}"),
}

_GIT_PREFIX = [
    "git",
    "-c",
    "core.pager=cat",
    "-c",
    "pager.status=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "protocol.file.allow=never",
]

_GIT_ENVIRONMENT_OVERRIDES = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_SYSTEM",
    "GIT_DIR",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_EXEC_PATH",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
}
_GIT_ENVIRONMENT_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def _git_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in tuple(env):
        if key in _GIT_ENVIRONMENT_OVERRIDES or key.startswith(_GIT_ENVIRONMENT_PREFIXES):
            env.pop(key, None)
    env.update(
        {
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return env


def _git_argv(path: Path, arguments: list[str]) -> list[str]:
    if tuple(arguments) not in _ALLOWED_GIT_PROBES:
        raise ValueError(f"unsupported Git observation probe: {arguments!r}")
    return [*_GIT_PREFIX, "-C", str(path), *arguments]


def _git(path: Path, arguments: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    argv = _git_argv(path, arguments)
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_git_environment(),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "git observation probe timed out")


def _git_bytes(
    path: Path,
    arguments: list[str],
    *,
    timeout: int = 10,
) -> subprocess.CompletedProcess[bytes]:
    argv = _git_argv(path, arguments)
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=timeout,
            env=_git_environment(),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv,
            124,
            b"",
            b"git observation probe timed out",
        )


def _text(result: subprocess.CompletedProcess[str]) -> str | None:
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _resolve_git_path(base: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def _git_directories_individually(path: Path) -> tuple[Path | None, Path | None]:
    return (
        _resolve_git_path(path, _text(_git(path, ["rev-parse", "--absolute-git-dir"]))),
        _resolve_git_path(path, _text(_git(path, ["rev-parse", "--git-common-dir"]))),
    )


def _git_checkout_paths(
    path: Path,
) -> tuple[Path | None, Path | None, Path | None, subprocess.CompletedProcess[str]]:
    combined = _git(
        path,
        ["rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"],
    )
    if combined.returncode == 0:
        values = [line.strip() for line in combined.stdout.splitlines()]
        if len(values) == 3 and all(values):
            return (
                Path(values[0]).resolve(strict=False),
                _resolve_git_path(path, values[1]),
                _resolve_git_path(path, values[2]),
                combined,
            )
    elif combined.returncode == 124:
        return None, None, None, combined

    # A path can legally contain newlines, so ambiguous combined output must never
    # be split by guesswork. Fall back to the original independent probes.
    toplevel_result = _git(path, ["rev-parse", "--show-toplevel"])
    toplevel_text = _text(toplevel_result)
    if toplevel_text is None:
        return None, None, None, toplevel_result
    git_dir, common_dir = _git_directories_individually(path)
    return Path(toplevel_text).resolve(strict=False), git_dir, common_dir, toplevel_result


def _remote_identity(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    value = url.strip()
    if "://" in value:
        parsed = urlsplit(value)
        path = parsed.path.removesuffix(".git").strip("/")
        if parsed.hostname:
            host = parsed.hostname.lower()
            return f"{host}/{path}" if path else host
        if parsed.scheme == "file":
            return f"file:{parsed.path.removesuffix('.git')}"
    prefix, separator, path = value.partition(":")
    if separator and "@" in prefix and "/" not in prefix:
        host = prefix.rsplit("@", 1)[1].lower()
        normalized_path = path.removesuffix(".git").strip("/")
        return f"{host}/{normalized_path}" if normalized_path else host
    return f"local:{value.removesuffix('.git').rstrip('/')}"


def _parse_porcelain_v1_z(payload: bytes) -> tuple[int, bool, bool, bool, bool]:
    records = payload.split(b"\0")
    index = 0
    count = 0
    staged = False
    unstaged = False
    untracked = False

    while index < len(records):
        entry = records[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 3 or entry[2] != ord(" "):
            raise ValueError("malformed porcelain status entry")

        index_status, worktree_status = entry[0], entry[1]
        count += 1
        if index_status == ord("?") and worktree_status == ord("?"):
            untracked = True
        elif index_status != ord("!") or worktree_status != ord("!"):
            staged = staged or index_status != ord(" ")
            unstaged = unstaged or worktree_status != ord(" ")

        if index_status in {ord("R"), ord("C")} or worktree_status in {ord("R"), ord("C")}:
            if index >= len(records) or not records[index]:
                raise ValueError("rename or copy status is missing its source path")
            index += 1

    return count, count > 0, staged, unstaged, untracked


def _stat_identity(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        metadata = path.stat()
    except OSError:
        return None
    return {
        "path": str(path),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
    }


def _operation_state(git_dir: Path | None) -> list[str]:
    if git_dir is None:
        return []
    markers = {
        "rebase": (git_dir / "rebase-merge", git_dir / "rebase-apply"),
        "merge": (git_dir / "MERGE_HEAD",),
        "cherry_pick": (git_dir / "CHERRY_PICK_HEAD",),
        "revert": (git_dir / "REVERT_HEAD",),
        "bisect": (git_dir / "BISECT_LOG",),
        "sequencer": (git_dir / "sequencer",),
    }
    return sorted(name for name, paths in markers.items() if any(path.exists() for path in paths))


def observe_checkout(
    raw_path: str | Path,
    *,
    explicit_role: str | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    path = Path(raw_path).expanduser().resolve(strict=False)
    observed_at = utc_now()
    base: dict[str, Any] = {
        "schema_version": 2,
        "kind": "reposkop_checkout_observation",
        "observed_at": observed_at,
        "authority": {
            "producer": "reposkop",
            "domain": "local_checkout_identity",
            "claim": "canonical",
        },
        "target": {"path": str(path), "purpose": purpose},
        "exists": path.exists(),
        "is_git_checkout": False,
        "observation_complete": False,
        "errors": [],
        "does_not_establish": [
            "remote_freshness",
            "task_or_lease_truth",
            "pull_request_truth",
            "effect_authorization",
        ],
    }
    if not path.exists():
        base["errors"].append("target_missing")
        role, role_reasons = classify_role(
            path=path, git_dir=None, git_common_dir=None, explicit_role=explicit_role
        )
        base["role"] = {"value": role, "reasons": role_reasons}
        base["observation_sha256"] = sha256_json(base)
        return base
    if not path.is_dir():
        base["errors"].append("target_not_directory")
        role, role_reasons = classify_role(
            path=path, git_dir=None, git_common_dir=None, explicit_role=explicit_role
        )
        base["role"] = {"value": role, "reasons": role_reasons}
        base["observation_sha256"] = sha256_json(base)
        return base

    toplevel, git_dir, common_dir, toplevel_result = _git_checkout_paths(path)
    if toplevel is None:
        base["errors"].append(
            "git_toplevel_probe_timeout" if toplevel_result.returncode == 124 else "not_git_checkout"
        )
        role, role_reasons = classify_role(
            path=path, git_dir=None, git_common_dir=None, explicit_role=explicit_role
        )
        base["role"] = {"value": role, "reasons": role_reasons}
        base["git_probe"] = {
            "returncode": toplevel_result.returncode,
            "stderr": toplevel_result.stderr.strip()[:500],
        }
        base["observation_sha256"] = sha256_json(base)
        return base

    head = _text(_git(path, ["rev-parse", "HEAD"]))
    branch = _text(_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"]))
    status_result = _git_bytes(
        path,
        ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
    )
    observation_complete = True
    if git_dir is None:
        base["errors"].append("git_dir_unavailable")
        observation_complete = False
    if common_dir is None:
        base["errors"].append("git_common_dir_unavailable")
        observation_complete = False
    if head is None:
        base["errors"].append("head_unavailable")
        observation_complete = False
    if status_result.returncode != 0:
        base["errors"].append("status_failed")
        status_entry_count = 0
        dirty: bool | None = None
        staged = unstaged = untracked = None
        status_sha256 = None
        observation_complete = False
    else:
        try:
            status_entry_count, dirty, staged, unstaged, untracked = _parse_porcelain_v1_z(
                status_result.stdout
            )
            status_sha256 = hashlib.sha256(status_result.stdout).hexdigest()
        except ValueError:
            base["errors"].append("status_unparseable")
            status_entry_count = 0
            dirty = staged = unstaged = untracked = None
            status_sha256 = None
            observation_complete = False
    origin_url = _text(_git(path, ["config", "--get", "remote.origin.url"]))
    remote = _remote_identity(origin_url)
    upstream = _text(
        _git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    )
    ahead: int | None = None
    behind: int | None = None
    if upstream:
        counts = _text(_git(path, ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]))
        if counts:
            try:
                ahead_text, behind_text = counts.split()
                ahead, behind = int(ahead_text), int(behind_text)
            except (ValueError, TypeError):
                base["errors"].append("upstream_counts_unparseable")

    role, role_reasons = classify_role(
        path=toplevel,
        git_dir=git_dir,
        git_common_dir=common_dir,
        explicit_role=explicit_role,
    )
    target_identity = _stat_identity(toplevel)
    git_dir_identity = _stat_identity(git_dir)
    common_dir_identity = _stat_identity(common_dir)
    for label, identity in (
        ("target_identity_unavailable", target_identity),
        ("git_dir_identity_unavailable", git_dir_identity),
        ("git_common_dir_identity_unavailable", common_dir_identity),
    ):
        if identity is None:
            base["errors"].append(label)
            observation_complete = False
    checkout_identity_material = {
        "target": target_identity,
        "git_dir": git_dir_identity,
        "git_common_dir": common_dir_identity,
        "remote": remote,
        "role": role,
        "purpose": purpose,
    }
    repository_identity_material: dict[str, Any]
    if remote:
        repository_identity_material = {"remote": remote}
    else:
        repository_identity_material = {"git_common_dir": common_dir_identity}

    base.update(
        {
            "is_git_checkout": True,
            "observation_complete": observation_complete,
            "target": {"path": str(path), "purpose": purpose},
            "identities": {
                "path": str(toplevel),
                "git_dir": str(git_dir) if git_dir else None,
                "git_common_dir": str(common_dir) if common_dir else None,
                "remote": remote,
                "purpose": purpose,
                "target_stat": target_identity,
                "git_dir_stat": git_dir_identity,
                "git_common_dir_stat": common_dir_identity,
                "repository_identity_sha256": sha256_json(repository_identity_material),
                "checkout_identity_sha256": sha256_json(checkout_identity_material),
            },
            "role": {"value": role, "reasons": role_reasons},
            "git": {
                "head": head,
                "branch": branch,
                "detached": branch is None,
                "dirty": dirty,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "status_entry_count": status_entry_count,
                "status_sha256": status_sha256,
                "operation_state": _operation_state(git_dir),
                "alternates_configured": bool(
                    common_dir and (common_dir / "objects" / "info" / "alternates").exists()
                ),
                "gitmodules_present": (toplevel / ".gitmodules").is_file(),
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "upstream_freshness": "locally_available_only",
            },
        }
    )
    base["observation_sha256"] = sha256_json(base)
    return base
