"""
Tests for whag-lite endpoints (PR #3): security defaults, SharePoint settings,
sensitivity labels, and subscribed SKUs.

Tests cover:
- All 4 endpoints return 200 with correct structure
- Greenfield vs hardened posture differences
- $top parameter on collection endpoints
- /beta/ mirror routes with correct context URLs
"""

import pytest
import httpx


class TestSecurityDefaults:
    """Tests for /v1.0/policies/identitySecurityDefaultsEnforcementPolicy."""

    def test_returns_200_singleton(self, mock_server, auth_headers):
        """GET returns 200 with singleton entity."""
        response = httpx.get(
            f"{mock_server}/v1.0/policies/identitySecurityDefaultsEnforcementPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "identitySecurityDefaultsEnforcementPolicy/$entity" in data["@odata.context"]
        assert "id" in data
        assert "isEnabled" in data
        assert "displayName" in data

    def test_greenfield_enabled(self, mock_server, auth_headers):
        """Greenfield has security defaults enabled."""
        response = httpx.get(
            f"{mock_server}/v1.0/policies/identitySecurityDefaultsEnforcementPolicy",
            headers=auth_headers,
        )
        data = response.json()
        assert data["isEnabled"] is True

    def test_hardened_disabled(self, mock_server_hardened, auth_headers):
        """Hardened has security defaults disabled (replaced by CA policies)."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/policies/identitySecurityDefaultsEnforcementPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["isEnabled"] is False

    def test_beta_mirror(self, mock_server, auth_headers):
        """GET /beta/ mirror returns correct beta context URL."""
        response = httpx.get(
            f"{mock_server}/beta/policies/identitySecurityDefaultsEnforcementPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "beta" in data["@odata.context"]


class TestSharePointSettings:
    """Tests for /v1.0/admin/sharepoint/settings."""

    def test_returns_200_singleton(self, mock_server, auth_headers):
        """GET returns 200 with singleton entity."""
        response = httpx.get(
            f"{mock_server}/v1.0/admin/sharepoint/settings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "admin/sharepoint/settings/$entity" in data["@odata.context"]
        assert "sharingCapability" in data
        assert "sharingDomainRestrictionMode" in data

    def test_greenfield_open_sharing(self, mock_server, auth_headers):
        """Greenfield has external sharing wide open."""
        response = httpx.get(
            f"{mock_server}/v1.0/admin/sharepoint/settings",
            headers=auth_headers,
        )
        data = response.json()
        assert data["sharingCapability"] == "externalUserAndGuestSharing"
        assert data["sharingDomainRestrictionMode"] == "none"

    def test_hardened_restricted_sharing(self, mock_server_hardened, auth_headers):
        """Hardened has restricted sharing with allowlist."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/admin/sharepoint/settings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sharingCapability"] == "existingExternalUserSharingOnly"
        assert data["sharingDomainRestrictionMode"] == "allowList"
        assert "contoso-defense.com" in data["sharingAllowedDomainList"]

    def test_beta_mirror(self, mock_server, auth_headers):
        """GET /beta/ mirror returns correct beta context URL."""
        response = httpx.get(
            f"{mock_server}/beta/admin/sharepoint/settings",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "beta" in data["@odata.context"]


class TestSensitivityLabels:
    """Tests for /v1.0/security/informationProtection/sensitivityLabels."""

    def test_returns_200_collection(self, mock_server, auth_headers):
        """GET returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/v1.0/security/informationProtection/sensitivityLabels",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "sensitivityLabels" in data["@odata.context"]
        assert "value" in data
        assert isinstance(data["value"], list)

    def test_greenfield_empty(self, mock_server, auth_headers):
        """Greenfield has no sensitivity labels configured."""
        response = httpx.get(
            f"{mock_server}/v1.0/security/informationProtection/sensitivityLabels",
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["value"]) == 0

    def test_hardened_has_labels(self, mock_server_hardened, auth_headers):
        """Hardened has 4 sensitivity labels."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/security/informationProtection/sensitivityLabels",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 4
        names = [label["name"] for label in data["value"]]
        assert "Public" in names
        assert "Highly Confidential" in names

    def test_hardened_label_structure(self, mock_server_hardened, auth_headers):
        """Each label has required fields."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/security/informationProtection/sensitivityLabels",
            headers=auth_headers,
        )
        data = response.json()
        for label in data["value"]:
            assert "id" in label
            assert "name" in label
            assert "sensitivity" in label
            assert "isActive" in label

    def test_top_parameter(self, mock_server_hardened, auth_headers):
        """$top=2 returns only 2 labels."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/security/informationProtection/sensitivityLabels?$top=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

    def test_beta_mirror(self, mock_server, auth_headers):
        """GET /beta/ mirror returns correct beta context URL."""
        response = httpx.get(
            f"{mock_server}/beta/security/informationProtection/sensitivityLabels",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "beta" in data["@odata.context"]


class TestSubscribedSkus:
    """Tests for /beta/subscribedSkus (beta path mapping only)."""

    def test_returns_200_collection(self, mock_server, auth_headers):
        """GET /beta/subscribedSkus returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/beta/subscribedSkus",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "subscribedSkus" in data["@odata.context"]
        assert "value" in data
        assert isinstance(data["value"], list)

    def test_e5_sku_present(self, mock_server, auth_headers):
        """Greenfield has SPE_E5 SKU."""
        response = httpx.get(
            f"{mock_server}/beta/subscribedSkus",
            headers=auth_headers,
        )
        data = response.json()
        assert len(data["value"]) >= 1
        sku_parts = [sku["skuPartNumber"] for sku in data["value"]]
        assert "SPE_E5" in sku_parts

    def test_e5_service_plans(self, mock_server, auth_headers):
        """E5 SKU includes expected service plans."""
        response = httpx.get(
            f"{mock_server}/beta/subscribedSkus",
            headers=auth_headers,
        )
        data = response.json()
        e5 = [sku for sku in data["value"] if sku["skuPartNumber"] == "SPE_E5"][0]
        plan_names = [p["servicePlanName"] for p in e5["servicePlans"]]
        assert "AAD_PREMIUM_P2" in plan_names
        assert "INTUNE_A" in plan_names
        assert "MTP" in plan_names
