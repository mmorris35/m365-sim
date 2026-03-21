"""
Comprehensive tests for Priority 1 endpoints (Subtask 23.1.3).

Tests cover:
- All 9 new endpoints return 200 with correct structure
- Greenfield vs hardened posture differences
- $top parameter works on collection endpoints
- $filter parameter works on selected endpoints
- /beta/ mirror routes work with correct context URLs
- All @odata.context fields present and correct
"""

import subprocess
import time
import socket
import pytest
import httpx


def get_free_port():
    """Get a free port by creating a socket and letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def mock_server_greenfield():
    """
    Session-scoped fixture that starts m365-sim server with greenfield scenario.
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    process = subprocess.Popen(
        ["python3", "server.py", "--scenario", "greenfield", "--port", str(port)],
        cwd="/home/mmn/github/m365-sim",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    start_time = time.time()
    timeout = 5
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.1)
    else:
        process.kill()
        raise RuntimeError(f"Greenfield server failed to start on port {port}")

    yield url

    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="session")
def mock_server_hardened():
    """
    Session-scoped fixture that starts m365-sim server with hardened scenario.
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    process = subprocess.Popen(
        ["python3", "server.py", "--scenario", "hardened", "--port", str(port)],
        cwd="/home/mmn/github/m365-sim",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    start_time = time.time()
    timeout = 5
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.1)
    else:
        process.kill()
        raise RuntimeError(f"Hardened server failed to start on port {port}")

    yield url

    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def auth_headers():
    """Return Bearer token headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


class TestAuthorizationPolicy:
    """Tests for /v1.0/policies/authorizationPolicy endpoint."""

    def test_authorization_policy_returns_200_singleton(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/policies/authorizationPolicy returns 200 with singleton object."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/policies/authorizationPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Singleton should have id and displayName, no "value" key
        assert "id" in data
        assert data["id"] == "authorizationPolicy"
        assert "displayName" in data
        assert "@odata.context" in data
        assert "authorizationPolicy/$entity" in data["@odata.context"]

    def test_authorization_policy_greenfield_permissive(
        self, mock_server_greenfield, auth_headers
    ):
        """Greenfield authorization_policy has permissive guest settings."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/policies/authorizationPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["blockMsolPowerShell"] is False
        assert data["allowInvitesFrom"] == "adminsAndGuestInviters"

    def test_authorization_policy_hardened_restricted(
        self, mock_server_hardened, auth_headers
    ):
        """Hardened authorization_policy has restricted guest settings."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/policies/authorizationPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["blockMsolPowerShell"] is True
        # Hardened should still be adminsAndGuestInviters per fixture
        assert data["allowInvitesFrom"] == "adminsAndGuestInviters"

    def test_authorization_policy_beta_mirror(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /beta/policies/authorizationPolicy mirrors v1.0 with correct context."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/policies/authorizationPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        # Context should be rewritten to /beta/
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestAccessReviewDefinitions:
    """Tests for /v1.0/identityGovernance/accessReviews/definitions endpoint."""

    def test_access_review_definitions_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/identityGovernance/accessReviews/definitions returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/identityGovernance/accessReviews/definitions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "accessReviews/definitions" in data["@odata.context"]

    def test_access_review_definitions_greenfield_empty(
        self, mock_server_greenfield, auth_headers
    ):
        """Greenfield access_review_definitions is empty."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/identityGovernance/accessReviews/definitions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 0

    def test_access_review_definitions_hardened_populated(
        self, mock_server_hardened, auth_headers
    ):
        """Hardened access_review_definitions has 2 active reviews."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/identityGovernance/accessReviews/definitions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2
        # Check structure of first review
        review = data["value"][0]
        assert "id" in review
        assert "displayName" in review
        assert "status" in review
        assert review["status"] == "Active"

    def test_access_review_definitions_top_parameter(
        self, mock_server_hardened, auth_headers
    ):
        """GET /v1.0/identityGovernance/accessReviews/definitions?$top=1 truncates results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/identityGovernance/accessReviews/definitions?$top=1",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

    def test_access_review_definitions_beta_mirror(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /beta/identityGovernance/accessReviews/definitions mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/identityGovernance/accessReviews/definitions",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestManagedAppPolicies:
    """Tests for /v1.0/deviceAppManagement/managedAppPolicies endpoint."""

    def test_managed_app_policies_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/deviceAppManagement/managedAppPolicies returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceAppManagement/managedAppPolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "managedAppPolicies" in data["@odata.context"]

    def test_managed_app_policies_greenfield_empty(
        self, mock_server_greenfield, auth_headers
    ):
        """Greenfield managed_app_policies is empty."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceAppManagement/managedAppPolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 0

    def test_managed_app_policies_hardened_populated(
        self, mock_server_hardened, auth_headers
    ):
        """Hardened managed_app_policies has 3 policies (iOS, Android, Windows)."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/managedAppPolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3
        # Check that we have different OData types
        odata_types = {policy["@odata.type"] for policy in data["value"]}
        assert "#microsoft.graph.iosManagedAppProtection" in odata_types
        assert "#microsoft.graph.androidManagedAppProtection" in odata_types

    def test_managed_app_policies_top_parameter(
        self, mock_server_hardened, auth_headers
    ):
        """GET /v1.0/deviceAppManagement/managedAppPolicies?$top=2 truncates results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/managedAppPolicies?$top=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

    def test_managed_app_policies_filter_parameter(
        self, mock_server_hardened, auth_headers
    ):
        """GET /v1.0/deviceAppManagement/managedAppPolicies?$filter=displayName eq 'iOS App Protection Policy' filters results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/managedAppPolicies?$filter=displayName eq 'iOS App Protection Policy'",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Filter works and returns only the matching policy
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "iOS App Protection Policy"


class TestMobileApps:
    """Tests for /v1.0/deviceAppManagement/mobileApps endpoint."""

    def test_mobile_apps_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/deviceAppManagement/mobileApps returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceAppManagement/mobileApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "mobileApps" in data["@odata.context"]

    def test_mobile_apps_greenfield_empty(self, mock_server_greenfield, auth_headers):
        """Greenfield mobile_apps is empty."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceAppManagement/mobileApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 0

    def test_mobile_apps_hardened_populated(self, mock_server_hardened, auth_headers):
        """Hardened mobile_apps has 5 apps."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/mobileApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 5
        # Check structure of first app
        app = data["value"][0]
        assert "id" in app
        assert "displayName" in app
        assert "@odata.type" in app

    def test_mobile_apps_top_parameter(self, mock_server_hardened, auth_headers):
        """GET /v1.0/deviceAppManagement/mobileApps?$top=3 truncates results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/mobileApps?$top=3",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3

    def test_mobile_apps_filter_parameter(self, mock_server_hardened, auth_headers):
        """GET /v1.0/deviceAppManagement/mobileApps?$filter=displayName eq 'Microsoft Outlook' filters results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceAppManagement/mobileApps?$filter=displayName eq 'Microsoft Outlook'",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Filter works and returns only the matching app
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "Microsoft Outlook"

    def test_mobile_apps_beta_mirror(self, mock_server_greenfield, auth_headers):
        """GET /beta/deviceAppManagement/mobileApps mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/deviceAppManagement/mobileApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestDetectedApps:
    """Tests for /v1.0/deviceManagement/detectedApps endpoint."""

    def test_detected_apps_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/deviceManagement/detectedApps returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceManagement/detectedApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "detectedApps" in data["@odata.context"]

    def test_detected_apps_greenfield_empty(
        self, mock_server_greenfield, auth_headers
    ):
        """Greenfield detected_apps is empty."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/deviceManagement/detectedApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 0

    def test_detected_apps_hardened_populated(self, mock_server_hardened, auth_headers):
        """Hardened detected_apps has 10 apps."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceManagement/detectedApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 10
        # Check structure of first app
        app = data["value"][0]
        assert "id" in app
        assert "displayName" in app
        assert "publisher" in app
        assert "version" in app

    def test_detected_apps_top_parameter(self, mock_server_hardened, auth_headers):
        """GET /v1.0/deviceManagement/detectedApps?$top=5 truncates results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceManagement/detectedApps?$top=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 5

    def test_detected_apps_filter_parameter(
        self, mock_server_hardened, auth_headers
    ):
        """GET /v1.0/deviceManagement/detectedApps?$filter=displayName eq 'Microsoft Edge' filters results."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceManagement/detectedApps?$filter=displayName eq 'Microsoft Edge'",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Filter works and returns only the matching app
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "Microsoft Edge"

    def test_detected_apps_beta_mirror(self, mock_server_greenfield, auth_headers):
        """GET /beta/deviceManagement/detectedApps mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/deviceManagement/detectedApps",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestUsersRegisteredByMethod:
    """Tests for /v1.0/reports/authenticationMethods/usersRegisteredByMethod endpoint."""

    def test_users_registered_by_method_returns_200_singleton(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/reports/authenticationMethods/usersRegisteredByMethod returns 200 with singleton."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/reports/authenticationMethods/usersRegisteredByMethod",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Singleton should have userRegistrationDetails array, not "value" key
        assert "userRegistrationDetails" in data
        assert isinstance(data["userRegistrationDetails"], list)
        assert "@odata.context" in data
        assert "usersRegisteredByMethod/$entity" in data["@odata.context"]

    def test_users_registered_by_method_greenfield_low_adoption(
        self, mock_server_greenfield, auth_headers
    ):
        """Greenfield users_registered_by_method shows low MFA adoption."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/reports/authenticationMethods/usersRegisteredByMethod",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Find microsoftAuthenticator entry
        details = {d["id"]: d for d in data["userRegistrationDetails"]}
        assert "microsoftAuthenticator" in details
        assert details["microsoftAuthenticator"]["userRegistrationCount"] == 1
        assert details["fido2"]["userRegistrationCount"] == 0

    def test_users_registered_by_method_hardened_high_adoption(
        self, mock_server_hardened, auth_headers
    ):
        """Hardened users_registered_by_method shows high MFA adoption."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/reports/authenticationMethods/usersRegisteredByMethod",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Find method entries
        details = {d["id"]: d for d in data["userRegistrationDetails"]}
        assert "microsoftAuthenticator" in details
        # Hardened should have higher adoption
        assert details["microsoftAuthenticator"]["userRegistrationCount"] == 2
        assert details["fido2"]["userRegistrationCount"] == 2

    def test_users_registered_by_method_beta_mirror(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /beta/reports/authenticationMethods/usersRegisteredByMethod mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/reports/authenticationMethods/usersRegisteredByMethod",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "userRegistrationDetails" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestSubscribedSkus:
    """Tests for /v1.0/subscribedSkus endpoint (bonus endpoint)."""

    def test_subscribed_skus_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/subscribedSkus returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/subscribedSkus",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "subscribedSkus" in data["@odata.context"]

    def test_subscribed_skus_top_parameter(self, mock_server_greenfield, auth_headers):
        """GET /v1.0/subscribedSkus?$top=2 truncates results."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/subscribedSkus?$top=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) <= 2

    def test_subscribed_skus_beta_mirror(self, mock_server_greenfield, auth_headers):
        """GET /beta/subscribedSkus mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/subscribedSkus",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]


class TestProvisioningLogs:
    """Tests for /v1.0/auditLogs/provisioning endpoint (bonus endpoint)."""

    def test_provisioning_logs_returns_200_collection(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/auditLogs/provisioning returns 200 with collection."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/auditLogs/provisioning",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data
        assert "provisioning" in data["@odata.context"]

    def test_provisioning_logs_top_parameter(
        self, mock_server_greenfield, auth_headers
    ):
        """GET /v1.0/auditLogs/provisioning?$top=3 truncates results."""
        response = httpx.get(
            f"{mock_server_greenfield}/v1.0/auditLogs/provisioning?$top=3",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) <= 3

    def test_provisioning_logs_beta_mirror(self, mock_server_greenfield, auth_headers):
        """GET /beta/auditLogs/provisioning mirrors v1.0."""
        response = httpx.get(
            f"{mock_server_greenfield}/beta/auditLogs/provisioning",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]
