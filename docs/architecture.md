# Reposkop architecture

Status: normative.

Reposkop has four layers only:

1. **Target selection** — exactly one path or an explicit bounded target list.
2. **Observation** — fixed read-only Git commands and path identity.
3. **Evidence binding** — validation of externally supplied, versioned, digest- and freshness-bound lifecycle evidence.
4. **Projection** — deterministic explanation with no effect authority.

The old Action, Approval, Execution, Runbook, Service-Gate and standalone UI layers are removed. They duplicated responsibilities already owned by Grabowski, Bureau, Infra and Leitstand.

## Identity axes

Reposkop keeps these identities separate:

- path identity;
- Git toplevel and Git common-directory identity;
- remote repository identity;
- purpose identity;
- checkout role.

Two paths can belong to the same Git repository and still have different purposes and lifecycle owners. Conversely, matching remote URLs do not prove that two checkouts are interchangeable.

## Checkout roles

- `canonical_checkout`
- `linked_worktree`
- `auxiliary_clone`
- `managed_repoground_source`
- `legacy_repobrief_source`
- `deployment_source`
- `grabowski_workspace`
- `grabowski_lifecycle_worktree`
- `unknown`

Explicit source-bound role input overrides heuristics. Heuristics are explanations, not ownership truth.

## Projection states

- `managed_retain`
- `protected_active`
- `dirty_preserve`
- `remove_candidate`
- `archive_then_remove`
- `inconclusive`

All states are non-authoritative. `remove_candidate` means only that the supplied evidence currently contains no represented blocker. It never means that absence of a blocker has been proven globally.

## Evidence freshness bound

Lifecycle evidence has a maximum five-minute validity interval. Longer envelopes are invalid, not merely stale. Every embedded source observation must also be no more than five minutes older than the envelope capture time; an old authority readback cannot become current merely by being wrapped in a fresh envelope. A digest inside a source reference is a binding claim supplied by the authority; Reposkop validates its shape and envelope binding but does not independently reproduce the authority's private source state.
