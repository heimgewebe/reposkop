from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .schema_validation import validate_artifact
from .timeutil import parse_utc, utc_now

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_KEYS = ("tasks", "leases", "processes", "tmux", "pull_requests")
_MAX_ARTIFACT_BYTES = 2_000_000
_MAX_EVIDENCE_TTL = timedelta(minutes=5)


def load_json(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise ValueError(f"artifact cannot be opened safely: {target}: {exc.strerror}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"artifact must be a regular file: {target}")
        if metadata.st_size > _MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds 2 MB bound")
        chunks: list[bytes] = []
        remaining = _MAX_ARTIFACT_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > _MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds 2 MB bound")
    finally:
        os.close(descriptor)
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant is forbidden: {constant}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"artifact is not strict UTF-8 JSON: {target}") from exc
    if not isinstance(value, dict):
        raise TypeError("artifact root must be an object")
    return value


def validate_lifecycle_evidence(value: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    schema_result = validate_artifact(value)
    if not schema_result["valid"]:
        errors.extend(
            f"schema:{error.get('path') or '<root>'}" if isinstance(error, dict) else f"schema:{error}"
            for error in schema_result["errors"]
        )
    if value.get("schema_version") != 1:
        errors.append("schema_version")
    if value.get("kind") != "reposkop_lifecycle_evidence":
        errors.append("kind")
    try:
        captured = parse_utc(value.get("captured_at"))
        expires = parse_utc(value.get("expires_at"))
        if expires <= captured:
            errors.append("expires_at_not_after_captured_at")
        if expires - captured > _MAX_EVIDENCE_TTL:
            errors.append("evidence_ttl_exceeds_5_minutes")
        if captured > datetime.now(timezone.utc):
            errors.append("captured_at_in_future")
    except (TypeError, ValueError):
        captured = expires = None
        errors.append("timestamps")
    subject = value.get("subject")
    if not isinstance(subject, dict) or not isinstance(subject.get("path"), str):
        errors.append("subject")
    sources = value.get("sources")
    lifecycle_authority_present = False
    if not isinstance(sources, list) or not sources:
        errors.append("sources")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"sources[{index}]")
                continue
            if not all(isinstance(source.get(key), str) and source.get(key) for key in ("authority", "source_ref", "observed_at")):
                errors.append(f"sources[{index}].identity")
            if source.get("authority") in {"grabowski", "bureau"}:
                lifecycle_authority_present = True
            try:
                source_observed = parse_utc(source.get("observed_at"))
                if captured is not None and source_observed > captured:
                    errors.append(f"sources[{index}].observed_after_capture")
                if source_observed > datetime.now(timezone.utc):
                    errors.append(f"sources[{index}].observed_in_future")
            except (TypeError, ValueError):
                errors.append(f"sources[{index}].observed_at")
            if _SHA_RE.fullmatch(str(source.get("sha256", ""))) is None:
                errors.append(f"sources[{index}].sha256")
    if isinstance(sources, list) and sources and not lifecycle_authority_present:
        errors.append("lifecycle_authority_missing")
    bindings = value.get("bindings", {})
    if not isinstance(bindings, dict):
        errors.append("bindings")
    else:
        unknown = set(bindings) - set(_BINDING_KEYS)
        if unknown:
            errors.append("bindings_unknown_keys")
        for key in _BINDING_KEYS:
            if key in bindings and not isinstance(bindings[key], list):
                errors.append(f"bindings.{key}")
    lifecycle = value.get("lifecycle")
    if not isinstance(lifecycle, dict) or not isinstance(lifecycle.get("status"), str):
        errors.append("lifecycle")

    now = datetime.now(timezone.utc)
    freshness = "unknown"
    if captured is not None and expires is not None:
        freshness = "fresh" if captured <= now <= expires else "stale"
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "freshness": freshness,
        "evidence_sha256": sha256_json(value),
        "validated_at": utc_now(),
    }


def subject_matches(observation: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, list[str]]:
    subject = evidence.get("subject", {})
    identities = observation.get("identities", {})
    mismatches: list[str] = []
    observed_path = identities.get("path") or observation.get("target", {}).get("path")
    if subject.get("path") != observed_path:
        mismatches.append("path")
    for key in ("git_common_dir", "remote"):
        expected = subject.get(key)
        if expected is not None and expected != identities.get(key):
            mismatches.append(key)
    expected_head = subject.get("head")
    if expected_head is not None and expected_head != observation.get("git", {}).get("head"):
        mismatches.append("head")
    expected_role = subject.get("role")
    if expected_role is not None and expected_role != observation.get("role", {}).get("value"):
        mismatches.append("role")
    return not mismatches, mismatches
