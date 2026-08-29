from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .canonical import sha256_json
from .roles import classify_role
from .timeutil import utc_now

_CONFIG_KEYS_PATTERN = r"^(remote\.origin\.url|core\.sparsecheckout|core\.sparsecheckoutcone)$"

_SPARSE_CHECKOUT_DEFINITION_MAX_BYTES = 1024 * 1024

_ALLOWED_GIT_PROBES = {
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--absolute-git-dir"),
    ("rev-parse", "--git-common-dir"),
    ("rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"),
    ("rev-parse", "HEAD"),
    ("symbolic-ref", "--quiet", "--short", "HEAD"),
    ("status", "--porcelain=v1", "-z", "--untracked-files=normal"),
    (
        "status",
        "--porcelain=v2",
        "--branch",
        "--ahead-behind",
        "-z",
        "--untracked-files=normal",
    ),
    ("config", "--null", "--get-regexp", _CONFIG_KEYS_PATTERN),
    ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
    ("rev-parse", "--git-path", "info/sparse-checkout"),
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


@dataclass(frozen=True)
class _GitProbeBinding:
    work_tree: Path
    git_dir: Path
    common_dir: Path


_GitProbeTarget = Path | _GitProbeBinding


def _git_environment(target: _GitProbeTarget | None = None) -> dict[str, str]:
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
    if isinstance(target, _GitProbeBinding):
        env.update(
            {
                "GIT_WORK_TREE": str(target.work_tree),
                "GIT_DIR": str(target.git_dir),
                "GIT_COMMON_DIR": str(target.common_dir),
            }
        )
    return env


def _git_probe_cwd(target: _GitProbeTarget) -> Path:
    return target.work_tree if isinstance(target, _GitProbeBinding) else target


def _git_argv(target: _GitProbeTarget, arguments: list[str]) -> list[str]:
    if tuple(arguments) not in _ALLOWED_GIT_PROBES:
        raise ValueError(f"unsupported Git observation probe: {arguments!r}")
    return [*_GIT_PREFIX, "-C", str(_git_probe_cwd(target)), *arguments]


def _git(
    path: _GitProbeTarget, arguments: list[str], *, timeout: int = 10
) -> subprocess.CompletedProcess[str]:
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
            env=_git_environment(path),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "git observation probe timed out")


def _git_bytes(
    path: _GitProbeTarget,
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
            env=_git_environment(path),
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


def _git_config_values(
    path: _GitProbeTarget,
) -> tuple[dict[str, str], str | None]:
    result = _git(path, ["config", "--null", "--get-regexp", _CONFIG_KEYS_PATTERN])
    if result.returncode == 1:
        return {}, None
    if result.returncode != 0:
        return {}, "git_config_probe_failed"

    values: dict[str, str] = {}
    for record in result.stdout.split("\0"):
        if not record:
            continue
        key, separator, value = record.partition("\n")
        if not separator or not key:
            return {}, "git_config_probe_unparseable"
        values[key.lower()] = value
    return values, None


def _config_bool(
    values: dict[str, str],
    key: str,
) -> tuple[bool | None, str | None]:
    value = values.get(key.lower())
    if value is None:
        return False, None
    normalized = value.strip().lower()
    if normalized in {"", "true", "yes", "on", "1"}:
        return True, None
    if normalized in {"false", "no", "off", "0"}:
        return False, None
    return None, "sparse_checkout_config_unparseable"


def _sha256_file(
    path: Path,
    *,
    max_bytes: int = _SPARSE_CHECKOUT_DEFINITION_MAX_BYTES,
) -> str:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise OSError("file is not regular")
    if before.st_size > max_bytes:
        raise OSError("file exceeds size limit")

    flags = os.O_RDONLY
    for flag_name in ("O_CLOEXEC", "O_NONBLOCK", "O_NOFOLLOW"):
        flags |= getattr(os, flag_name, 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("opened file is not regular")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise OSError("file changed while opening")
        if opened.st_size > max_bytes:
            raise OSError("file exceeds size limit")

        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                return digest.hexdigest()
            total += len(chunk)
            if total > max_bytes:
                raise OSError("file exceeds size limit")
            digest.update(chunk)
    finally:
        os.close(fd)


def _sparse_checkout_state(
    path: _GitProbeTarget,
    config_values: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    enabled, error = _config_bool(config_values, "core.sparsecheckout")
    if error is not None or enabled is None:
        return None, error or "sparse_checkout_config_unavailable"
    if not enabled:
        return {
            "enabled": False,
            "cone_mode": None,
            "definition_sha256": None,
        }, None

    cone_mode, error = _config_bool(config_values, "core.sparsecheckoutcone")
    if error is not None or cone_mode is None:
        return None, error or "sparse_checkout_config_unavailable"
    definition = _text(_git(path, ["rev-parse", "--git-path", "info/sparse-checkout"]))
    definition_path = _resolve_git_path(_git_probe_cwd(path), definition)
    if definition_path is None:
        return None, "sparse_checkout_definition_unavailable"
    try:
        definition_sha256 = _sha256_file(definition_path)
    except OSError:
        return None, "sparse_checkout_definition_unavailable"
    return {
        "enabled": True,
        "cone_mode": cone_mode,
        "definition_sha256": definition_sha256,
    }, None


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


def _branch_state_individually(
    path: _GitProbeTarget,
) -> tuple[str | None, str | None, str | None, int | None, int | None, bool]:
    head = _text(_git(path, ["rev-parse", "HEAD"]))
    branch = _text(_git(path, ["symbolic-ref", "--quiet", "--short", "HEAD"]))
    upstream = _text(
        _git(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    )
    ahead: int | None = None
    behind: int | None = None
    counts_unparseable = False
    if upstream:
        counts = _text(_git(path, ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]))
        if counts:
            try:
                ahead_text, behind_text = counts.split()
                ahead, behind = int(ahead_text), int(behind_text)
            except (ValueError, TypeError):
                counts_unparseable = True
    return head, branch, upstream, ahead, behind, counts_unparseable


def _parse_branch_status_v2_z(
    payload: bytes,
) -> tuple[str | None, str | None, str | None, int | None, int | None]:
    fields: dict[str, bytes] = {}
    prefixes = {
        b"# branch.oid ": "oid",
        b"# branch.head ": "head",
        b"# branch.upstream ": "upstream",
        b"# branch.ab ": "ab",
    }
    for record in payload.split(b"\0"):
        if not record.startswith(b"# branch."):
            continue
        for prefix, key in prefixes.items():
            if record.startswith(prefix):
                if key in fields:
                    raise ValueError(f"duplicate branch status field: {key}")
                value = record[len(prefix) :]
                if not value:
                    raise ValueError(f"empty branch status field: {key}")
                fields[key] = value
                break

    if "oid" not in fields or "head" not in fields:
        raise ValueError("branch status is missing oid or head")

    oid = fields["oid"]
    if oid == b"(initial)":
        head: str | None = None
    else:
        if not 40 <= len(oid) <= 64 or any(
            character not in b"0123456789abcdef" for character in oid
        ):
            raise ValueError("branch status has an invalid object id")
        head = oid.decode("ascii")

    branch = (
        None
        if fields["head"] == b"(detached)"
        else fields["head"].decode("utf-8", errors="replace")
    )
    upstream_bytes = fields.get("upstream")
    upstream = (
        upstream_bytes.decode("utf-8", errors="replace")
        if upstream_bytes is not None
        else None
    )
    ahead: int | None = None
    behind: int | None = None
    ab = fields.get("ab")
    if ab is not None:
        if upstream is None:
            raise ValueError("branch status has ahead/behind counts without upstream")
        parts = ab.split()
        if len(parts) != 2 or not parts[0].startswith(b"+") or not parts[1].startswith(b"-"):
            raise ValueError("branch status has malformed ahead/behind counts")
        try:
            ahead = int(parts[0][1:])
            behind = int(parts[1][1:])
        except ValueError as exc:
            raise ValueError("branch status has non-integer ahead/behind counts") from exc
        if ahead < 0 or behind < 0:
            raise ValueError("branch status has negative ahead/behind counts")

    return head, branch, upstream, ahead, behind


def _v1_xy_from_v2(value: bytes) -> bytes:
    if len(value) != 2 or any(character not in b".MADRCUT" for character in value):
        raise ValueError("porcelain v2 status has an invalid XY field")
    return value.replace(b".", b" ")


def _validate_v2_submodule(value: bytes) -> None:
    valid = value == b"N..." or (
        len(value) == 4
        and value[:1] == b"S"
        and value[1] in b".C"
        and value[2] in b".M"
        and value[3] in b".U"
    )
    if not valid:
        raise ValueError("porcelain v2 status has an invalid submodule field")


def _validate_v2_mode(value: bytes) -> None:
    if len(value) != 6 or any(character not in b"01234567" for character in value):
        raise ValueError("porcelain v2 status has an invalid mode")


def _validate_v2_oid(value: bytes) -> None:
    if not 40 <= len(value) <= 64 or any(
        character not in b"0123456789abcdef" for character in value
    ):
        raise ValueError("porcelain v2 status has an invalid object id")


def _validate_v2_tracked_fields(
    fields: list[bytes],
    *,
    mode_indexes: tuple[int, ...],
    oid_indexes: tuple[int, ...],
) -> bytes:
    xy = _v1_xy_from_v2(fields[1])
    _validate_v2_submodule(fields[2])
    for index in mode_indexes:
        _validate_v2_mode(fields[index])
    for index in oid_indexes:
        _validate_v2_oid(fields[index])
    return xy


def _porcelain_v1_from_v2_z(payload: bytes) -> bytes:
    """Losslessly render the v1 -z status bytes represented by v2 -z records."""
    records = payload.split(b"\0")
    rendered: list[bytes] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            if any(records[index:]):
                raise ValueError("porcelain v2 status contains an empty record")
            continue
        if record.startswith(b"# "):
            continue
        if record.startswith(b"1 "):
            fields = record.split(b" ", 8)
            if len(fields) != 9 or not fields[8]:
                raise ValueError("malformed ordinary porcelain v2 status entry")
            xy = _validate_v2_tracked_fields(
                fields,
                mode_indexes=(3, 4, 5),
                oid_indexes=(6, 7),
            )
            rendered.append(xy + b" " + fields[8] + b"\0")
            continue
        if record.startswith(b"2 "):
            fields = record.split(b" ", 9)
            if len(fields) != 10 or not fields[9]:
                raise ValueError("malformed rename/copy porcelain v2 status entry")
            xy = _validate_v2_tracked_fields(
                fields,
                mode_indexes=(3, 4, 5),
                oid_indexes=(6, 7),
            )
            score = fields[8]
            if (
                len(score) < 2
                or score[:1] not in {b"R", b"C"}
                or not score[1:].isdigit()
                or score[:1] not in (xy[:1], xy[1:])
            ):
                raise ValueError("porcelain v2 status has an invalid rename/copy score")
            if index >= len(records) or not records[index]:
                raise ValueError("rename/copy porcelain v2 status is missing its source path")
            source = records[index]
            index += 1
            rendered.append(xy + b" " + fields[9] + b"\0" + source + b"\0")
            continue
        if record.startswith(b"u "):
            fields = record.split(b" ", 10)
            if len(fields) != 11 or not fields[10]:
                raise ValueError("malformed unmerged porcelain v2 status entry")
            xy = _validate_v2_tracked_fields(
                fields,
                mode_indexes=(3, 4, 5, 6),
                oid_indexes=(7, 8, 9),
            )
            rendered.append(xy + b" " + fields[10] + b"\0")
            continue
        if record.startswith(b"? ") and len(record) > 2:
            rendered.append(b"?? " + record[2:] + b"\0")
            continue
        raise ValueError("unknown porcelain v2 status record")

    result = b"".join(rendered)
    _parse_porcelain_v1_z(result)
    return result


def _status_and_branch_state(
    path: _GitProbeTarget,
) -> tuple[
    str | None,
    str | None,
    str | None,
    int | None,
    int | None,
    bool,
    subprocess.CompletedProcess[bytes],
]:
    combined = _git_bytes(
        path,
        [
            "status",
            "--porcelain=v2",
            "--branch",
            "--ahead-behind",
            "-z",
            "--untracked-files=normal",
        ],
    )
    if combined.returncode == 0:
        try:
            branch_state = _parse_branch_status_v2_z(combined.stdout)
            v1_status = _porcelain_v1_from_v2_z(combined.stdout)
            status_result = subprocess.CompletedProcess(
                combined.args,
                0,
                v1_status,
                combined.stderr,
            )
            return (*branch_state, False, status_result)
        except ValueError:
            pass
    elif combined.returncode == 124:
        status_result = _git_bytes(
            path,
            ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
        )
        return None, None, None, None, None, False, status_result

    # Preserve the prior probes when combined metadata or status records are
    # unexpected. A timed-out combined status probe is not blindly retried.
    branch_state = _branch_state_individually(path)
    status_result = _git_bytes(
        path,
        ["status", "--porcelain=v1", "-z", "--untracked-files=normal"],
    )
    return (*branch_state, status_result)


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

    initial_target_identity = _stat_identity(toplevel)
    initial_git_dir_identity = _stat_identity(git_dir)
    initial_common_dir_identity = _stat_identity(common_dir)
    probe_target: _GitProbeTarget = path
    if git_dir is not None and common_dir is not None:
        probe_target = _GitProbeBinding(
            work_tree=toplevel,
            git_dir=git_dir,
            common_dir=common_dir,
        )

    head, branch, upstream, ahead, behind, counts_unparseable, status_result = (
        _status_and_branch_state(probe_target)
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
    config_values, config_error = _git_config_values(probe_target)
    if config_error is not None:
        base["errors"].append(config_error)
        observation_complete = False
        sparse_checkout = None
    else:
        sparse_checkout, sparse_checkout_error = _sparse_checkout_state(
            probe_target, config_values
        )
        if sparse_checkout_error is not None:
            base["errors"].append(sparse_checkout_error)
            observation_complete = False
    origin_url = config_values.get("remote.origin.url") if config_error is None else None
    remote = _remote_identity(origin_url)
    if counts_unparseable:
        base["errors"].append("upstream_counts_unparseable")

    role, role_reasons = classify_role(
        path=toplevel,
        git_dir=git_dir,
        git_common_dir=common_dir,
        explicit_role=explicit_role,
    )
    operation_state = _operation_state(git_dir)
    alternates_configured = bool(
        common_dir and (common_dir / "objects" / "info" / "alternates").exists()
    )
    gitmodules_present = (toplevel / ".gitmodules").is_file()

    recheck_toplevel, recheck_git_dir, recheck_common_dir, _ = _git_checkout_paths(path)
    if (
        recheck_toplevel is None
        or recheck_git_dir is None
        or recheck_common_dir is None
    ):
        base["errors"].append("checkout_binding_recheck_unavailable")
        observation_complete = False
    elif (recheck_toplevel, recheck_git_dir, recheck_common_dir) != (
        toplevel,
        git_dir,
        common_dir,
    ):
        base["errors"].append("checkout_binding_changed_during_observation")
        observation_complete = False

    target_identity = _stat_identity(toplevel)
    git_dir_identity = _stat_identity(git_dir)
    common_dir_identity = _stat_identity(common_dir)
    for unavailable_label, changed_label, initial_identity, final_identity in (
        (
            "target_identity_unavailable",
            "target_identity_changed_during_observation",
            initial_target_identity,
            target_identity,
        ),
        (
            "git_dir_identity_unavailable",
            "git_dir_identity_changed_during_observation",
            initial_git_dir_identity,
            git_dir_identity,
        ),
        (
            "git_common_dir_identity_unavailable",
            "git_common_dir_identity_changed_during_observation",
            initial_common_dir_identity,
            common_dir_identity,
        ),
    ):
        if initial_identity is None or final_identity is None:
            base["errors"].append(unavailable_label)
            observation_complete = False
        elif initial_identity != final_identity:
            base["errors"].append(changed_label)
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
                "operation_state": operation_state,
                "alternates_configured": alternates_configured,
                "gitmodules_present": gitmodules_present,
                "sparse_checkout": sparse_checkout,
                "upstream": upstream,
                "ahead": ahead,
                "behind": behind,
                "upstream_freshness": "locally_available_only",
            },
        }
    )
    base["observation_sha256"] = sha256_json(base)
    return base
