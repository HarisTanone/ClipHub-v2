"""Unit tests for Role-Based Access Control (RBAC) and permissions system."""
import pytest
from src.infrastructure.auth import (
    has_permission,
    has_any_permission,
    has_all_permissions,
    is_superadmin,
)
from src.presentation.auth_deps import CurrentUser


def test_superadmin_bypasses_all_permissions():
    assert has_permission("superadmin", [], "any:permission") is True
    assert has_permission("superadmin", [], "jobs:create") is True
    assert has_any_permission("superadmin", [], "a", "b") is True
    assert has_all_permissions("superadmin", [], "a", "b") is True


def test_wildcard_asterisk_matches_everything():
    assert has_permission("custom", ["*"], "jobs:create") is True
    assert has_permission("custom", ["*"], "system:testing") is True
    assert has_permission("custom", ["system:admin"], "anything:else") is True


def test_scope_wildcards():
    perms = ["jobs:*", "styles:read"]
    assert has_permission("editor", perms, "jobs:create") is True
    assert has_permission("editor", perms, "jobs:read") is True
    assert has_permission("editor", perms, "jobs:delete") is True
    assert has_permission("editor", perms, "jobs:update") is True
    assert has_permission("editor", perms, "styles:read") is True
    assert has_permission("editor", perms, "styles:delete") is False
    assert has_permission("editor", perms, "users:create") is False


def test_exact_permissions():
    perms = ["jobs:read", "jobs:export"]
    assert has_permission("viewer", perms, "jobs:read") is True
    assert has_permission("viewer", perms, "jobs:export") is True
    assert has_permission("viewer", perms, "jobs:create") is False
    assert has_permission("viewer", perms, "jobs:delete") is False


def test_has_any_permission():
    perms = ["jobs:read", "social:read"]
    assert has_any_permission("user", perms, "jobs:create", "jobs:read") is True
    assert has_any_permission("user", perms, "users:create", "roles:create") is False


def test_has_all_permissions():
    perms = ["jobs:read", "jobs:create"]
    assert has_all_permissions("user", perms, "jobs:read", "jobs:create") is True
    assert has_all_permissions("user", perms, "jobs:read", "jobs:delete") is False


def test_current_user_object():
    user = CurrentUser(user_id=10, email="test@example.com", role="editor", permissions=["jobs:*"])
    assert user.is_superadmin is False
    assert user.has_perm("jobs:create") is True
    assert user.has_perm("jobs:delete") is True
    assert user.has_perm("users:create") is False

    admin = CurrentUser(user_id=1, email="admin@example.com", role="superadmin", permissions=[])
    assert admin.is_superadmin is True
    assert admin.has_perm("anything") is True
