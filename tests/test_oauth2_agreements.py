"""
Tests for oauth2PermissionGrants and agreements endpoints (Phase 26).

Tests cover:
- OAuth2 permission grants: greenfield empty, hardened has grants, structure validation, $top truncation, beta mirror
- Agreements: greenfield empty, partial with isViewingBeforeAcceptanceRequired: false, hardened with true, $top truncation, beta mirror
"""

import pytest
import httpx


class TestOAuth2PermissionGrants:
    """Tests for /v1.0/oauth2PermissionGrants collection."""

    def test_returns_200_collection(self, mock_server, auth_headers):
        """GET returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "oauth2PermissionGrants" in data["@odata.context"]
        assert "value" in data
        assert isinstance(data["value"], list)

    def test_greenfield_empty(self, mock_server, auth_headers):
        """Greenfield has no oauth2 permission grants configured."""
        response = httpx.get(
            f"{mock_server}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["value"]) == 0

    def test_hardened_has_grants(self, mock_server_hardened, auth_headers):
        """Hardened has 3 oauth2 permission grants."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3

    def test_hardened_grant_structure(self, mock_server_hardened, auth_headers):
        """Each grant has required fields."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        data = response.json()
        for grant in data["value"]:
            assert "id" in grant
            assert "clientId" in grant
            assert "consentType" in grant
            assert "resourceId" in grant
            assert "scope" in grant

    def test_hardened_grant_consent_types(self, mock_server_hardened, auth_headers):
        """Hardened grants use AllPrincipals consent type."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        data = response.json()
        for grant in data["value"]:
            assert grant["consentType"] == "AllPrincipals"

    def test_hardened_grant_scopes(self, mock_server_hardened, auth_headers):
        """Hardened grants have expected scopes."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/oauth2PermissionGrants",
            headers=auth_headers,
        )
        data = response.json()
        scopes = [grant["scope"] for grant in data["value"]]
        assert "User.Read" in scopes
        assert "openid profile" in scopes

    def test_top_parameter(self, mock_server_hardened, auth_headers):
        """$top=2 returns only 2 grants."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/oauth2PermissionGrants?$top=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

    def test_beta_mirror(self, mock_server, auth_headers):
        """GET /beta/ mirror returns correct beta context URL."""
        response = httpx.get(
            f"{mock_server}/beta/oauth2PermissionGrants",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "beta" in data["@odata.context"]
        assert "oauth2PermissionGrants" in data["@odata.context"]


class TestAgreements:
    """Tests for /v1.0/agreements collection."""

    def test_returns_200_collection(self, mock_server, auth_headers):
        """GET returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/v1.0/agreements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "agreements" in data["@odata.context"]
        assert "value" in data
        assert isinstance(data["value"], list)

    def test_greenfield_empty(self, mock_server, auth_headers):
        """Greenfield has no agreements configured."""
        response = httpx.get(
            f"{mock_server}/v1.0/agreements",
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["value"]) == 0

    def test_partial_has_agreement(self, mock_server_partial, auth_headers):
        """Partial scenario has 1 agreement."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/agreements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

    def test_partial_agreement_viewing_before_acceptance_false(self, mock_server_partial, auth_headers):
        """Partial scenario agreement has isViewingBeforeAcceptanceRequired: false."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/agreements",
            headers=auth_headers,
        )
        data = response.json()
        agreement = data["value"][0]
        assert agreement["isViewingBeforeAcceptanceRequired"] is False

    def test_hardened_has_agreement(self, mock_server_hardened, auth_headers):
        """Hardened scenario has 1 agreement."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/agreements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

    def test_hardened_agreement_viewing_before_acceptance_true(self, mock_server_hardened, auth_headers):
        """Hardened scenario agreement has isViewingBeforeAcceptanceRequired: true."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/agreements",
            headers=auth_headers,
        )
        data = response.json()
        agreement = data["value"][0]
        assert agreement["isViewingBeforeAcceptanceRequired"] is True

    def test_hardened_agreement_structure(self, mock_server_hardened, auth_headers):
        """Hardened agreement has required fields."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/agreements",
            headers=auth_headers,
        )
        data = response.json()
        agreement = data["value"][0]
        assert "id" in agreement
        assert "displayName" in agreement
        assert "isViewingBeforeAcceptanceRequired" in agreement
        assert "isPerDeviceAcceptanceRequired" in agreement
        assert "createdDateTime" in agreement

    def test_hardened_agreement_display_name(self, mock_server_hardened, auth_headers):
        """Hardened agreement has expected display name."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/agreements",
            headers=auth_headers,
        )
        data = response.json()
        agreement = data["value"][0]
        assert agreement["displayName"] == "Acceptable Use Policy"

    def test_top_parameter(self, mock_server_hardened, auth_headers):
        """$top=1 returns only 1 agreement (already 1 in hardened)."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/agreements?$top=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

    def test_beta_mirror(self, mock_server, auth_headers):
        """GET /beta/ mirror returns correct beta context URL."""
        response = httpx.get(
            f"{mock_server}/beta/agreements",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "beta" in data["@odata.context"]
        assert "agreements" in data["@odata.context"]
