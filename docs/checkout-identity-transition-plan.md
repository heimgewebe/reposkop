# Checkout identity and transition plan

Status: implementation contract for Reposkop 2.0.

## Goal

Make Reposkop indispensable through a unique, narrow responsibility: canonical local checkout identity, transition and continuity truth.

Reposkop must not become a second task store, GitHub observer, effect engine or UI. Its value is that every risk-bearing repository operation can prove which checkout it started from, whether that identity remained continuous, and what local state changed.

## Implemented in Reposkop 2.0

- checkout observation schema v2;
- filesystem device and inode binding for target, Git directory and common directory;
- stable repository and checkout identity digests;
- dirty-state digest and active Git operation markers;
- checkout transition artifact with stable reason and anomaly codes;
- checkout continuity classification;
- version-aware artifact validation;
- CLI commands for transition and continuity;
- removal of the legacy `steuerboard` package entrypoint from the distributed product.

## Required consumer cutover

### Grabowski

For risk-bearing operations:

1. capture a purpose-bound Reposkop observation;
2. bind its digest to the operation receipt or durable task record;
3. execute the effect under Grabowski authority;
4. capture the current checkout state;
5. create a Reposkop transition and continuity artifact;
6. bind their digests to the final effect receipt;
7. fail closed on `identity_break`; require explicit recovery on `inconclusive`.

Initial mandatory paths:

- interrupted-work resumption;
- worktree archival and removal;
- branch switch, rebase and merge preparation;
- push and post-push readback;
- deployment source selection.

### Bureau

Repository-bound task evidence should support references to:

- expected checkout observation digest;
- pre-effect observation digest;
- post-effect observation digest;
- transition digest;
- continuity digest.

Bureau remains authoritative for task lifecycle. It must not infer task completion from a Reposkop artifact.

### Chronik

Chronik should record digest references instead of duplicating full Reposkop artifacts. Historical events should be able to answer which checkout identity and transition accompanied an operation.

### RepoGround

A locally generated RepoGround bundle should optionally bind the Reposkop observation digest of its source checkout. RepoGround remains authoritative for commit-bound context, while Reposkop proves the local source identity used to produce it.

### Leitstand

Leitstand should display only actionable Reposkop signals by default:

- checkout identity break;
- repository identity break;
- unexpected purpose or role change;
- active Git operation during resume or mutation;
- incomplete or invalid observation;
- unresolved transition after a risk-bearing effect.

## Admission policy

Reposkop is mandatory only where identity continuity materially affects safety or recovery. It is not required for ordinary reads such as file inspection, `git log`, or repository search.

A Reposkop outage must not block unrelated work. It should block or reroute only the risk-bearing repository operation that requires a trustworthy checkout binding.

## Measurement

Consumers should emit bounded local usage receipts containing:

- consumer and purpose;
- artifact kind and digest;
- latency;
- continuity state;
- anomaly codes;
- whether the operation was replanned or rejected.

After sufficient real usage, mandatory integration points should be retained only where they demonstrably detect drift, improve recovery or prevent identity mistakes.

## Deferred extensions

These are useful but not required for the initial contract:

- ancestry-aware fast-forward, rewind and divergence classification;
- submodule identity digests;
- sparse-checkout definition digest;
- separate index and working-tree content digests;
- remote repository numeric identity supplied by GitHub evidence;
- cross-host checkout identity envelopes.
