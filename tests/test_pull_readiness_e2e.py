from __future__ import annotations

import json
from pathlib import Path

from steuerboard.action_plans import plan_git_pull_ff_only

ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_pull_readiness_accepts_externally_supplied_freshness_evidence() -> None:
    assessment = _load("examples/assessments/pull-preflight-local-clear-evidence-missing.json")
    evidence = _load("examples/remote-refresh-results/fetch-origin-prune-success.json")
    plan = plan_git_pull_ff_only(assessment, remote_refresh_result=evidence)
    assert plan["action"] == "git-pull-ff-only"
    assert plan["decision"] == "blocked"
    assert "remote_refresh.refresh-example-origin-prune-success" in plan["source_refs"]
    assert evidence["operation"] == "git.fetch_origin_prune"


def test_pull_readiness_remains_blocked_without_external_freshness_evidence() -> None:
    assessment = _load("examples/assessments/pull-preflight-local-clear-evidence-missing.json")
    plan = plan_git_pull_ff_only(assessment)
    assert plan["decision"] == "blocked"
    assert plan["boundary"]["does_not_mutate"] is True
