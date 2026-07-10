from __future__ import annotations

import json
from pathlib import Path

import pytest

from steuerboard.local_config import load_local_config, require_operation_allowed
from steuerboard.remote_refresh import run_fetch_origin_prune


def _config(tmp_path: Path, *, allow_network_fetch: bool = True) -> Path:
    path = tmp_path / "local-config.json"
    path.write_text(json.dumps({
        "schema_version": "local-config.v1",
        "host": {"name": "test"},
        "paths": {"canonical_repo_roots": [str(tmp_path)], "excluded_repo_roots": []},
        "preferences": {"favorite_repo_paths": []},
        "policy": {
            "allow_mutating_actions": True,
            "allow_branch_switch": True,
            "allow_network_fetch": allow_network_fetch,
        },
    }), encoding="utf-8")
    return path


def test_fetch_origin_prune_is_retired_even_when_policy_allows(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    trace = tmp_path / "trace.json"
    with pytest.raises(ValueError, match="operation retired from steuerboard"):
        run_fetch_origin_prune(
            repo_path=str(tmp_path),
            config_path=str(config_path),
            assessment_id="assess-retired",
            command_trace_out=str(trace),
        )
    assert not trace.exists()


def test_retirement_precedes_repository_and_output_validation(tmp_path: Path) -> None:
    config_path = _config(tmp_path)
    config = load_local_config(config_path)
    with pytest.raises(ValueError, match="use grabowski git/fleet execution"):
        require_operation_allowed(config, "remote-refresh.fetch-origin-prune")


def test_policy_cannot_reenable_retired_fetch(tmp_path: Path) -> None:
    config = load_local_config(_config(tmp_path, allow_network_fetch=True))
    with pytest.raises(ValueError, match="observation and derivation only"):
        require_operation_allowed(config, "remote-refresh.fetch-origin-prune")
