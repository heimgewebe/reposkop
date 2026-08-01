# Integration contract

## Grabowski

Grabowski must use Reposkop for checkout identity at risk-bearing repository transitions.

Required sequence:

1. capture a purpose-bound checkout observation;
2. bind `observation_sha256`, `repository_identity_sha256` and `checkout_identity_sha256` to the operation;
3. execute the effect under Grabowski authority;
4. derive a transition and continuity artifact from the current target;
5. bind `transition_sha256` and `continuity_sha256` to the final effect receipt.

`identity_break` blocks continuation until Grabowski performs explicit recovery. `inconclusive` cannot be silently replaced with a new expected identity.

Grabowski must still independently read task, lease, process, GitHub and effect authority. Reposkop does not grant permission to mutate.

## Bureau

Bureau may bind Reposkop digest references into repository-scoped task evidence. It remains authoritative for task, claim, queue and completion truth and must not infer completion from checkout continuity.

Recommended evidence fields:

- expected checkout observation digest;
- pre-effect observation digest;
- post-effect observation digest;
- transition digest;
- continuity digest.

## Chronik

Chronik should record digest references, operation identity and continuity state. It should not duplicate the complete Reposkop payload unless required for an immutable external archive.

## RepoGround

RepoGround source bundles may bind the observation digest and checkout identity digest of the local source used to generate the bundle. RepoGround remains authoritative for commit-bound code context; Reposkop is authoritative for local checkout identity.

## Systemkatalog

Systemkatalog owns the stable component identity and relationship entry for Reposkop. It should describe Reposkop as `checkout_identity_transition_authority`.

## Leitstand

Leitstand should render actionable signals rather than raw reports:

- identity or repository break;
- purpose or role change;
- incomplete or invalid observation;
- active Git operation during resume or mutation;
- missing post-effect transition.

Leitstand must not add mutation controls backed only by Reposkop artifacts.
