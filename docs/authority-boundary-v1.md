# Steuerboard Authority Boundary v1

Status: normative

## Decision

Steuerboard is a **repository observation and readiness-derivation library**. It may read local repository state, validate supplied evidence, and derive display-only assessments or plans. It does not own Git execution, network refresh, branch switching, pulls, task dispatch, queue state, approval authority, or runtime mutation.

Execution ownership is assigned as follows:

| Capability | Authority |
|---|---|
| repository observation and scope classification | Steuerboard |
| readiness and plan derivation from supplied evidence | Steuerboard |
| task, claim and completion truth | Bureau |
| Git fetch, pull, branch switch, worktree and host effects | Grabowski |
| source branch, PR and review state | GitHub |
| display and orientation | Leitstand/Cabinet, source-bound |

## Consumer proof

A source scan on 2026-07-10 found:

- Grabowski references Steuerboard reports and readiness context, but no live invocation of the three retired execution commands.
- Bureau references readiness/repository assessment semantics, but no live invocation of the retired execution commands.
- Cabinet observes Steuerboard as a repository and documentation source; it is not an execution consumer.

These are source-integration findings, not proof that no external private caller exists. Compatibility command names therefore remain visible and fail closed with a migration message.

## Retired compatibility commands

The following commands are no longer executable in Steuerboard:

- `remote-refresh fetch-origin-prune`
- `action run-git-pull-ff-only`
- `action run-switch-main`

Operational policy cannot re-enable them. They return a deterministic block before any network or repository effect. Existing readiness, approval-validation, and evidence-chain derivations remain available as read-only inputs to Grabowski or human review.

## Migration

1. Keep using Steuerboard for `observe`, `assess`, `inventory`, `operator report`, plan previews, and readiness validation.
2. Hand the resulting source-bound evidence to a typed Grabowski grip.
3. Let Grabowski reproduce live preconditions and perform the effect under its resource, review, and receipt boundaries.
4. Treat old Stage-D result examples as historical fixtures, not supported execution instructions.

## Non-claims

This decision does not make a derived readiness verdict an approval, does not grant Grabowski automatic execution permission, and does not prove that every undocumented external caller has migrated.
