from __future__ import annotations

import argparse
import json
import sys

from reposkop.evidence import load_json
from reposkop.observation import observe_checkout
from reposkop.report import build_report

_MIGRATION = (
    "Steuerboard was replaced by Reposkop. This compatibility command is read-only; "
    "use 'reposkop --help'."
)


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    print(_MIGRATION, file=sys.stderr)
    if len(arguments) >= 3 and arguments[:2] == ["observe", "repo"]:
        path = arguments[2]
        if "--json" not in arguments:
            _emit({"kind": "reposkop_error", "error": "--json is required"})
            return 2
        _emit(observe_checkout(path))
        return 0
    if len(arguments) >= 3 and arguments[:2] == ["operator", "report"]:
        parser = argparse.ArgumentParser(prog="steuerboard operator report")
        parser.add_argument("--repo", required=True)
        parser.add_argument("--lifecycle-evidence")
        parser.add_argument("--json", action="store_true", required=True)
        parsed = parser.parse_args(arguments[2:])
        evidence = load_json(parsed.lifecycle_evidence) if parsed.lifecycle_evidence else None
        _emit(build_report(parsed.repo, lifecycle_evidence=evidence))
        return 0
    _emit(
        {
            "schema_version": 1,
            "kind": "reposkop_compatibility_block",
            "error": "unsupported_legacy_surface",
            "migration": "Use a target-bound Reposkop command; no legacy action or global report is executed.",
            "effect_started": False,
        }
    )
    return 2
