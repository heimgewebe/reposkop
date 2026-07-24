# Migration from Steuerboard to Reposkop

## Staged cutover

1. Land Reposkop core while keeping the `steuerboard` CLI adapter.
2. Change Grabowski's target-bound context adapter to call `reposkop report`.
3. Update Systemkatalog identity, relations and authority matrix.
4. Add or update the Leitstand source-bound display adapter.
5. Confirm no active consumer invokes removed legacy surfaces.
6. Rename the GitHub repository from `steuerboard` to `reposkop` and update remotes, RepoGround publication identity and deployment metadata.
7. Retain the `steuerboard` CLI adapter for one compatibility window; remove it only after consumer readback.

## Removed compatibility

Python imports of historical action, approval, runbook, remote-refresh, Heimserver service-gate and UI modules are intentionally not preserved. T003 established that no active consumer requires the retired mutation commands. Any newly discovered private consumer must migrate to the owning system rather than restoring duplicate authority.

## Repository rename gate

The repository rename is not part of the first code commit. It occurs only after all consumer PRs are merged and the old GitHub URL redirect, local remote, RepoGround bundle identity and Systemkatalog node are read back successfully.
