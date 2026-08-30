from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

from reposkop import __version__


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_self_extracting.py"


def _run(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _git(repo: Path, *arguments: str) -> str:
    result = _run("git", "-C", str(repo), *arguments)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _build(repo: Path, output: Path, revision: str = "HEAD") -> dict[str, object]:
    result = _run(
        sys.executable,
        str(BUILDER),
        "--repo",
        str(repo),
        "--revision",
        revision,
        "--output",
        str(output),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_build_is_reproducible_and_source_bound(tmp_path: Path) -> None:
    head = _git(ROOT, "rev-parse", "HEAD")
    first = tmp_path / "reposkop-first"
    second = tmp_path / "reposkop-second"

    first_receipt = _build(ROOT, first)
    second_receipt = _build(ROOT, second)

    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    assert first_bytes == second_bytes
    assert first_receipt == second_receipt | {"output": str(first.resolve())}
    assert first_receipt["source_commit"] == head
    assert first_receipt["source_repository"] == "heimgewebe/reposkop"
    assert first_receipt["artifact_kind"] == "reposkop-self-extracting-python"
    assert first_receipt["artifact_sha256"] == hashlib.sha256(first_bytes).hexdigest()
    assert stat.S_IMODE(first.stat().st_mode) == 0o755

    version = _run(str(first), "--version")
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip() == f"reposkop {__version__}"


def test_built_artifact_exposes_current_observation_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "reposkop"
    _build(ROOT, artifact)

    result = _run(
        str(artifact),
        "inspect",
        str(ROOT),
        "--purpose",
        "self-extracting-builder-test",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert observation["schema_version"] == 2
    sparse_checkout = observation["git"]["sparse_checkout"]
    assert set(sparse_checkout) == {"enabled", "cone_mode", "definition_sha256"}


def test_build_reads_committed_git_objects_not_dirty_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "source"
    package = repo / "reposkop"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    (package / "cli.py").write_text(
        "from __future__ import annotations\n"
        "import argparse\n"
        "from . import __version__\n\n"
        "def main(argv=None):\n"
        "    parser = argparse.ArgumentParser(prog='reposkop')\n"
        "    parser.add_argument('--version', action='version', version=f'reposkop {__version__}')\n"
        "    parser.parse_args(argv)\n"
        "    return 0\n",
        encoding="utf-8",
    )
    assert _run("git", "init", "-q", str(repo)).returncode == 0
    assert _run("git", "-C", str(repo), "config", "user.email", "reposkop@example.invalid").returncode == 0
    assert _run("git", "-C", str(repo), "config", "user.name", "Reposkop").returncode == 0
    assert _run("git", "-C", str(repo), "add", "reposkop").returncode == 0
    commit = _run("git", "-C", str(repo), "commit", "-qm", "fixture")
    assert commit.returncode == 0, commit.stderr

    (package / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    artifact = tmp_path / "reposkop-fixture"
    receipt = _build(repo, artifact)

    assert receipt["source_commit"] == _git(repo, "rev-parse", "HEAD")
    result = _run(str(artifact), "--version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "reposkop 1.2.3"


def test_build_refuses_symlink_output_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("sentinel\n", encoding="utf-8")
    output = tmp_path / "reposkop"
    output.symlink_to(target)

    result = _run(
        sys.executable,
        str(BUILDER),
        "--repo",
        str(ROOT),
        "--revision",
        "HEAD",
        "--output",
        str(output),
    )

    assert result.returncode == 2
    assert "output path must not be a symlink" in result.stderr
    assert output.is_symlink()
    assert target.read_text(encoding="utf-8") == "sentinel\n"
