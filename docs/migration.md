# Migration from Steuerboard to Reposkop

## Repository cutover

The GitHub repository rename was completed on 2026-07-26:

- former canonical identity: `heimgewebe/steuerboard`
- canonical identity: `heimgewebe/reposkop`
- preserved GitHub repository ID: `1232573747`
- default branch: `main`

The former GitHub path may redirect to Reposkop, but redirects are compatibility only. Active configuration, documentation, manifests, bundles and adapters must use `heimgewebe/reposkop` and the canonical local checkout `${HOME}/repos/reposkop`.

## Consumer migration

Active consumers must use one of the bounded Reposkop commands:

```text
reposkop inspect <path> --json
reposkop report <path> --json
```

Global discovery, favorites, branch-drift simulation, action recommendations, mutation and effect authorization are not Reposkop surfaces. Consumers that formerly depended on those Steuerboard commands must migrate to the system that owns the corresponding truth or effect.

## Transitional compatibility

The `steuerboard` CLI remains for one bounded compatibility window and supports only:

```text
steuerboard observe repo <path> --json
steuerboard operator report --repo <path> --json
```

Every other legacy command fails closed with a migration message. The adapter may be removed only after a fresh system-wide consumer readback proves that no active caller still depends on it.

## Historical evidence

Historical receipts, audits, schemas, archived documentation and frozen artifacts keep their original Steuerboard bytes and names. Current documentation may identify Steuerboard as the historical predecessor of Reposkop, but must not rewrite hash-bound evidence.
