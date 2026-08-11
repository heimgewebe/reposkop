# Reposkop architecture

Status: normative for Reposkop 2.0.

## System responsibility

Reposkop owns the canonical representation of local checkout identity and the canonical comparison of bound checkout observations.

It has five layers:

1. **Target binding** — exactly one explicit path and purpose.
2. **Observation** — fixed read-only Git and filesystem probes.
3. **Identity derivation** — repository and checkout identity digests from normalized, source-bound material.
4. **Transition derivation** — deterministic before/after comparison with stable reason and anomaly codes.
5. **Continuity classification** — `intact`, `explainable_drift`, `identity_break` or `inconclusive`.

The result is authoritative inside this domain. Reposkop does not own task, lease, pull-request, remote-freshness or effect truth.

## Identity axes

Reposkop keeps these identities separate:

- selected target path and purpose;
- resolved Git toplevel;
- Git directory;
- Git common directory;
- filesystem device and inode for each bound directory;
- normalized remote repository identity;
- checkout role;
- repository identity digest;
- checkout identity digest.

The repository identity represents the repository lineage available locally. A normalized remote is preferred when present; otherwise the Git common-directory identity is used.

The checkout identity represents one exact local working checkout. It binds path, Git directory, common directory, role and purpose. HEAD and dirty state are deliberately excluded so that legitimate work changes state without changing checkout identity.

## State axes

Dynamic state includes:

- HEAD and branch;
- detached state;
- upstream and locally available ahead/behind counts;
- dirty, staged, unstaged and untracked indicators;
- a SHA-256 digest of the byte-exact Porcelain v1 `-z` status representation (the normal
  observation derives those compatibility bytes from its combined Porcelain v2 probe);
- active rebase, merge, cherry-pick, revert, bisect or sequencer markers;
- alternates and `.gitmodules` presence.

These fields belong to transition and continuity comparison, not checkout identity.

## Artifact contracts

### Checkout observation v2

The observation is a canonical, digest-bound statement about one local target at one time. It is authoritative for the material it contains and explicitly does not establish remote freshness or external lifecycle truth.

### Checkout transition v1

The transition embeds and validates before and after observations. It compares identity and state fields and emits stable reason codes. Identity discontinuities are also emitted as anomaly codes.

### Checkout continuity v1

Continuity is derived only from a validated transition:

- `intact`: same checkout identity and no tracked state change;
- `explainable_drift`: same checkout identity with tracked local state changes;
- `identity_break`: checkout or repository identity changed;
- `inconclusive`: an observation or transition is invalid or incomplete.

### Shadow transition v1

The shadow artifact is a self-contained, operation-agnostic summary derived from two captured
observations. It embeds validated continuity evidence, which recursively carries the transition and
source observations, and exposes canonical source/transition/continuity digests, continuity state,
reason/anomaly codes and a tri-state local identity result. Validation recomputes the derived claims
from those embedded sources. It does not contain an operation permission decision.

### Coherence projection v2

Projection state is local-only. A valid, complete Git observation produces `local_coherent` even
when lifecycle evidence is missing, invalid, stale or subject-mismatched. Those conditions are
preserved separately in `foreign_authority_gaps`; supplied active bindings remain descriptive.
`local_coherent` means that local checkout observation was established, not that the tree is clean,
an operation is safe, or an effect is authorized. Invalid or incomplete local Git observation
remains `inconclusive`.

Legacy lifecycle-oriented projection states remain schema-valid for persisted artifacts, but the
current projector does not derive cleanup, archive or protection decisions from foreign evidence.
The boundary correction is versioned additively as projection v2 and coherence report v3; v1/v2
report artifacts and projection v1 remain valid historical inputs.

## Authority boundary

| Concern | Authority |
| --- | --- |
| Checkout identity, local transition and continuity | Reposkop |
| Task, claim, queue and completion | Bureau |
| Local effects, leases, processes and worktree lifecycle | Grabowski |
| Pull request, review and check state | GitHub / CI |
| Commit-bound code context | RepoGround |
| Stable system identity and relationships | Systemkatalog |
| Presentation and orientation | Leitstand |

`effect_authorized` remains false in Reposkop artifacts. This is not a statement that Reposkop lacks authority in its own domain. It states that observation authority is not effect permission.

## Failure semantics

- Invalid or incomplete observations produce `inconclusive` continuity.
- A changed checkout identity produces `identity_break` even when the repository identity remains equal.
- A changed repository identity produces both checkout and repository break anomalies.
- A consumer must not silently replace an expected observation with a fresh one after an identity break.
- Reposkop failure blocks only the risk-bearing operation that requires checkout identity; unrelated reads and other repositories continue.
- Missing or stale task, lifecycle, pull-request or remote-freshness authority is not a local
  checkout-integrity failure.

## Automation policy

Accepted automation is event-bound:

- pre-effect observation;
- post-effect transition and continuity derivation;
- interrupted-work resume checks;
- delta-only publication of anomalies to Leitstand;
- digest references in Grabowski, Bureau, Chronik and RepoGround artifacts.

Rejected automation:

- permanent daemon;
- implicit home or fleet discovery;
- unconditional scheduled full scans;
- global stop semantics;
- cleanup or repair execution;
- task creation without Bureau assessment;
- action approval derived only from Reposkop state.

## Standalone retention criterion

The component remains standalone only while targeted fault injection and real shadow transitions
demonstrate material identity substitutions uniquely detected by Reposkop. If they do not, prefer
library migration into Grabowski or retirement over scope expansion. See
[Differential value-falsification plan](value-falsification.md).
