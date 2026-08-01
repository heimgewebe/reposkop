# Automation decision

## Required event-bound automation

### Risk-bearing repository transition

Grabowski should capture a Reposkop observation before a branch, rebase, push, merge, deployment-source or worktree-lifecycle effect. After the effect it should derive transition and continuity artifacts and bind their digests to the effect receipt.

### Interrupted-work resume

Before resuming durable or abandoned work, the consumer should compare the last bound observation with the current target. `identity_break` requires recovery or rerouting; `inconclusive` requires fresh authority reads rather than silent adoption.

### Lifecycle readback

After Grabowski creates, archives or removes a worktree, Reposkop should derive the target-bound post-state and transition. Reposkop records the local identity result; Grabowski remains responsible for the effect and its authorization.

### Leitstand anomaly publication

Identity breaks, incomplete observations and unresolved transitions may be published to Leitstand. Publication should be delta-based and deduplicated by artifact digest.

## Optional automation

A bounded explicit inventory may be used for a named target set when an operator needs portfolio-level orientation. It must not become an implicit home or fleet scan.

## Rejected automation

- permanent Reposkop daemon;
- implicit full-home or full-fleet discovery;
- unconditional scheduled full scans;
- global stop semantics;
- cleanup or repair execution;
- task creation without Bureau assessment;
- effect approval derived from Reposkop state;
- notifications when the relevant artifact digest has not changed.

## Availability rule

A Reposkop failure blocks only the risk-bearing operation that requires checkout identity continuity. It must not pause unrelated repositories, read-only investigation or the global operator queue.
