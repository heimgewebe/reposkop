# Automation decision

## Accepted automations

### Event-bound target report

A typed Grabowski grip may request one Reposkop report for the exact repository or checkout it is about to inspect. The report is bounded by target, time and output size and cannot block unrelated work globally.

### Lifecycle projection refresh

After Grabowski creates, archives or removes a worktree, it may emit fresh lifecycle evidence and request a new Reposkop projection for that same target. The post-effect report is a readback aid, not the effect receipt itself.

### Leitstand advisory publication

A source-bound report may be published to Leitstand after a meaningful state transition. Publication should be delta-based and deduplicated by report digest.

## Rejected automations

- permanent Reposkop daemon;
- implicit full-home or full-fleet discovery;
- mandatory global preflight for every operator action;
- scheduled unconditional full scan;
- cleanup scheduler or repair executor;
- independent notifications based only on branch-count thresholds;
- task creation without Bureau candidate assessment.

## Conditional future option

A low-frequency, delta-only explicit inventory can be considered after real usage proves that event-bound reports miss material drift. It must have a fixed target list, runtime and output budgets, no effects, no global stop semantics, and no notification when the digest is unchanged.
