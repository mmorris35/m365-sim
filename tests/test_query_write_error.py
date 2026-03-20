"""
Query param, write operation, and error simulation tests for m365-sim.

Tests:
- $top query parameter truncation
- POST and PATCH write stubs
- mock_status error simulation
- 404 error handling
- State immutability (writes don't mutate fixtures)
"""

import pytest
import httpx


class TestQueryParams:
    """Tests for query parameter handling."""

    def test_top_truncation(self, mock_server, auth_headers):
        """GET /v1.0/directoryRoles?$top=2 returns exactly 2 roles."""
        response = httpx.get(
            f"{mock_server}/v1.0/directoryRoles?$top=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

    def test_top_on_empty_collection(self, mock_server, auth_headers):
        """GET /v1.0/groups?$top=5 returns empty value for empty collection."""
        response = httpx.get(
            f"{mock_server}/v1.0/groups?$top=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert data["value"] == []


class TestWriteOperations:
    """Tests for POST and PATCH write stubs."""

    def test_post_ca_policy(self, mock_server, auth_headers):
        """POST to CA policies returns 201 with id and createdDateTime."""
        payload = {
            "displayName": "Test Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
            "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
        }
        response = httpx.post(
            f"{mock_server}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "createdDateTime" in data
        assert data["displayName"] == "Test Policy"

    def test_patch_auth_method(self, mock_server, auth_headers):
        """PATCH to microsoftAuthenticator returns 200."""
        payload = {"state": "enabled"}
        response = httpx.patch(
            f"{mock_server}/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/microsoftAuthenticator",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "enabled"

    def test_post_compliance_policy(self, mock_server, auth_headers):
        """POST to compliance policies returns 201 with id."""
        payload = {
            "displayName": "Test Compliance Policy",
            "@odata.type": "#microsoft.graph.deviceCompliancePolicy",
        }
        response = httpx.post(
            f"{mock_server}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "createdDateTime" in data
        assert data["displayName"] == "Test Compliance Policy"


class TestErrorSimulation:
    """Tests for mock_status error simulation."""

    def test_mock_status_429(self, mock_server, auth_headers):
        """GET with ?mock_status=429 returns 429 with Retry-After header."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?mock_status=429",
            headers=auth_headers,
        )
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "1"
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "Request_Throttled"

    def test_mock_status_403(self, mock_server, auth_headers):
        """GET with ?mock_status=403 returns 403 with Graph error body."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?mock_status=403",
            headers=auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "Authorization_RequestDenied"
        assert "message" in data["error"]

    def test_mock_status_404(self, mock_server, auth_headers):
        """GET with ?mock_status=404 returns 404."""
        response = httpx.get(
            f"{mock_server}/v1.0/users?mock_status=404",
            headers=auth_headers,
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data


class TestErrorHandling:
    """Tests for error handling and 404 responses."""

    def test_unmapped_path_returns_404(self, mock_server, auth_headers):
        """GET /v1.0/nonexistent/path returns 404 with path in error message."""
        response = httpx.get(
            f"{mock_server}/v1.0/nonexistent/path",
            headers=auth_headers,
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "Request_ResourceNotFound"
        assert "nonexistent/path" in data["error"]["message"]


class TestStateImmutability:
    """Tests to verify that write operations do not mutate fixture state."""

    def test_write_operation_does_not_mutate_state(self, mock_server, auth_headers):
        """POST a CA policy, then GET policies, verify original fixture unchanged."""
        # POST a new policy
        payload = {
            "displayName": "Temporary Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
            "grantControls": {"operator": "OR", "builtInControls": ["mfa"]},
        }
        response = httpx.post(
            f"{mock_server}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=payload,
        )
        assert response.status_code == 201

        # GET policies and verify the original fixture is still empty
        response = httpx.get(
            f"{mock_server}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert data["value"] == []  # Should still be empty
