from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_REPOSITORY = "heimgewebe/reposkop"
PACKAGE_PREFIX = "reposkop/"
ENTRYPOINT = "reposkop.cli:main"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
RUNTIME_DEPENDENCIES = ("jsonschema",)
_MAX_SHEBANG_BYTES = 127
_VERSION_PATTERN = re.compile(rb"(?m)^__version__\s*=\s*['\"]([^'\"]+)['\"]\s*$")


class BuildError(RuntimeError):
    pass


def _git(repo: Path, *arguments: str) -> bytes:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "LC_ALL": "C",
        }
    )
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise BuildError(f"git {' '.join(arguments)} failed: {stderr or result.returncode}")
    return result.stdout


def _object_id(repo: Path, revision: str, suffix: str) -> str:
    value = _git(repo, "rev-parse", "--verify", f"{revision}{suffix}").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", value):
        raise BuildError(f"unexpected Git object id: {value!r}")
    return value


def _runtime_binding() -> tuple[str, str]:
    interpreter = sys.executable
    if not interpreter or not Path(interpreter).is_absolute():
        raise BuildError("builder Python interpreter must have an absolute executable path")
    if "\n" in interpreter or "\r" in interpreter:
        raise BuildError("builder Python interpreter path is not safe for a shebang")
    shebang = f"#!{interpreter}\n".encode()
    if len(shebang) > _MAX_SHEBANG_BYTES:
        raise BuildError("builder Python interpreter path is too long for a portable shebang")
    unavailable: list[str] = []
    for name in RUNTIME_DEPENDENCIES:
        try:
            importlib.import_module(name)
        except ImportError as exc:
            unavailable.append(f"{name} ({type(exc).__name__})")
    if unavailable:
        raise BuildError(
            "builder Python interpreter cannot import runtime dependencies: "
            + ", ".join(unavailable)
        )
    runtime_python = ".".join(str(value) for value in sys.version_info[:3])
    return interpreter, runtime_python


def _package_blobs(repo: Path, commit: str) -> list[tuple[str, str, bytes]]:
    raw = _git(repo, "ls-tree", "-r", "-z", commit, "--", "reposkop")
    entries: list[tuple[str, str, bytes]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BuildError("could not parse reposkop Git tree entry") from exc
        pure_path = PurePosixPath(path)
        if (
            object_type != "blob"
            or mode not in {"100644", "100755"}
            or not path.startswith(PACKAGE_PREFIX)
            or pure_path.is_absolute()
            or ".." in pure_path.parts
        ):
            raise BuildError(f"unsupported package tree entry: {path!r}")
        data = _git(repo, "cat-file", "blob", object_id)
        entries.append((path, object_id, data))
    entries.sort(key=lambda item: item[0])
    paths = [path for path, _, _ in entries]
    for required in ("reposkop/__init__.py", "reposkop/cli.py"):
        if required not in paths:
            raise BuildError(f"required package file is missing from source revision: {required}")
    if len(paths) != len(set(paths)):
        raise BuildError("duplicate package path in Git tree")
    return entries


def _version(entries: list[tuple[str, str, bytes]]) -> str:
    init_data = next(data for path, _, data in entries if path == "reposkop/__init__.py")
    match = _VERSION_PATTERN.search(init_data)
    if match is None:
        raise BuildError("could not determine Reposkop version from reposkop/__init__.py")
    return match.group(1).decode("utf-8")


def _payload(entries: list[tuple[str, str, bytes]]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, _, data in entries:
            info = zipfile.ZipInfo(path, date_time=ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return target.getvalue()


def _manifest(
    *,
    commit: str,
    source_tree: str,
    version: str,
    runtime_interpreter: str,
    runtime_python: str,
    entries: list[tuple[str, str, bytes]],
) -> dict[str, Any]:
    return {
        "artifact_kind": "reposkop-self-extracting-python",
        "entrypoint": ENTRYPOINT,
        "runtime_dependencies": list(RUNTIME_DEPENDENCIES),
        "runtime_interpreter": runtime_interpreter,
        "runtime_python": runtime_python,
        "schema_version": 1,
        "source_commit": commit,
        "source_repository": SOURCE_REPOSITORY,
        "source_tree": source_tree,
        "tracked_files": [
            {
                "path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
            for path, _, data in entries
        ],
        "version": version,
    }


_RUNTIME_TAIL = r'''

def _materialize(root: pathlib.Path) -> None:
    payload = base64.b64decode(b"".join(_PAYLOAD_B64.split()), validate=True)
    if hashlib.sha256(payload).hexdigest() != _PAYLOAD_SHA256:
        raise RuntimeError("embedded Reposkop payload digest mismatch")
    manifest = json.loads(_MANIFEST_JSON)
    expected = {item["path"]: item for item in manifest["tracked_files"]}
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = sorted(archive.namelist())
        if names != sorted(expected):
            raise RuntimeError("embedded Reposkop file inventory mismatch")
        for name in names:
            pure_name = pathlib.PurePosixPath(name)
            if not name.startswith("reposkop/") or pure_name.is_absolute() or ".." in pure_name.parts:
                raise RuntimeError("embedded Reposkop path is unsafe")
            data = archive.read(name)
            item = expected[name]
            if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise RuntimeError("embedded Reposkop file digest mismatch")
            target = root.joinpath(*pure_name.parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(data)
            target.chmod(0o600)


def _run() -> int:
    with tempfile.TemporaryDirectory(prefix=f"reposkop-{_VERSION}-") as directory:
        root = pathlib.Path(directory)
        _materialize(root)
        sys.path.insert(0, str(root))
        try:
            from reposkop.cli import main
            return int(main())
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    raise SystemExit(_run())
'''


def _render_executable(
    *,
    commit: str,
    version: str,
    runtime_interpreter: str,
    manifest: dict[str, Any],
    payload: bytes,
) -> bytes:
    manifest_json = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    encoded = base64.b64encode(payload).decode("ascii")
    wrapped_payload = "\n".join(textwrap.wrap(encoded, width=76))
    prefix = "\n".join(
        [
            f"#!{runtime_interpreter}",
            f"# Deterministic Reposkop {version} executable built from {SOURCE_REPOSITORY}@{commit}.",
            "import base64",
            "import hashlib",
            "import io",
            "import json",
            "import pathlib",
            "import sys",
            "import tempfile",
            "import zipfile",
            "",
            f"_SOURCE_COMMIT = {commit!r}",
            f"_VERSION = {version!r}",
            f"_PAYLOAD_SHA256 = {payload_sha256!r}",
            f"_MANIFEST_JSON = {manifest_json!r}",
            f'_PAYLOAD_B64 = b"""{wrapped_payload}"""',
        ]
    )
    return (prefix + _RUNTIME_TAIL).encode("utf-8")


def build_artifact(repo: Path, revision: str) -> tuple[bytes, dict[str, Any]]:
    repo = repo.resolve(strict=True)
    commit = _object_id(repo, revision, "^{commit}")
    source_tree = _object_id(repo, commit, "^{tree}")
    runtime_interpreter, runtime_python = _runtime_binding()
    entries = _package_blobs(repo, commit)
    version = _version(entries)
    payload = _payload(entries)
    manifest = _manifest(
        commit=commit,
        source_tree=source_tree,
        version=version,
        runtime_interpreter=runtime_interpreter,
        runtime_python=runtime_python,
        entries=entries,
    )
    artifact = _render_executable(
        commit=commit,
        version=version,
        runtime_interpreter=runtime_interpreter,
        manifest=manifest,
        payload=payload,
    )
    result = {
        "artifact_kind": manifest["artifact_kind"],
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "runtime_dependencies": list(RUNTIME_DEPENDENCIES),
        "runtime_interpreter": runtime_interpreter,
        "runtime_python": runtime_python,
        "source_commit": commit,
        "source_repository": SOURCE_REPOSITORY,
        "source_tree": source_tree,
        "tracked_file_count": len(entries),
        "version": version,
    }
    return artifact, result


def _absolute_output(output: Path) -> Path:
    expanded = output.expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(expanded))


def _atomic_write(output: Path, artifact: bytes) -> Path:
    output = _absolute_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise BuildError("output path must not be a symlink")
    if output.exists() and not output.is_file():
        raise BuildError("output path must be a regular file or absent")

    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary_path = Path(temporary)
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
    directory_fd = os.open(output.parent, directory_flags)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(artifact)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o755)
        os.replace(temporary_path, output)
        os.fsync(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        os.close(directory_fd)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the deterministic source-bound Reposkop self-extracting executable."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Reposkop Git repository (default: repository containing this script)",
    )
    parser.add_argument(
        "--revision",
        default="HEAD",
        help="exact Git revision to package (default: HEAD)",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifact, result = build_artifact(args.repo, args.revision)
        output = _atomic_write(args.output, artifact)
    except (BuildError, OSError) as exc:
        print(f"build_self_extracting: {exc}", file=sys.stderr)
        return 2
    result["output"] = str(output)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
