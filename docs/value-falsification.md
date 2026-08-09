# Differential value-falsification plan

Status: normative retention criterion for the standalone Reposkop component.

## Hypothesis under test

Reposkop's unique value is local checkout identity continuity that is not established by ordinary
resolved-path, branch, HEAD and Git common-directory-path guards. The inode-bound target, Git
directory and common-directory identities plus normalized remote identity must find material
checkout substitutions that those simpler fields miss.

Reposkop is not a second Grabowski or RepoGround. This plan does not model writer path policy,
effect permission, task or lease truth, pull-request state, deployment authority, commit-bound
context or remote freshness.

## Differential baseline

`tests/test_differential_identity.py` contains a deliberately small baseline with exactly four
fields:

- resolved checkout path;
- current branch;
- HEAD object ID;
- resolved Git common-directory path.

This is a **non-authoritative differential baseline**, not imported Grabowski code and not a claim
about Grabowski's current or future guards. Its only purpose is to make the additional detection
claim falsifiable.

## Deterministic fault matrix

| Injected case | Baseline result | Exact Reposkop result | Value classification |
| --- | --- | --- | --- |
| Replace the checkout at the same path with a second clone of the same source, preserving branch, HEAD, common-dir path and remote | No changed baseline field | `same_repository_different_checkout`; `identity.checkout_changed`; anomaly `identity.checkout_break`; continuity `identity_break` | Intended unique value: target/Git-dir/common-dir filesystem identities change |
| Replace Git metadata behind an unchanged `.git` redirection and unchanged resolved Git-dir/common-dir path | No changed baseline field | `same_repository_different_checkout`; `identity.checkout_changed`; anomaly `identity.checkout_break`; continuity `identity_break` | Intended unique value: Git-dir/common-dir filesystem identities change |
| Redirect `.git` from one metadata path to another | `git_common_dir` changes | `same_repository_different_checkout`; Git-dir/common-dir and checkout reason codes; anomaly `identity.checkout_break` | Generic Git drift already covered by the modeled baseline |
| Substitute normalized `origin` identity while path, branch, HEAD and common-dir path remain fixed | No changed baseline field | `different_repository`; remote/repository/checkout reason codes; checkout and repository break anomalies; continuity `identity_break` | Intended unique value: remote identity is local repository-lineage evidence |
| Replace the target with a different repository that has the same branch and clean state but a different HEAD and remote | `head` changes | `different_repository`; HEAD plus remote/repository/checkout reason codes; checkout and repository break anomalies | Generic Git drift already covered by the modeled baseline |
| Modify a tracked file without changing checkout identity | No changed baseline field | `same_checkout`; dirty/status reason codes; no anomaly; continuity `explainable_drift` | Negative control: state drift must not be promoted to identity break |

Every case asserts complete and schema-valid before/after observations, exact baseline field deltas,
exact transition reason/anomaly codes, exact continuity state/reasons, and the self-contained shadow result.
The test uses real temporary Git repositories and filesystem replacement/redirection; it does not
mock Reposkop identity material.

## Real shadow transitions

Consumers can capture operation-agnostic observations on either side of any interval:

```text
reposkop inspect /path/to/checkout --purpose shadow --json > before.json
# time or externally owned activity passes; Reposkop does not authorize it
reposkop inspect /path/to/checkout --purpose shadow --json > after.json
reposkop shadow --before before.json --after after.json --json > shadow.json
```

The shadow artifact embeds validated continuity evidence, which recursively carries the transition
and both captured observations. It also exposes canonical observation, repository-identity,
checkout-identity, transition, continuity and shadow digests; continuity state; exact reason/anomaly
codes; and only the tri-state local identity flag `continuous`, `broken` or
`could_not_be_established`. Validation recomputes those derived claims from the embedded sources. It
has no operation permission result.

For each validated shadow receipt, Reposkop can now emit a self-contained differential assessment:

```text
reposkop shadow-value --shadow shadow.json --json > shadow-value.json
```

The assessment compares only the four documented baseline fields and reports one of
`unique_identity_signal`, `baseline_visible_change`, `no_identity_break` or `inconclusive`. Its
validation recomputes the field deltas and classification from the embedded shadow observations.
This closes the local measurement gap without importing consumer semantics: materiality, recovery
improvement and wrong-checkout prevention remain external evidence.

Aggregate only bounded, purpose-bound shadow receipts. Evaluate whether identity breaks were
material, whether the simpler baseline would have missed them, and whether they improved recovery
or prevented a wrong-checkout action. Ordinary HEAD/branch/common-dir drift is not unique value.

## Falsification criterion

The standalone component's value hypothesis is falsified if targeted identity-substitution fault
injection **and** sufficient real consumer shadow transitions fail to find material cases uniquely
detected by Reposkop. If falsified, Reposkop should be considered for migration into Grabowski as a
small observation library or retirement. It must not respond by adding writer path policy,
task/lease/PR/deployment authority, remote-freshness authority, a policy DSL, global discovery, or
effect execution.

The deterministic harness currently establishes synthetic differential cases; it does not by
itself satisfy the real-transition evidence requirement for retaining a standalone component.
