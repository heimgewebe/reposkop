# Reposkop

Reposkop is the deterministic, target-bound, read-only repository and checkout coherence adapter for the Heimgewebe operator ecosystem.

Canonical repository: `https://github.com/heimgewebe/reposkop` (GitHub repository ID `1232573747`). The former `heimgewebe/steuerboard` path is redirect compatibility only and is not a canonical system identity.

It observes one explicitly selected repository or checkout, validates supplied lifecycle evidence, and derives a non-authoritative coherence projection. It never fetches, pulls, switches branches, changes worktrees, dispatches tasks, approves actions, or mutates host state.

> Observation ≠ evidence binding ≠ projection ≠ decision ≠ effect

## Authority boundary

| Concern | Authority |
| --- | --- |
| Local repository and checkout observation | Reposkop |
| Read-only coherence projection from supplied evidence | Reposkop |
| Task, claim, queue and completion truth | Bureau |
| Git, worktree, process, service and host effects | Grabowski |
| Branch, pull-request, review and check truth | GitHub / CI |
| Repository context bundles | RepoGround |
| System identity and stable relations | Systemkatalog |
| Display and orientation | Leitstand |

A Reposkop state such as `remove_candidate` is an explanation, not deletion permission. Grabowski must obtain fresh authority and reproduce every live precondition before any effect. Reposkop reports therefore keep `effect_authorized` fixed to `false`.

## Commands

```text
reposkop inspect <path> [--role <role>] [--purpose <text>] --json
reposkop report <path> [--role <role>] [--purpose <text>] [--lifecycle-evidence <file>] --json
reposkop project <observation.json> [--lifecycle-evidence <file>] --json
reposkop inventory --config <explicit-targets.json> --json
reposkop validate <artifact.json> --json
```

There is no implicit filesystem discovery and no global scan by default. `inventory` reads only the targets explicitly listed in its configuration.

## Compatibility

The transitional `steuerboard` executable remains as a narrow, read-only adapter for:

```text
steuerboard observe repo <path> --json
steuerboard operator report --repo <path> [--lifecycle-evidence <file>] --json
```

All former mutation, approval, planning, runbook, network-refresh, service-gate and global-report surfaces fail closed with a migration message. The compatibility adapter is retained only for the bounded migration window documented in [Migration](docs/migration.md); it does not preserve the old repository identity or authority model.

## Validation

```text
make deploy-check
```

See:

- [Architecture audit](docs/audit-2026-07-24.md)
- [Architecture](docs/architecture.md)
- [Integration contract](docs/integration.md)
- [Automation decision](docs/automation.md)
- [Migration status](docs/migration.md)
