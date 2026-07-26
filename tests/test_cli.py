from __future__ import annotations

import json

from reposkop.cli import main
from steuerboard.cli import main as legacy_main


def test_reposkop_cli_inspect(git_repo, capsys):
    assert main(["inspect", str(git_repo), "--json"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["kind"] == "reposkop_checkout_observation"


def test_legacy_observe_adapter(git_repo, capsys):
    assert legacy_main(["observe", "repo", str(git_repo), "--json"]) == 0
    captured = capsys.readouterr()
    assert "replaced by Reposkop" in captured.err
    assert json.loads(captured.out)["kind"] == "reposkop_checkout_observation"


def test_legacy_mutation_surface_fails_closed(capsys):
    assert legacy_main(["action", "run-switch-main"]) == 2
    value = json.loads(capsys.readouterr().out)
    assert value["effect_started"] is False
