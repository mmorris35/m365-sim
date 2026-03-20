"""
Tests for m365-sim GCC High hardened and partial scenarios.

Tests:
- GCC High hardened scenario: 8 CA policies, auth methods (FIDO2), devices, compliance
- GCC High partial scenario: 3 CA policies, partial auth, fewer devices, subset compliance
- URL verification: all responses use graph.microsoft.us URLs
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
def mock_server_gcc_high_hardened():
    """
    Session-scoped fixture that starts m365-sim server with GCC High hardened scenario.

    - Picks a random available port
    - Starts: python server.py --cloud gcc-high --scenario hardened --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Start subprocess with GCC High hardened scenario
    process = subprocess.Popen(
        [
            "python3",
            "server.py",
            "--cloud",
            "gcc-high",
            "--scenario",
            "hardened",
            "--port",
            str(port),
        ],
        cwd="/home/mmn/github/m365-sim",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (retry loop, 5s timeout)
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
        # Timeout reached
        process.kill()
        raise RuntimeError(
            f"GCC High hardened server failed to start on port {port} within {timeout}s"
        )

    yield url

    # Cleanup: kill subprocess
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="session")
def mock_server_gcc_high_partial():
    """
    Session-scoped fixture that starts m365-sim server with GCC High partial scenario.

    - Picks a random available port
    - Starts: python server.py --cloud gcc-high --scenario partial --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Start subprocess with GCC High partial scenario
    process = subprocess.Popen(
        [
            "python3",
            "server.py",
            "--cloud",
            "gcc-high",
            "--scenario",
            "partial",
            "--port",
            str(port),
        ],
        cwd="/home/mmn/github/m365-sim",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (retry loop, 5s timeout)
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
        # Timeout reached
        process.kill()
        raise RuntimeError(
            f"GCC High partial server failed to start on port {port} within {timeout}s"
        )

    yield url

    # Cleanup: kill subprocess
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def auth_headers():
    """Return Bearer token headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


class TestGccHighHardenedCAPolicy:
    """Tests for GCC High hardened conditional access policies."""

    def test_gcc_high_hardened_ca_policies_count(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """GET /v1.0/identity/conditionalAccess/policies returns 8 CMMC policies."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 8

    def test_gcc_high_hardened_ca_policies_report_only(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """All CA policies have state=enabledForReportingButNotEnforced."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for policy in data["value"]:
            assert policy["state"] == "enabledForReportingButNotEnforced"
            assert policy["state"] != "enabled"

    def test_gcc_high_hardened_ca_policies_breakglass_excluded(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """All CA policies exclude break-glass account."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for policy in data["value"]:
            conditions = policy.get("conditions", {})
            users = conditions.get("users", {})
            exclude_users = users.get("excludeUsers", [])
            assert "00000000-0000-0000-0000-000000000011" in exclude_users

    def test_gcc_high_hardened_ca_policy_microsoft_us_context(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """@odata.context uses graph.microsoft.us for GCC High."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "graph.microsoft.us" in data["@odata.context"]
        assert "graph.microsoft.com" not in data["@odata.context"]


class TestGccHighHardenedAuthMethods:
    """Tests for GCC High hardened authentication methods."""

    def test_gcc_high_hardened_auth_methods_enabled(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """microsoftAuthenticator, fido2, and temporaryAccessPass are enabled."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "authenticationMethodConfigurations" in data

        method_states = {
            config["id"]: config["state"]
            for config in data["authenticationMethodConfigurations"]
        }

        assert method_states["microsoftAuthenticator"] == "enabled"
        assert method_states["fido2"] == "enabled"
        assert method_states["temporaryAccessPass"] == "enabled"
        assert method_states["sms"] == "disabled"

    def test_gcc_high_hardened_auth_policy_microsoft_us_context(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """@odata.context uses graph.microsoft.us for GCC High."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "graph.microsoft.us" in data["@odata.context"]


class TestGccHighHardenedDevices:
    """Tests for GCC High hardened managed devices and compliance."""

    def test_gcc_high_hardened_managed_devices(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """GET /v1.0/deviceManagement/managedDevices returns 3 compliant devices."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/deviceManagement/managedDevices",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 3

        for device in data["value"]:
            assert device["complianceState"] == "compliant"

    def test_gcc_high_hardened_compliance_policies(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """GET /v1.0/deviceManagement/deviceCompliancePolicies returns 3 policies."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 3

        policy_names = {policy["displayName"] for policy in data["value"]}
        expected_names = {
            "CMMC-Windows-Compliance",
            "CMMC-iOS-Compliance",
            "CMMC-Android-Compliance",
        }
        assert policy_names == expected_names


class TestGccHighPartialCAPolicy:
    """Tests for GCC High partial conditional access policies."""

    def test_gcc_high_partial_ca_policies_count(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """GET /v1.0/identity/conditionalAccess/policies returns 3 CMMC policies."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 3

    def test_gcc_high_partial_ca_policies_subset(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """Partial scenario has the basic 3 CA policies."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        policy_names = {policy["displayName"] for policy in data["value"]}
        expected_names = {
            "CMMC-MFA-AllUsers",
            "CMMC-MFA-Admins",
            "CMMC-Block-Legacy-Auth",
        }
        assert policy_names == expected_names

    def test_gcc_high_partial_ca_policy_microsoft_us_context(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """@odata.context uses graph.microsoft.us for GCC High partial."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "graph.microsoft.us" in data["@odata.context"]


class TestGccHighPartialAuthMethods:
    """Tests for GCC High partial authentication methods."""

    def test_gcc_high_partial_auth_methods_limited(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """Partial scenario has only microsoftAuthenticator enabled."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "authenticationMethodConfigurations" in data

        method_states = {
            config["id"]: config["state"]
            for config in data["authenticationMethodConfigurations"]
        }

        assert method_states["microsoftAuthenticator"] == "enabled"
        assert method_states["fido2"] == "disabled"
        assert method_states["temporaryAccessPass"] == "disabled"
        assert method_states["sms"] == "disabled"

    def test_gcc_high_partial_me_no_fido2(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """GET /v1.0/me/authentication/methods does not include FIDO2."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/me/authentication/methods",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

        # Verify no FIDO2 method
        for method in data["value"]:
            assert method.get("@odata.type") != "#microsoft.graph.fido2AuthenticationMethod"


class TestGccHighPartialDevices:
    """Tests for GCC High partial managed devices and compliance."""

    def test_gcc_high_partial_managed_devices(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """GET /v1.0/deviceManagement/managedDevices returns 1 device."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/deviceManagement/managedDevices",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        assert data["value"][0]["deviceName"] == "CONTOSO-LT001"

    def test_gcc_high_partial_compliance_policies(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """GET /v1.0/deviceManagement/deviceCompliancePolicies returns 1 policy."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "CMMC-Windows-Compliance"


class TestGccHighURLs:
    """Tests to verify GCC High responses use graph.microsoft.us URLs."""

    def test_gcc_high_hardened_managed_devices_url(
        self, mock_server_gcc_high_hardened, auth_headers
    ):
        """Managed devices response uses graph.microsoft.us."""
        response = httpx.get(
            f"{mock_server_gcc_high_hardened}/v1.0/deviceManagement/managedDevices",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "graph.microsoft.us" in data["@odata.context"]

    def test_gcc_high_partial_me_auth_methods_url(
        self, mock_server_gcc_high_partial, auth_headers
    ):
        """Me auth methods response uses graph.microsoft.us."""
        response = httpx.get(
            f"{mock_server_gcc_high_partial}/v1.0/me/authentication/methods",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "graph.microsoft.us" in data["@odata.context"]
