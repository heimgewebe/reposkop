from __future__ import annotations

from enum import Enum


class CheckoutRole(str, Enum):
    CANONICAL_CHECKOUT = "canonical_checkout"
    LINKED_WORKTREE = "linked_worktree"
    AUXILIARY_CLONE = "auxiliary_clone"
    MANAGED_REPOGROUND_SOURCE = "managed_repoground_source"
    LEGACY_REPOBRIEF_SOURCE = "legacy_repobrief_source"
    DEPLOYMENT_SOURCE = "deployment_source"
    GRABOWSKI_WORKSPACE = "grabowski_workspace"
    GRABOWSKI_LIFECYCLE_WORKTREE = "grabowski_lifecycle_worktree"
    UNKNOWN = "unknown"


class ProjectionState(str, Enum):
    MANAGED_RETAIN = "managed_retain"
    PROTECTED_ACTIVE = "protected_active"
    DIRTY_PRESERVE = "dirty_preserve"
    REMOVE_CANDIDATE = "remove_candidate"
    ARCHIVE_THEN_REMOVE = "archive_then_remove"
    INCONCLUSIVE = "inconclusive"


MANAGED_ROLES = {
    CheckoutRole.MANAGED_REPOGROUND_SOURCE.value,
    CheckoutRole.DEPLOYMENT_SOURCE.value,
    CheckoutRole.GRABOWSKI_WORKSPACE.value,
}

ROLE_VALUES = tuple(role.value for role in CheckoutRole)
STATE_VALUES = tuple(state.value for state in ProjectionState)
