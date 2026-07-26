# Reposkop

Reposkop is the deterministic, target-bound, read-only repository and checkout coherence adapter for the Heimgewebe operator ecosystem.

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

A Reposkop state such as `remove_candidate` is an explanation, not deletion permission. Grabowski must obtain fresh authority and reproduce every live precondition before any effect.

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

The transitional `steuerboard` executable remains as a read-only adapter for:

```text
steuerboard observe repo <path> --json
steuerboard operator report --repo <path> [--lifecycle-evidence <file>] --json
```

All former mutation, approval, planning, runbook, network-refresh, service-gate and global-report surfaces fail closed with a migration message. The GitHub repository keeps its old name until all consumers have passed staged cutover readbacks.

## Validation

```text
make deploy-check
```

See:

- [Architecture audit](docs/audit-2026-07-24.md)
- [Architecture](docs/architecture.md)
- [Integration contract](docs/integration.md)
- [Automation decision](docs/automation.md)
- [Migration plan](docs/migration.md)
