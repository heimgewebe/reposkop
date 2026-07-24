from __future__ import annotations

from pathlib import Path

from .model import CheckoutRole, ROLE_VALUES


def classify_role(
    *,
    path: Path,
    git_dir: Path | None,
    git_common_dir: Path | None,
    explicit_role: str | None = None,
) -> tuple[str, list[str]]:
    if explicit_role is not None:
        if explicit_role not in ROLE_VALUES:
            raise ValueError(f"unsupported checkout role: {explicit_role}")
        return explicit_role, ["explicit_role"]

    text = str(path)
    if "/.repoground-sources/" in text or text.endswith("/.repoground-sources"):
        return CheckoutRole.MANAGED_REPOGROUND_SOURCE.value, ["path:.repoground-sources"]
    if "/.repobrief-sources/" in text or text.endswith("/.repobrief-sources"):
        return CheckoutRole.LEGACY_REPOBRIEF_SOURCE.value, ["path:.repobrief-sources"]
    if "/.local/share/grabowski/worktrees/" in text:
        return CheckoutRole.GRABOWSKI_WORKSPACE.value, ["path:grabowski-workspace"]
    if "/.grabowski-worktrees/" in text:
        return CheckoutRole.GRABOWSKI_LIFECYCLE_WORKTREE.value, ["path:.grabowski-worktrees"]
    if git_dir is not None and git_common_dir is not None:
        if git_dir != git_common_dir and "worktrees" in git_dir.parts:
            return CheckoutRole.LINKED_WORKTREE.value, ["git_dir:linked-worktree"]
        if (path / ".git").is_dir():
            return CheckoutRole.CANONICAL_CHECKOUT.value, ["git_marker:directory"]
        if (path / ".git").is_file():
            return CheckoutRole.LINKED_WORKTREE.value, ["git_marker:file"]
        return CheckoutRole.AUXILIARY_CLONE.value, ["git_identity:independent"]

    return CheckoutRole.UNKNOWN.value, ["insufficient_git_identity"]
