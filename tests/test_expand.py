"""
Tests for OData $expand query parameter support.

Tests:
- test_expand_users_memberof — /users?$expand=memberOf expands memberOf relation
- test_expand_me_authentication — /me?$expand=authentication expands authentication
- test_expand_directory_roles_members — /directoryRoles?$expand=members expands members
- test_expand_wildcard — /users?$expand=* expands all known relations
- test_expand_unknown_field_graceful — /users?$expand=nonexistent returns normal data gracefully
- test_expand_with_filter — /users?$expand=memberOf&$filter=... combines both
- test_expand_with_top — /users?$expand=memberOf&$top=1 returns 1 user with expand
- test_expand_empty_relation — expanding a relation that maps to empty fixture returns empty array
"""

import pytest
import httpx


class TestExpandBasics:
    """Basic $expand functionality tests."""

    def test_expand_users_memberof(self, mock_server, auth_headers):
        """GET /users?$expand=memberOf adds memberOf property to each user."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

        # Each user should have memberOf key (expanded property)
        for user in data["value"]:
            assert "memberOf" in user
            # memberOf should be the expanded array from groups fixture
            # It's returned as the value array directly (not wrapped in a dict)
            assert isinstance(user["memberOf"], list)
            # Groups fixture is empty in greenfield
            assert len(user["memberOf"]) == 0

    def test_expand_me_authentication(self, mock_server, auth_headers):
        """GET /me?$expand=authentication returns me with authentication property."""
        response = httpx.get(
            f"{mock_server}/v1.0/me?$expand=authentication",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # me endpoint returns singleton (no value key)
        assert "displayName" in data
        assert "id" in data
        # authentication must be expanded from me_auth_methods fixture
        assert "authentication" in data
        assert isinstance(data["authentication"], list)
        assert len(data["authentication"]) > 0

    def test_expand_directory_roles_members(self, mock_server, auth_headers):
        """GET /directoryRoles?$expand=members adds members property to each role."""
        response = httpx.get(
            f"{mock_server}/v1.0/directoryRoles?$expand=members",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) > 0

        # Each role should have members property (expanded)
        for role in data["value"]:
            assert "members" in role
            # members comes from directory_role_members fixture
            # It's returned as the value array directly (same fixture for all roles)
            assert isinstance(role["members"], list)
            # First role (Global Administrator) has 1 member
            if role.get("displayName") == "Global Administrator":
                assert len(role["members"]) == 1
                assert role["members"][0]["displayName"] == "Mike Morris"


class TestExpandWildcard:
    """Test $expand=* expands all known relations."""

    def test_expand_wildcard(self, mock_server, auth_headers):
        """GET /users?$expand=* expands all known relations for users."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=*",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data

        # For users, known relations are memberOf and authentication
        for user in data["value"]:
            # Both relations should be present when using *
            assert "memberOf" in user
            assert "authentication" in user
            # Both should be arrays (value array directly, not wrapped)
            assert isinstance(user["memberOf"], list)
            assert isinstance(user["authentication"], list)
            # memberOf should be empty (groups fixture is empty)
            assert len(user["memberOf"]) == 0
            # authentication should have items
            assert len(user["authentication"]) > 0


class TestExpandGracefulHandling:
    """Test graceful handling of edge cases."""

    def test_expand_unknown_field_graceful(self, mock_server, auth_headers):
        """GET /users?$expand=nonexistent returns normal data, logs warning, no error."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=nonexistent",
            headers=auth_headers,
        )
        # Should not error - gracefully skipped
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

        # Should not have the nonexistent property added
        for user in data["value"]:
            assert "nonexistent" not in user
            # But should still have normal properties
            assert "displayName" in user
            assert "id" in user

    def test_expand_empty_relation(self, mock_server, auth_headers):
        """Expanding a relation that maps to empty fixture returns empty array."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # groups fixture is empty in greenfield
        for user in data["value"]:
            assert "memberOf" in user
            # Should have empty array (not wrapped in dict)
            assert isinstance(user["memberOf"], list)
            assert len(user["memberOf"]) == 0


class TestExpandCombinations:
    """Test $expand combined with other query parameters."""

    def test_expand_with_filter(self, mock_server, auth_headers):
        """GET /users?$expand=memberOf&$filter=userType eq 'Member' combines both."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf&$filter=userType eq 'Member'",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Filter applied: both users are Members, so should get 2
        assert "value" in data
        assert len(data["value"]) == 2

        # Expand applied: each should have memberOf
        for user in data["value"]:
            assert user["userType"] == "Member"
            assert "memberOf" in user
            assert isinstance(user["memberOf"], list)

    def test_expand_with_top(self, mock_server, auth_headers):
        """GET /users?$expand=memberOf&$top=1 returns 1 user with expand."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf&$top=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Top applied: should have only 1 user
        assert "value" in data
        assert len(data["value"]) == 1

        # Expand applied: the returned user should have memberOf
        user = data["value"][0]
        assert "memberOf" in user
        assert isinstance(user["memberOf"], list)


class TestExpandMultipleFields:
    """Test expanding multiple fields at once."""

    def test_expand_multiple_fields_comma_separated(self, mock_server, auth_headers):
        """GET /users?$expand=memberOf,authentication expands both fields."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf,authentication",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data

        # Both expansions should be applied
        for user in data["value"]:
            assert "memberOf" in user
            assert "authentication" in user
            # Both should be arrays (value arrays directly)
            assert isinstance(user["memberOf"], list)
            assert isinstance(user["authentication"], list)
            # memberOf is empty, authentication has items
            assert len(user["memberOf"]) == 0
            assert len(user["authentication"]) > 0

    def test_expand_mixed_valid_and_invalid(self, mock_server, auth_headers):
        """GET /users?$expand=memberOf,invalid,authentication handles gracefully."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?$expand=memberOf,invalid,authentication",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data

        # Valid fields should be expanded, invalid should be skipped
        for user in data["value"]:
            assert "memberOf" in user
            assert "authentication" in user
            assert "invalid" not in user
            # Both valid expansions should be arrays
            assert isinstance(user["memberOf"], list)
            assert isinstance(user["authentication"], list)
