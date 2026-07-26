# Integration contract

## Grabowski

Grabowski may invoke Reposkop for a specific target before a repository- or checkout-sensitive operation. The report is context only. Grabowski must independently and freshly verify:

- current HEAD and dirty state;
- tasks and lifecycle status;
- leases and resource ownership;
- processes and tmux bindings;
- GitHub pull requests and checks;
- recovery and rollback;
- exact effect authorization.

Reposkop never emits an executable command or approval token.

## Bureau

Bureau may supply task and lifecycle evidence through a versioned evidence envelope. Reposkop does not read or mutate Bureau's private database and does not infer queue or completion truth from filesystem names.

## RepoGround

RepoGround source checkouts are classified as managed sources and retained by default. Reposkop does not scan, refresh, publish or prune RepoGround bundles.

## Systemkatalog

Systemkatalog owns the stable identity and relationship entry for Reposkop. It must describe Reposkop as `repository_observation_readiness`, not as an operator, gate or truth store.

## Leitstand

Leitstand may render a source-bound Reposkop report. It must show capture time, target, source freshness, projection reasons and the explicit `effect_authorized: false` boundary. It must not add action controls backed only by a Reposkop report.
