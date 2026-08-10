# Reposkop CLI

Reposkop exposes only target-bound, deterministic, read-only repository and checkout coherence commands.

## Canonical commands

```text
python -m reposkop inspect <path> --json
python -m reposkop shadow --before <observation.json> --after <observation.json> --json
python -m reposkop shadow-value --shadow <shadow.json> --json
python -m reposkop shadow-value-set --purpose <purpose> --assessment <assessment.json> [--assessment <assessment.json> ...] --json
python -m reposkop report <path> --json
python -m reposkop project <observation.json> --json
python -m reposkop inventory --config <explicit-targets.json> --json
python -m reposkop validate <artifact.json> --json
```

`inspect` and `report` require one explicit repository or checkout path. `inventory` accepts only an explicit bounded target list. Reposkop performs no implicit filesystem discovery and no global repository scan.

`shadow` summarizes two separately captured observations. It reports only whether local checkout
identity stayed continuous, broke or could not be established; it does not evaluate operation
intent or permission. `shadow-value` classifies one validated shadow transition against the
non-authoritative four-field baseline. `shadow-value-set` accepts only an explicit list of 1..128
validated assessments with the same exact purpose, rejects duplicate digests, canonicalizes their
order and summarizes only Reposkop's four local differential classifications plus the observation
window. It does not establish materiality, evidence sufficiency or a retention decision.

## Authority boundary

Reposkop may observe local Git and checkout state and derive a local coherence projection. Supplied
lifecycle evidence and its gaps remain separately labeled foreign-authority descriptions; they do
not select local coherence posture. Reposkop does not establish task truth, merge permission,
runtime authority or effect authorization. Every report keeps `effect_authorized` fixed to `false`.

Reposkop never fetches, pulls, checks out branches, pushes, deletes, cleans up, dispatches tasks or changes host state.

## Transitional Steuerboard adapter

The historical `steuerboard` executable is retained temporarily for exactly two read-only translations:

```text
python -m steuerboard observe repo <path> --json
python -m steuerboard operator report --repo <path> --json
```

All former inventory discovery, favorites, branch-drift, assessment, planning, approval, action, remote-refresh, runbook, network and service-gate commands fail closed with a migration message. They are not simulated under the Reposkop name.

The canonical repository is `https://github.com/heimgewebe/reposkop`. The former GitHub repository path is redirect compatibility only.
