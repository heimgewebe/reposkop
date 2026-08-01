from __future__ import annotations

import argparse
import json
from typing import Any

from . import __version__
from .evidence import load_json
from .inventory import inspect_inventory
from .model import ROLE_VALUES
from .observation import observe_checkout
from .projection import project_coherence
from .report import build_report
from .schema_validation import validate_artifact
from .transition import observe_continuity, observe_transition


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reposkop")
    parser.add_argument("--version", action="version", version=f"reposkop {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="observe exactly one repository or checkout")
    inspect.add_argument("path")
    inspect.add_argument("--role", choices=ROLE_VALUES)
    inspect.add_argument("--purpose")
    inspect.add_argument("--json", action="store_true", required=True)

    transition = sub.add_parser(
        "transition",
        help="compare one bound observation with the current state of the same target",
    )
    transition.add_argument("path")
    transition.add_argument("--before", required=True)
    transition.add_argument("--role", choices=ROLE_VALUES)
    transition.add_argument("--purpose")
    transition.add_argument("--json", action="store_true", required=True)

    continuity = sub.add_parser(
        "continuity",
        help="classify whether a current checkout continues one bound observation",
    )
    continuity.add_argument("path")
    continuity.add_argument("--expected", required=True)
    continuity.add_argument("--role", choices=ROLE_VALUES)
    continuity.add_argument("--purpose")
    continuity.add_argument("--json", action="store_true", required=True)

    report = sub.add_parser("report", help="build one source-bound coherence report")
    report.add_argument("path")
    report.add_argument("--role", choices=ROLE_VALUES)
    report.add_argument("--purpose")
    report.add_argument("--lifecycle-evidence")
    report.add_argument("--json", action="store_true", required=True)

    project = sub.add_parser("project", help="project an existing observation")
    project.add_argument("observation")
    project.add_argument("--lifecycle-evidence")
    project.add_argument("--json", action="store_true", required=True)

    inventory = sub.add_parser("inventory", help="observe only explicitly configured targets")
    inventory.add_argument("--config", required=True)
    inventory.add_argument("--json", action="store_true", required=True)

    validate = sub.add_parser("validate", help="validate one Reposkop artifact")
    validate.add_argument("artifact")
    validate.add_argument("--json", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            _emit(observe_checkout(args.path, explicit_role=args.role, purpose=args.purpose))
        elif args.command == "transition":
            _emit(
                observe_transition(
                    load_json(args.before),
                    args.path,
                    explicit_role=args.role,
                    purpose=args.purpose,
                )
            )
        elif args.command == "continuity":
            _emit(
                observe_continuity(
                    load_json(args.expected),
                    args.path,
                    explicit_role=args.role,
                    purpose=args.purpose,
                )
            )
        elif args.command == "report":
            evidence = load_json(args.lifecycle_evidence) if args.lifecycle_evidence else None
            _emit(
                build_report(
                    args.path,
                    explicit_role=args.role,
                    purpose=args.purpose,
                    lifecycle_evidence=evidence,
                )
            )
        elif args.command == "project":
            observation = load_json(args.observation)
            evidence = load_json(args.lifecycle_evidence) if args.lifecycle_evidence else None
            _emit(project_coherence(observation, evidence))
        elif args.command == "inventory":
            _emit(inspect_inventory(load_json(args.config)))
        elif args.command == "validate":
            result = validate_artifact(load_json(args.artifact))
            _emit(result)
            return 0 if result["valid"] else 2
        else:
            raise AssertionError(args.command)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _emit({"schema_version": 1, "kind": "reposkop_error", "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
