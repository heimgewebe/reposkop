from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .roles import classify_role
from .timeutil import utc_now

_ALLOWED_GIT_PROBES = {
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--absolute-git-dir"),
    ("rev-parse", "--git-common-dir"),
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


def _git(path: Path, arguments: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    if tuple(arguments) not in _ALLOWED_GIT_PROBES:
        raise ValueError(f"unsupported Git observation probe: {arguments!r}")
    env = os.environ.copy()
    env.update({"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C", "LANG": "C"})
    argv = [*_GIT_PREFIX, "-C", str(path), *arguments]
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "git observation probe timed out")


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


def _remote_identity(url: str | None) -> str | None:
    if not url:
        return None
    value = url.removesuffix(".git")
    if value.startswith("git@") and ":" in value:
        value = value.split(":", 1)[1]
    elif "://" in value:
        value = value.split("://", 1)[1]
        value = value.split("/", 1)[1] if "/" in value else value
    return value.strip("/") or None


def observe_checkout(
    raw_path: str | Path,
    *,
    explicit_role: str | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    path = Path(raw_path).expanduser().resolve(strict=False)
    observed_at = utc_now()
    base: dict[str, Any] = {
        "schema_version": 1,
        "kind": "reposkop_checkout_observation",
        "observed_at": observed_at,
        "target": {"path": str(path), "purpose": purpose},
        "exists": path.exists(),
        "is_git_checkout": False,
        "observation_complete": False,
        "errors": [],
        "does_not_establish": [
            "remote_freshness",
            "task_or_lease_truth",
            "pull_request_truth",
            "cleanup_or_mutation_authority",
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

    toplevel_result = _git(path, ["rev-parse", "--show-toplevel"])
    toplevel_text = _text(toplevel_result)
    if toplevel_text is None:
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

    toplevel = Path(toplevel_text).resolve(strict=False)
    git_dir = _resolve_git_path(path, _text(_git(path, ["rev-parse", "--absolute-git-dir"])))
    common_dir = _resolve_git_path(path, _text(_git(path, ["rev-parse", "--git-common-dir"])))
    head = _text(_git(path, ["rev-parse", "HEAD"]))
    branch = _text(_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"]))
    status_result = _git(path, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
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
        status_entries: list[str] = []
        dirty: bool | None = None
        staged = unstaged = untracked = None
        observation_complete = False
    else:
        status_entries = [entry for entry in status_result.stdout.split("\0") if entry]
        dirty = bool(status_entries)
        staged = any(len(entry) >= 2 and entry[0] not in {" ", "?"} for entry in status_entries)
        unstaged = any(len(entry) >= 2 and entry[1] != " " for entry in status_entries)
        untracked = any(entry.startswith("??") for entry in status_entries)
    origin_url = _text(_git(path, ["config", "--get", "remote.origin.url"]))
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
    base.update(
        {
            "is_git_checkout": True,
            "observation_complete": observation_complete,
            "target": {"path": str(path), "purpose": purpose},
            "identities": {
                "path": str(toplevel),
                "git_dir": str(git_dir) if git_dir else None,
                "git_common_dir": str(common_dir) if common_dir else None,
                "remote": _remote_identity(origin_url),
                "purpose": purpose,
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
                "status_entry_count": len(status_entries),
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "upstream_freshness": "locally_available_only",
            },
        }
    )
    base["observation_sha256"] = sha256_json(base)
    return base
