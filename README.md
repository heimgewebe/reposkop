# Reposkop

Reposkop is the canonical producer of local checkout identity, transition and continuity truth for the Heimgewebe operator ecosystem.

It answers three operational questions:

1. **Identity** — which exact repository checkout is this?
2. **Transition** — what changed between a bound observation and the current state?
3. **Continuity** — is resumed work still attached to the same checkout identity?

Reposkop derives these facts from one explicitly selected local target. Its artifacts are deterministic, schema-versioned and digest-bound.

## Authority scope

Reposkop is authoritative for:

- the canonical representation of a local checkout identity;
- the canonical comparison of two bound checkout observations;
- the continuity classification derived from that comparison;
- machine-readable reason and anomaly codes for identity and state changes.

Other systems retain their own authority:

| Concern | Authority |
| --- | --- |
| Local checkout identity, transition and continuity | Reposkop |
| Task, claim, queue and completion truth | Bureau |
| Effects, leases, processes, worktrees and host mutation | Grabowski |
| Pull requests, reviews and checks | GitHub / CI |
| Commit-bound code context | RepoGround |
| System identity and stable ecosystem relations | Systemkatalog |
| Display and operator orientation | Leitstand |

Reposkop does not authorize effects. `effect_authorized` remains fixed to `false` because observing a state transition is different from permitting one.

## Artifacts

### Checkout observation v2

A checkout observation binds:

- resolved target, Git directory and common-directory paths;
- filesystem device and inode identities;
- normalized remote repository identity;
- checkout role and purpose;
- repository and checkout identity digests;
- HEAD, branch, upstream and dirty-state digest;
- active Git operation markers such as rebase, merge or cherry-pick.

### Checkout transition v1

A transition embeds validated before and after observations, compares identity and state fields, and emits stable reason codes such as:

- `identity.checkout_break`
- `identity.remote_changed`
- `continuity.head_changed`
- `continuity.status_changed`
- `continuity.operation_state_changed`

### Checkout continuity v1

Continuity classifies a transition as:

- `intact`
- `explainable_drift`
- `identity_break`
- `inconclusive`

### Shadow transition v1

A self-contained shadow transition embeds validated continuity evidence (including its transition
and captured before/after observations) and exposes their canonical digests. Its
`local_identity_continuity` result is only
`continuous`, `broken` or `could_not_be_established`; it never decides whether an operation was
allowed.

### Shadow value assessment v1

A shadow value assessment embeds one validated shadow transition and compares the same four-field
non-authoritative baseline used by the falsification harness: path, branch, HEAD and Git common-dir
path. It classifies the local result as `unique_identity_signal`, `baseline_visible_change`,
`no_identity_break` or `inconclusive`. The artifact deliberately does not claim materiality, recovery
value, wrong-checkout prevention or effect permission.

### Shadow value set v1

A shadow value set aggregates an explicit, purpose-bound list of at most 128 validated shadow value
assessments. Assessments are canonicalized by digest and summarized only by the four local
differential classifications plus their observation window. The set never truncates silently and
rejects duplicate digests or mixed purposes. Consumer outcome truth, evidence sufficiency and any
retain/migrate/retire decision remain outside Reposkop.

## Commands

```text
reposkop inspect <path> [--role <role>] [--purpose <purpose>] --json
reposkop transition <path> --before <observation.json> [--role <role>] [--purpose <purpose>] --json
reposkop continuity <path> --expected <observation.json> [--role <role>] [--purpose <purpose>] --json
reposkop shadow --before <observation.json> --after <observation.json> --json
reposkop shadow-value --shadow <shadow.json> --json
reposkop shadow-value-set --purpose <purpose> --assessment <assessment.json> [--assessment <assessment.json> ...] --json
reposkop report <path> [--role <role>] [--purpose <purpose>] [--lifecycle-evidence <file>] --json
reposkop project <observation.json> [--lifecycle-evidence <file>] --json
reposkop inventory --config <explicit-targets.json> --json
reposkop validate <artifact.json> --json
```

There is no implicit filesystem discovery. Inventory observes only explicitly configured targets.

## Required operator integration

Risk-bearing repository operations should bind a Reposkop observation before the effect and a transition after it:

```text
Reposkop observation
        ↓
Grabowski effect
        ↓
Reposkop transition / continuity
        ↓
Grabowski receipt binds all artifact digests
```

This applies especially to interrupted-work resumption, branch or rebase operations, pushes, merges, deployment source selection, and worktree archival or removal.

Read-only repository inspection does not require this lifecycle.

## Validation

```text
make deploy-check
```

See [Checkout identity and transition plan](docs/checkout-identity-transition-plan.md),
[Differential value-falsification plan](docs/value-falsification.md) and
[Architecture](docs/architecture.md).
