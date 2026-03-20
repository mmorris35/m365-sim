"""
Tests for Commercial E5 cloud target.

Tests:
- Health check returns commercial-e5 cloud
- Organization fixture has correct tenant identity and E5 SKUs
- Users have contoso.com domain (not contoso-defense.com)
- Domains include contoso.com
- Graph API URLs use graph.microsoft.com (same as GCC Moderate, not sovereign cloud)
- Conditional Access policies are empty (greenfield)
- Auth methods are disabled (greenfield)
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
def mock_server_e5():
    """
    Session-scoped fixture that starts m365-sim server as a subprocess with commercial-e5 cloud.

    - Picks a random available port
    - Starts: python server.py --cloud commercial-e5 --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Start subprocess
    process = subprocess.Popen(
        ["python3", "server.py", "--cloud", "commercial-e5", "--port", str(port)],
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
        raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")

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


class TestCommercialE5Health:
    """Health check tests for Commercial E5 cloud."""

    def test_e5_health(self, mock_server_e5):
        """GET /health returns 200 with cloud: commercial-e5."""
        response = httpx.get(f"{mock_server_e5}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["scenario"] == "greenfield"
        assert data["cloud"] == "commercial-e5"


class TestCommercialE5Organization:
    """Tests for Commercial E5 organization fixture."""

    def test_e5_organization_name(self, mock_server_e5, auth_headers):
        """GET /v1.0/organization returns displayName: 'Contoso Corp'."""
        response = httpx.get(
            f"{mock_server_e5}/v1.0/organization", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 1
        org = data["value"][0]
        assert org["displayName"] == "Contoso Corp"

    def test_e5_organization_plans(self, mock_server_e5, auth_headers):
        """GET /v1.0/organization returns commercial E5 SKU plan IDs."""
        response = httpx.get(
            f"{mock_server_e5}/v1.0/organization", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        org = data["value"][0]
        plans = org["assignedPlans"]
        
        # Commercial E5 SKU IDs
        plan_ids = {p["servicePlanId"] for p in plans}
        assert "efb87545-963c-4e0d-99df-69c6916d9eb0" in plan_ids  # EXCHANGE_S_ENTERPRISE
        assert "64bfac92-2b17-4482-b5e5-a0304429de3e" in plan_ids  # MICROSOFT_DEFENDER_EXPERT
        assert "c1ec4a95-1f05-45b3-a911-aa3fa01094f5" in plan_ids  # INTUNE_A
        assert "eec0eb4f-6444-4f95-aba0-50c24d67f998" in plan_ids  # AAD_PREMIUM_P2


class TestCommercialE5Users:
    """Tests for Commercial E5 users fixture."""

    def test_e5_users_domain(self, mock_server_e5, auth_headers):
        """GET /v1.0/users returns users with contoso.com domain."""
        response = httpx.get(f"{mock_server_e5}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        users = data["value"]
        
        # Verify all users have contoso.com domain
        for user in users:
            assert user["userPrincipalName"].endswith("@contoso.com")


class TestCommercialE5Domains:
    """Tests for Commercial E5 domains fixture."""

    def test_e5_domains(self, mock_server_e5, auth_headers):
        """GET /v1.0/domains includes contoso.com."""
        response = httpx.get(f"{mock_server_e5}/v1.0/domains", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        domains = {d["id"] for d in data["value"]}
        assert "contoso.com" in domains
        assert "contoso.onmicrosoft.com" in domains


class TestCommercialE5GraphAPI:
    """Tests for Commercial E5 Graph API URLs."""

    def test_e5_graph_api_url(self, mock_server_e5, auth_headers):
        """@odata.context uses graph.microsoft.com (not sovereign cloud)."""
        response = httpx.get(f"{mock_server_e5}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Commercial E5 uses standard graph.microsoft.com, same as GCC Moderate
        assert data["@odata.context"].startswith("https://graph.microsoft.com/v1.0/")


class TestCommercialE5Policies:
    """Tests for Commercial E5 security and auth policies."""

    def test_e5_ca_policies_empty(self, mock_server_e5, auth_headers):
        """GET /v1.0/identity/conditionalAccess/policies returns empty array (greenfield)."""
        response = httpx.get(
            f"{mock_server_e5}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert data["value"] == []

    def test_e5_auth_methods_disabled(self, mock_server_e5, auth_headers):
        """GET /v1.0/policies/authenticationMethodsPolicy returns all disabled (greenfield)."""
        response = httpx.get(
            f"{mock_server_e5}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Greenfield: all auth methods should be disabled
        if "microsoftAuthenticator" in data:
            assert data["microsoftAuthenticator"]["state"] == "disabled"
        if "temporaryAccessPass" in data:
            assert data["temporaryAccessPass"]["state"] == "disabled"
        if "fido2" in data:
            assert data["fido2"]["state"] == "disabled"
