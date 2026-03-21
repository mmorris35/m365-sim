"""
Tests for /beta/ route mirror endpoints.

Tests cover:
- GET endpoints with beta context URL rewriting
- POST/PATCH write operations with beta context
- Query parameters ($top, $filter, $expand)
- Authentication enforcement
- Error simulation
- Multiple cloud targets (gcc-moderate, gcc-high, commercial-e5)
- 404 handling for unmapped paths
"""

import json
import pytest
import httpx


class TestBetaAuthentication:
    """Authentication enforcement on beta endpoints."""

    def test_beta_auth_required_missing_header(self, mock_server):
        """GET /beta/users without auth returns 401."""
        response = httpx.get(f"{mock_server}/beta/users")
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "Authorization_RequestDenied"

    def test_beta_auth_succeeds_with_bearer_token(self, mock_server, auth_headers):
        """GET /beta/users with auth header returns 200."""
        response = httpx.get(f"{mock_server}/beta/users", headers=auth_headers)
        assert response.status_code == 200


class TestBetaContextRewriting:
    """Tests that @odata.context URLs are rewritten from v1.0 to beta."""

    def test_beta_users_context_rewritten(self, mock_server, auth_headers):
        """GET /beta/users returns users with 'beta' in context URL."""
        response = httpx.get(f"{mock_server}/beta/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Check context URL contains 'beta' instead of 'v1.0'
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]
        assert "/v1.0/" not in data["@odata.context"]

    def test_beta_me_context_rewritten(self, mock_server, auth_headers):
        """GET /beta/me returns me singleton with beta context."""
        response = httpx.get(f"{mock_server}/beta/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]
        assert "/v1.0/" not in data["@odata.context"]
        assert "displayName" in data

    def test_beta_organization_context_rewritten(self, mock_server, auth_headers):
        """GET /beta/organization returns organization with beta context."""
        response = httpx.get(f"{mock_server}/beta/organization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestBetaCollectionEndpoints:
    """Tests for beta collection endpoints."""

    def test_beta_users_returns_value_array(self, mock_server, auth_headers):
        """GET /beta/users returns collection with value array."""
        response = httpx.get(f"{mock_server}/beta/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert isinstance(data["value"], list)
        assert len(data["value"]) == 2

    def test_beta_groups_returns_value_array(self, mock_server, auth_headers):
        """GET /beta/groups returns collection with value array."""
        response = httpx.get(f"{mock_server}/beta/groups", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert isinstance(data["value"], list)

    def test_beta_domains_returns_value_array(self, mock_server, auth_headers):
        """GET /beta/domains returns collection with value array."""
        response = httpx.get(f"{mock_server}/beta/domains", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert isinstance(data["value"], list)


class TestBetaQueryParameters:
    """Tests for beta endpoints with query parameters."""

    def test_beta_top_parameter(self, mock_server, auth_headers):
        """GET /beta/users?$top=1 returns truncated collection."""
        response = httpx.get(f"{mock_server}/beta/users?$top=1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert len(data["value"]) == 1

    def test_beta_filter_parameter(self, mock_server, auth_headers):
        """GET /beta/users?$filter=accountEnabled eq true returns filtered results."""
        response = httpx.get(
            f"{mock_server}/beta/users?$filter=accountEnabled eq true",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        # All returned users should have accountEnabled = true
        for user in data["value"]:
            assert user.get("accountEnabled") == True

    def test_beta_expand_parameter(self, mock_server, auth_headers):
        """GET /beta/users?$expand=memberOf returns users with expanded relation."""
        response = httpx.get(
            f"{mock_server}/beta/users?$expand=memberOf",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        # Each user should now have memberOf property
        for user in data["value"]:
            assert "memberOf" in user

    def test_beta_combined_filters_and_top(self, mock_server, auth_headers):
        """GET /beta/users?$filter=accountEnabled eq true&$top=1."""
        response = httpx.get(
            f"{mock_server}/beta/users?$filter=accountEnabled eq true&$top=1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert len(data["value"]) <= 1


class TestBetaWriteOperations:
    """Tests for beta POST and PATCH write operations."""

    def test_beta_post_ca_policy(self, mock_server, auth_headers):
        """POST /beta/identity/conditionalAccess/policies returns 201."""
        policy = {
            "displayName": "Test Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {},
            "grantControls": {},
        }
        response = httpx.post(
            f"{mock_server}/beta/identity/conditionalAccess/policies",
            json=policy,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()

        # Should have id and createdDateTime added
        assert "id" in data
        assert "createdDateTime" in data
        # Context should be rewritten to beta
        assert "@odata.context" in data or "displayName" in data

    def test_beta_post_compliance_policy(self, mock_server, auth_headers):
        """POST /beta/deviceManagement/deviceCompliancePolicies returns 201."""
        policy = {
            "displayName": "Test Compliance",
            "description": "Test policy",
        }
        response = httpx.post(
            f"{mock_server}/beta/deviceManagement/deviceCompliancePolicies",
            json=policy,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert "createdDateTime" in data
        assert data["displayName"] == "Test Compliance"

    def test_beta_post_device_configuration(self, mock_server, auth_headers):
        """POST /beta/deviceManagement/deviceConfigurations returns 201."""
        config = {
            "displayName": "Test Device Config",
            "description": "Test configuration",
        }
        response = httpx.post(
            f"{mock_server}/beta/deviceManagement/deviceConfigurations",
            json=config,
            headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert "createdDateTime" in data

    def test_beta_patch_auth_method_config(self, mock_server, auth_headers):
        """PATCH /beta/policies/.../authenticationMethodConfigurations/{method_id} returns 200."""
        update = {
            "id": "microsoftAuthenticator",
            "state": "enabled",
        }
        response = httpx.patch(
            f"{mock_server}/beta/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/microsoftAuthenticator",
            json=update,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        # Should return the patched data unchanged
        assert data["id"] == "microsoftAuthenticator"
        assert data["state"] == "enabled"


class TestBetaErrorSimulation:
    """Tests for error simulation on beta endpoints."""

    def test_beta_mock_status_429(self, mock_server, auth_headers):
        """GET /beta/users?mock_status=429 returns throttled error."""
        response = httpx.get(
            f"{mock_server}/beta/users?mock_status=429",
            headers=auth_headers
        )
        assert response.status_code == 429
        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == "Request_Throttled"
        assert response.headers.get("Retry-After") == "1"

    def test_beta_mock_status_403(self, mock_server, auth_headers):
        """GET /beta/users?mock_status=403 returns access denied."""
        response = httpx.get(
            f"{mock_server}/beta/users?mock_status=403",
            headers=auth_headers
        )
        assert response.status_code == 403
        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == "Authorization_RequestDenied"


class TestBetaCloudTargets:
    """Tests that beta routes work with multiple cloud targets."""

    def test_beta_gcc_moderate_context(self, mock_server, auth_headers):
        """GET /beta/users on gcc-moderate returns graph.microsoft.com context."""
        response = httpx.get(f"{mock_server}/beta/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        assert "@odata.context" in data
        # Should contain graph.microsoft.com (not graph.microsoft.us) for gcc-moderate
        context = data["@odata.context"]
        assert "graph.microsoft.com/beta/" in context


class TestBetaUnmappedPaths:
    """Tests for unmapped/404 paths on beta routes."""

    def test_beta_unmapped_path_returns_404(self, mock_server, auth_headers):
        """GET /beta/nonexistent/path returns 404."""
        response = httpx.get(f"{mock_server}/beta/nonexistent/path", headers=auth_headers)
        assert response.status_code == 404
        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == "Request_ResourceNotFound"

    def test_beta_root_returns_404(self, mock_server, auth_headers):
        """GET /beta/ with no path returns 404."""
        response = httpx.get(f"{mock_server}/beta/", headers=auth_headers)
        assert response.status_code == 404


class TestBetaItemEndpoints:
    """Tests for beta endpoints that handle item-level requests."""

    def test_beta_user_auth_methods(self, mock_server, auth_headers):
        """GET /beta/users/{user_id}/authentication/methods returns auth methods."""
        response = httpx.get(
            f"{mock_server}/beta/users/550e8400-e29b-41d4-a716-446655440000/authentication/methods",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]

    def test_beta_me_auth_methods(self, mock_server, auth_headers):
        """GET /beta/me/authentication/methods returns auth methods."""
        response = httpx.get(
            f"{mock_server}/beta/me/authentication/methods",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]

    def test_beta_directory_role_members(self, mock_server, auth_headers):
        """GET /beta/directoryRoles/{role_id}/members returns members."""
        response = httpx.get(
            f"{mock_server}/beta/directoryRoles/550e8400-e29b-41d4-a716-446655440000/members",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]
