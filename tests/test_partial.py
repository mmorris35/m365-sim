"""
Smoke tests for m365-sim partial scenario.

Tests:
- Partial conditional access policies (3 of 8 CMMC policies)
- Report-only state enforcement
- Break-glass account exclusion
- Partially enabled auth methods (Authenticator enabled, FIDO2 disabled)
- Managed devices (1 compliant device)
- Compliance policies (1 policy)
- Fixture inheritance from greenfield
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
def mock_server_partial():
    """
    Session-scoped fixture that starts m365-sim server with partial scenario.

    - Picks a random available port
    - Starts: python server.py --scenario partial --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Start subprocess with partial scenario
    process = subprocess.Popen(
        ["python3", "server.py", "--scenario", "partial", "--port", str(port)],
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
            f"Partial server failed to start on port {port} within {timeout}s"
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


class TestPartialCAPolicy:
    """Tests for partial conditional access policies."""

    def test_partial_ca_policies_count(self, mock_server_partial, auth_headers):
        """GET /v1.0/identity/conditionalAccess/policies returns 3 CMMC policies."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 3

    def test_partial_ca_policies_report_only(self, mock_server_partial, auth_headers):
        """All CA policies have state=enabledForReportingButNotEnforced."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for policy in data["value"]:
            assert policy["state"] == "enabledForReportingButNotEnforced"

    def test_partial_ca_policies_breakglass_excluded(
        self, mock_server_partial, auth_headers
    ):
        """All CA policies exclude break-glass account (00000000-0000-0000-0000-000000000011)."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        for policy in data["value"]:
            if "conditions" in policy and "users" in policy["conditions"]:
                if "excludeUsers" in policy["conditions"]["users"]:
                    assert (
                        "00000000-0000-0000-0000-000000000011"
                        in policy["conditions"]["users"]["excludeUsers"]
                    )


class TestPartialAuthMethods:
    """Tests for partial authentication methods policy."""

    def test_partial_auth_methods(self, mock_server_partial, auth_headers):
        """Auth methods policy has microsoftAuthenticator enabled, others disabled."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "authenticationMethodConfigurations" in data

        # Build a state map by id
        methods = {m["id"]: m["state"] for m in data["authenticationMethodConfigurations"]}

        # Verify partial deployment state
        assert methods["microsoftAuthenticator"] == "enabled"
        assert methods["fido2"] == "disabled"
        assert methods["temporaryAccessPass"] == "disabled"
        assert methods["sms"] == "disabled"


class TestPartialManagedDevices:
    """Tests for partial managed devices."""

    def test_partial_managed_devices(self, mock_server_partial, auth_headers):
        """GET /v1.0/deviceManagement/managedDevices returns 1 compliant device."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/deviceManagement/managedDevices",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        assert data["value"][0]["complianceState"] == "compliant"


class TestPartialCompliancePolicies:
    """Tests for partial compliance policies."""

    def test_partial_compliance_policies(self, mock_server_partial, auth_headers):
        """GET /v1.0/deviceManagement/deviceCompliancePolicies returns 1 Windows policy."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "CMMC-Windows-Compliance"


class TestPartialInheritance:
    """Tests for fixture inheritance from greenfield."""

    def test_partial_inherits_greenfield_users(self, mock_server_partial, auth_headers):
        """GET /v1.0/users returns same 2 users as greenfield."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/users",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

    def test_partial_inherits_greenfield_organization(
        self, mock_server_partial, auth_headers
    ):
        """GET /v1.0/organization returns Contoso Defense LLC."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/organization",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        assert data["value"][0]["displayName"] == "Contoso Defense LLC"

    def test_partial_no_fido2(self, mock_server_partial, auth_headers):
        """GET /v1.0/me/authentication/methods returns 2 entries (no FIDO2)."""
        response = httpx.get(
            f"{mock_server_partial}/v1.0/me/authentication/methods",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

        # Verify no FIDO2 keys
        for method in data["value"]:
            assert "fido2" not in method.get("@odata.type", "").lower()
